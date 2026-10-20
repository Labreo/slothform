"""Playwright form filler automation with remote CDP file streaming and dry-run guard."""

import datetime
import logging
import os
from typing import Any, Optional
from app.models.browser_schema import (
    FieldType,
    FillPlan,
    FillResult,
)
from app.services.document_generator import SyntheticDocumentGenerator

logger = logging.getLogger(__name__)


class FormFiller:
    """Executes validated FillPlans against Playwright pages with a pre-submission dry-run safety guard."""

    def __init__(self, screenshot_dir: Optional[str] = None):
        self.screenshot_dir = screenshot_dir or os.path.join(os.getcwd(), "artifacts", "screenshots")
        os.makedirs(self.screenshot_dir, exist_ok=True)
        self.doc_generator = SyntheticDocumentGenerator()

    async def fill(
        self,
        page: Any,
        fill_plan: FillPlan,
        dry_run: bool = True,
        session_id: Optional[str] = None,
    ) -> FillResult:
        """
        Populates form fields according to fill_plan:
        - Fills inputs, textareas, selects, comboboxes, checkboxes
        - Streams resume/tax files over CDP
        - If dry_run=True:
            - Outlines detected submit button in amber glow (outline: 4px solid #f59e0b)
            - Captures full-page screenshot
            - Strictly halts without triggering submission
        - If dry_run=False:
            - Clicks submit button and waits for confirmation
        """
        sess_id = session_id or getattr(page, "_session_id", "sess_local")
        replay_url = f"https://browserbase.com/sessions/{sess_id}"
        filled_count = 0
        error_msg = None

        frames = getattr(page, "frames", [page])

        # Step 0: Pre-flight DOM Neutralization & Network Route Guard (Dry-Run Mode)
        if dry_run:
            # 1. Register Playwright route handler aborting outbound submission requests
            if hasattr(page, "route"):
                async def _abort_dry_run_submissions(route):
                    req = route.request
                    if req.method in ("POST", "PUT", "PATCH"):
                        logger.warning(
                            f"[DRY-RUN GUARD] Aborting outbound {req.method} request to {req.url}"
                        )
                        await route.abort("blockedbyclient")
                    else:
                        await route.continue_()

                try:
                    await page.route("**/*", _abort_dry_run_submissions)
                    setattr(page, "_slothform_dry_run_route", _abort_dry_run_submissions)
                except Exception as e:
                    logger.debug(f"Could not register dry-run route handler: {e}")

            # 2. Injected script to neutralize DOM submission across page and child frames
            neutralize_script = """
            (() => {
                try {
                    // Intercept and prevent submit events in the capture phase
                    window.addEventListener("submit", function(e) {
                        e.preventDefault();
                        e.stopImmediatePropagation();
                        console.warn("[DRY-RUN GUARD] Intercepted and blocked form submit event");
                        return false;
                    }, true);

                    // Monkey-patch HTMLFormElement prototype methods
                    if (window.HTMLFormElement) {
                        HTMLFormElement.prototype.submit = function() {
                            console.warn("Blocked submit in dry run");
                        };
                        if (HTMLFormElement.prototype.requestSubmit) {
                            HTMLFormElement.prototype.requestSubmit = function() {
                                console.warn("Blocked requestSubmit in dry run");
                            };
                        }
                    }

                    // Defuse existing form actions and inline onsubmit handlers
                    const defuseForms = () => {
                        document.querySelectorAll("form").forEach(f => {
                            if (!f.hasAttribute("data-slothform-action")) {
                                f.setAttribute("data-slothform-action", f.action || "");
                            }
                            f.action = "javascript:void(0);";
                            f.onsubmit = function(e) {
                                if (e) {
                                    e.preventDefault();
                                    e.stopImmediatePropagation();
                                }
                                return false;
                            };
                        });
                    };

                    defuseForms();

                    if (window.MutationObserver) {
                        const observer = new MutationObserver(() => defuseForms());
                        observer.observe(document.documentElement || document.body, { childList: true, subtree: true });
                    }
                } catch (err) {
                    console.error("Error neutralizing DOM in dry run:", err);
                }
            })();
            """

            if hasattr(page, "add_init_script"):
                try:
                    await page.add_init_script(neutralize_script)
                except Exception as e:
                    logger.debug(f"Could not add init script: {e}")

            for f in frames:
                try:
                    await f.evaluate(neutralize_script)
                except Exception as e:
                    logger.debug(f"Could not evaluate neutralize script on frame: {e}")

        # Step 1: Populate fields
        for item in fill_plan.items:
            try:
                frame = frames[item.frame_index] if item.frame_index < len(frames) else page
                locator = frame.locator(item.selector).first

                if await locator.count() == 0:
                    logger.warning(f"Element not found for selector: {item.selector}")
                    continue

                if item.field_type in (
                    FieldType.TEXT,
                    FieldType.EMAIL,
                    FieldType.TEL,
                    FieldType.URL,
                    FieldType.NUMBER,
                    FieldType.DATE,
                ):
                    val_str = str(item.value) if item.value is not None else ""
                    try:
                        await locator.fill(val_str, timeout=3000)
                    except Exception:
                        await locator.click(timeout=2000)
                        await locator.press_sequentially(val_str, delay=10)
                    filled_count += 1

                elif item.field_type == FieldType.TEXTAREA:
                    val_str = str(item.value) if item.value is not None else ""
                    await locator.fill(val_str, timeout=3000)
                    filled_count += 1

                elif item.field_type == FieldType.SELECT:
                    val_str = str(item.value)
                    try:
                        await locator.select_option(value=val_str, timeout=3000)
                    except Exception:
                        # Fallback to select by visible label
                        await locator.select_option(label=val_str, timeout=3000)
                    filled_count += 1

                elif item.field_type == FieldType.CHECKBOX:
                    # Treat truthy values as check, falsy or specific 'false' / 'uncheck' as uncheck
                    val = item.value
                    should_check = bool(val and str(val).lower() not in ("false", "0", "uncheck", "no"))
                    if should_check:
                        await locator.check(timeout=3000)
                    else:
                        await locator.uncheck(timeout=3000)
                    filled_count += 1

                elif item.field_type == FieldType.RADIO:
                    await locator.check(timeout=3000)
                    filled_count += 1

                elif item.field_type == FieldType.COMBOBOX:
                    val_str = str(item.value)
                    await locator.click(timeout=3000)
                    # Try to locate dropdown option item
                    opt_locator = frame.locator(
                        f'[role="option"]:has-text("{val_str}"), li:has-text("{val_str}"), div[class*="option"]:has-text("{val_str}")'
                    ).first
                    if await opt_locator.count() > 0:
                        await opt_locator.click(timeout=3000)
                    else:
                        try:
                            await locator.fill(val_str, timeout=2000)
                            # Safe combobox handling: locate option after typing without pressing Enter
                            opt_after = frame.locator(
                                f'[role="option"]:has-text("{val_str}"), li:has-text("{val_str}"), div[class*="option"]:has-text("{val_str}")'
                            ).first
                            if await opt_after.count() > 0:
                                await opt_after.click(timeout=2000)
                        except Exception:
                            pass
                    filled_count += 1

                elif item.field_type == FieldType.FILE:
                    file_path = str(item.value) if item.value else None
                    if not file_path or not os.path.isfile(file_path):
                        # Inspect context to determine whether to generate tax document or resume
                        context_parts = [
                            item.field_id or "",
                            item.selector or "",
                            fill_plan.target_url or "",
                            getattr(item, "rationale", "") or "",
                        ]
                        try:
                            name_attr = await locator.get_attribute("name") or ""
                            aria_attr = await locator.get_attribute("aria-label") or ""
                            id_attr = await locator.get_attribute("id") or ""
                            context_parts.extend([name_attr, aria_attr, id_attr])
                            if id_attr:
                                label_el = frame.locator(f'label[for="{id_attr}"]').first
                                if await label_el.count() > 0:
                                    context_parts.append(await label_el.text_content() or "")
                        except Exception:
                            pass

                        full_context = " ".join(context_parts).lower()
                        tax_keywords = [
                            "tax",
                            "w8",
                            "w-8",
                            "w_8",
                            "w-8ben",
                            "w8ben",
                            "contractor",
                            "compliance",
                            "treaty",
                            "ftin",
                            "withholding",
                            "certificate of foreign",
                        ]
                        if any(kw in full_context for kw in tax_keywords):
                            file_path = self.doc_generator.generate_tax_document()
                            logger.info(f"Generated synthetic tax document fallback at {file_path}")
                        else:
                            if fill_plan.resume_path and os.path.isfile(fill_plan.resume_path):
                                file_path = fill_plan.resume_path
                            else:
                                file_path = self.doc_generator.generate_resume()
                            logger.info(f"Generated synthetic resume fallback at {file_path}")

                    # Playwright set_input_files works even when input is display: none
                    await locator.set_input_files(file_path, timeout=5000)
                    filled_count += 1

            except Exception as e:
                logger.warning(f"Failed to populate field {item.field_id} ({item.selector}): {e}")

        # Handle global resume_path if provided and file field wasn't populated explicitly
        if fill_plan.resume_path:
            for frame in frames:
                try:
                    file_inputs = frame.locator('input[type="file"]')
                    count = await file_inputs.count()
                    for i in range(count):
                        inp = file_inputs.nth(i)
                        file_val = await inp.evaluate("el => el.files.length")
                        if file_val == 0:
                            path_to_upload = fill_plan.resume_path
                            if not os.path.isfile(path_to_upload):
                                inp_id = await inp.get_attribute("id") or ""
                                inp_name = await inp.get_attribute("name") or ""
                                inp_aria = await inp.get_attribute("aria-label") or ""
                                ctx = f"{inp_id} {inp_name} {inp_aria} {fill_plan.target_url}".lower()
                                tax_keywords = ["tax", "w8", "w-8", "w_8", "contractor", "compliance"]
                                if any(kw in ctx for kw in tax_keywords):
                                    path_to_upload = self.doc_generator.generate_tax_document()
                                else:
                                    path_to_upload = self.doc_generator.generate_resume()
                            await inp.set_input_files(path_to_upload, timeout=5000)
                            filled_count += 1
                except Exception as e:
                    logger.debug(f"Global resume upload check: {e}")

        # Step 2: Detect Primary Visible Submit Button
        detected_submit_btn = None
        submit_locator = None

        candidate_selectors = [
            'button:has-text("Submit Application")',
            'button:has-text("Complete Application")',
            'button:has-text("Send Application")',
            'button.template-btn-submit',
            'button:has-text("Apply")',
            'button:has-text("Submit")',
            '[role="button"]:has-text("Submit Application")',
            '[role="button"]:has-text("Complete Application")',
            '[role="button"]:has-text("Send Application")',
            '[role="button"]:has-text("Apply")',
            '[role="button"]:has-text("Submit")',
            'input[type="submit"][value*="Submit Application" i]',
            'input[type="submit"][value*="Complete Application" i]',
            'input[type="submit"][value*="Apply" i]',
            'input[type="submit"][value*="Submit" i]',
            'input[type="submit"]',
            'button[type="submit"]',
            '[role="button"][type="submit"]',
        ]

        secondary_keywords = ["draft", "cancel", "back", "preview", "reset", "discard", "delete"]

        for sel in candidate_selectors:
            for frame in frames:
                try:
                    candidates = frame.locator(sel)
                    count = await candidates.count()
                    for idx in range(count):
                        loc = candidates.nth(idx)
                        # 1. Filter: Element must be visible
                        if not await loc.is_visible():
                            continue

                        # 2. Filter: Disqualify secondary actions
                        btn_text = (await loc.text_content() or "").strip()
                        btn_val = (await loc.get_attribute("value") or "").strip()
                        btn_name = (await loc.get_attribute("name") or "").strip()
                        btn_aria = (await loc.get_attribute("aria-label") or "").strip()
                        combined = f"{btn_text} {btn_val} {btn_name} {btn_aria}".lower()

                        if any(neg in combined for neg in secondary_keywords):
                            continue

                        detected_submit_btn = sel
                        submit_locator = loc
                        break
                    if submit_locator:
                        break
                except Exception:
                    continue
            if submit_locator:
                break

        screenshot_path = None

        # Step 3: Apply Dry-Run Guard or Submit
        if dry_run:
            logger.info("[DRY-RUN] Safety guard active. Highlighting submit button and capturing proof.")
            if submit_locator:
                try:
                    # Inject amber glowing border around the submit button
                    await submit_locator.evaluate(
                        "el => {"
                        "  el.style.outline = '4px solid #f59e0b';"
                        "  el.style.boxShadow = '0 0 20px #f59e0b';"
                        "  el.setAttribute('data-slothform-dry-run', 'guarded');"
                        "}"
                    )
                except Exception as e:
                    logger.warning(f"Could not style submit button: {e}")

            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            shot_file = f"dry_run_{sess_id}_{timestamp}.png"
            screenshot_path = os.path.join(self.screenshot_dir, shot_file)

            try:
                await page.screenshot(path=screenshot_path, full_page=True)
                logger.info(f"[DRY-RUN] Full-page verification screenshot saved to {screenshot_path}")
            except Exception as e:
                logger.warning(f"Could not capture screenshot: {e}")

            logger.info("[DRY-RUN] Safety guard strictly halted before submission action. No submit click performed.")

            return FillResult(
                status="DRY_RUN_SUCCESS",
                session_id=sess_id,
                replay_url=replay_url,
                screenshot_path=screenshot_path,
                fields_filled_count=filled_count,
                submit_button_detected=detected_submit_btn,
                dry_run=True,
                submitted=False,
                error=None,
            )

        else:
            # Live submission
            if not submit_locator:
                error_msg = "No submit button found on target form."
                logger.error(error_msg)
                return FillResult(
                    status="FAILED",
                    session_id=sess_id,
                    replay_url=replay_url,
                    fields_filled_count=filled_count,
                    dry_run=False,
                    submitted=False,
                    error=error_msg,
                )

            logger.info(f"Clicking submit button ({detected_submit_btn}) for real dispatch.")
            try:
                await submit_locator.click(timeout=10000)
                try:
                    await page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    pass

                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                shot_file = f"submission_{sess_id}_{timestamp}.png"
                screenshot_path = os.path.join(self.screenshot_dir, shot_file)
                try:
                    await page.screenshot(path=screenshot_path, full_page=True)
                except Exception:
                    pass

                return FillResult(
                    status="SUBMITTED",
                    session_id=sess_id,
                    replay_url=replay_url,
                    screenshot_path=screenshot_path,
                    fields_filled_count=filled_count,
                    submit_button_detected=detected_submit_btn,
                    dry_run=False,
                    submitted=True,
                    error=None,
                )
            except Exception as e:
                logger.error(f"Failed to submit form: {e}")
                return FillResult(
                    status="FAILED",
                    session_id=sess_id,
                    replay_url=replay_url,
                    fields_filled_count=filled_count,
                    submit_button_detected=detected_submit_btn,
                    dry_run=False,
                    submitted=False,
                    error=str(e),
                )
