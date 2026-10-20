"""In-page DOM schema extractor traversing documents and child iframes."""

import logging
from typing import Any, List, Optional
from app.models.browser_schema import (
    FieldType,
    FormField,
    FormSchema,
    SelectOption,
    SubmitButton,
)

logger = logging.getLogger(__name__)

# In-page JS function to extract fields and submit buttons from a single Frame document
EXTRACTOR_JS = """
() => {
    function getCleanLabel(el) {
        // 1. Explicit label element referencing id
        if (el.id) {
            const labelEl = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
            if (labelEl && labelEl.innerText.trim()) {
                return labelEl.innerText.trim();
            }
        }

        // 2. Enclosing label element
        const parentLabel = el.closest('label');
        if (parentLabel && parentLabel.innerText.trim()) {
            return parentLabel.innerText.trim();
        }

        // 3. aria-label or aria-labelledby
        if (el.getAttribute('aria-label')) {
            return el.getAttribute('aria-label').trim();
        }
        if (el.getAttribute('aria-labelledby')) {
            const refEl = document.getElementById(el.getAttribute('aria-labelledby'));
            if (refEl && refEl.innerText.trim()) {
                return refEl.innerText.trim();
            }
        }

        // 4. Nearby container label or class-based label (Lever, Ashby, etc.)
        const fieldContainer = el.closest('.field, .application-question, .form-group, .form-field, div[class*="field"], div[class*="question"]');
        if (fieldContainer) {
            const candidateLabel = fieldContainer.querySelector('.label, .application-label, label, span[class*="label"], div[class*="label"]');
            if (candidateLabel && candidateLabel.innerText.trim()) {
                return candidateLabel.innerText.trim();
            }
        }

        // 5. Placeholder
        if (el.placeholder && el.placeholder.trim()) {
            return el.placeholder.trim();
        }

        // 6. Name attribute fallback
        if (el.name) {
            return el.name.replace(/[\\[\\]_-]/g, ' ').trim();
        }

        return '';
    }

    function generateSelector(el) {
        if (el.id) {
            return `#${CSS.escape(el.id)}`;
        }
        if (el.name) {
            const tag = el.tagName.toLowerCase();
            return `${tag}[name="${CSS.escape(el.name)}"]`;
        }
        if (el.dataset && el.dataset.testid) {
            return `[data-testid="${CSS.escape(el.dataset.testid)}"]`;
        }
        // Specific class identifier if available
        if (el.className && typeof el.className === 'string') {
            const classes = el.className.trim().split(/\\s+/).filter(c => c && !c.includes(':'));
            if (classes.length > 0) {
                return `${el.tagName.toLowerCase()}.${classes.join('.')}`;
            }
        }
        return el.tagName.toLowerCase();
    }

    const fields = [];
    const submitButtons = [];

    // 1. Interactive Inputs, Textareas, and Selects
    const elements = Array.from(document.querySelectorAll('input, textarea, select, [role="combobox"]'));

    for (const el of elements) {
        const tagName = el.tagName.toLowerCase();
        const type = (el.type || '').toLowerCase();

        // Skip hidden and non-data input types
        if (type === 'hidden' || type === 'reset' || type === 'button') {
            continue;
        }

        // Handle submit inputs
        if (type === 'submit') {
            const val = el.value || el.innerText || 'Submit';
            submitButtons.push({
                selector: generateSelector(el),
                text: val.trim(),
                is_primary: true
            });
            continue;
        }

        const label = getCleanLabel(el);
        const required = el.required ||
                         el.getAttribute('aria-required') === 'true' ||
                         label.includes('*') ||
                         /\\(required\\)/i.test(label);

        let fieldType = 'text';
        let options = [];

        if (tagName === 'textarea') {
            fieldType = 'textarea';
        } else if (tagName === 'select') {
            fieldType = 'select';
            const optElements = Array.from(el.querySelectorAll('option'));
            options = optElements.map(opt => ({
                label: opt.text.trim(),
                value: opt.value
            })).filter(o => o.value !== '' || o.label !== '');
        } else if (el.getAttribute('role') === 'combobox') {
            fieldType = 'combobox';
        } else {
            switch (type) {
                case 'email': fieldType = 'email'; break;
                case 'tel': fieldType = 'tel'; break;
                case 'url': fieldType = 'url'; break;
                case 'number': fieldType = 'number'; break;
                case 'date': fieldType = 'date'; break;
                case 'checkbox': fieldType = 'checkbox'; break;
                case 'radio': fieldType = 'radio'; break;
                case 'file': fieldType = 'file'; break;
                default:
                    // Semantic detection based on name or label
                    const lowerLabel = (label + ' ' + (el.name || '')).toLowerCase();
                    if (lowerLabel.includes('email')) fieldType = 'email';
                    else if (lowerLabel.includes('phone') || lowerLabel.includes('mobile')) fieldType = 'tel';
                    else if (lowerLabel.includes('linkedin') || lowerLabel.includes('website') || lowerLabel.includes('url') || lowerLabel.includes('portfolio') || lowerLabel.includes('github')) fieldType = 'url';
                    else if (lowerLabel.includes('date') || lowerLabel.includes('dob') || lowerLabel.includes('birth')) fieldType = 'date';
                    else fieldType = 'text';
                    break;
            }
        }

        const selector = generateSelector(el);
        const fieldId = el.id || el.name || `${fieldType}_${fields.length}`;

        fields.push({
            field_id: fieldId,
            selector: selector,
            field_type: fieldType,
            label: label || fieldId,
            required: Boolean(required),
            placeholder: el.placeholder || null,
            options: options,
            current_value: el.value || null,
            name_attr: el.name || null
        });
    }

    // 2. Buttons (Look for Submit / Apply buttons)
    const buttonElements = Array.from(document.querySelectorAll('button, [role="button"], input[type="submit"]'));
    for (const btn of buttonElements) {
        if (btn.type === 'submit' || btn.getAttribute('type') === 'submit') {
            const btnText = btn.innerText || btn.value || 'Submit Application';
            submitButtons.push({
                selector: generateSelector(btn),
                text: btnText.trim(),
                is_primary: true
            });
        } else {
            const text = (btn.innerText || btn.value || '').trim();
            const lower = text.toLowerCase();
            if (
                lower.includes('submit') ||
                lower.includes('apply') ||
                lower.includes('send application') ||
                lower.includes('complete application')
            ) {
                submitButtons.push({
                    selector: generateSelector(btn),
                    text: text,
                    is_primary: true
                });
            }
        }
    }

    const formIndicators = Array.from(document.querySelectorAll('form')).map(f => (f.id + ' ' + (f.className || '')).trim());

    return {
        fields: fields,
        submit_buttons: submitButtons,
        form_indicators: formIndicators
    };
}
"""


class DOMExtractor:
    """Extracts structured FormSchema from Playwright pages across all nested frames."""

    async def extract_schema(self, page: Any) -> FormSchema:
        """
        Executes JavaScript evaluation across the main page and all child frames,
        deduplicating inputs and consolidating into a typed FormSchema.
        """
        url = getattr(page, "url", "")
        try:
            page_title = await page.title()
        except Exception:
            page_title = ""

        all_fields: List[FormField] = []
        all_submit_buttons: List[SubmitButton] = []
        all_form_indicators: List[str] = []

        # Determine frame list
        frames = getattr(page, "frames", None)
        if not frames:
            frames = [page]

        has_iframes = len(frames) > 1

        for idx, frame in enumerate(frames):
            try:
                frame_data = await frame.evaluate(EXTRACTOR_JS)
                if not frame_data:
                    continue

                raw_fields = frame_data.get("fields", [])
                raw_buttons = frame_data.get("submit_buttons", [])
                indicators = frame_data.get("form_indicators", [])
                all_form_indicators.extend(indicators)

                for rf in raw_fields:
                    try:
                        ft = FieldType(rf["field_type"])
                    except ValueError:
                        ft = FieldType.TEXT

                    opts = [SelectOption(label=o["label"], value=o["value"]) for o in rf.get("options", [])]

                    field = FormField(
                        field_id=rf["field_id"],
                        selector=rf["selector"],
                        field_type=ft,
                        label=rf["label"],
                        required=rf["required"],
                        placeholder=rf.get("placeholder"),
                        options=opts,
                        current_value=rf.get("current_value"),
                        frame_index=idx,
                        name_attr=rf.get("name_attr"),
                    )
                    all_fields.append(field)

                for rb in raw_buttons:
                    btn = SubmitButton(
                        selector=rb["selector"],
                        text=rb["text"],
                        is_primary=rb.get("is_primary", True),
                    )
                    all_submit_buttons.append(btn)
            except Exception as e:
                logger.warning(f"Error extracting DOM from frame {idx}: {e}")

        # Deduplicate buttons by selector
        seen_button_selectors = set()
        deduped_buttons = []
        for btn in all_submit_buttons:
            if btn.selector not in seen_button_selectors:
                seen_button_selectors.add(btn.selector)
                deduped_buttons.append(btn)

        # Platform detection
        detected_platform = self._detect_platform(url, page_title, all_fields, all_form_indicators)

        schema = FormSchema(
            url=url,
            page_title=page_title,
            fields=all_fields,
            submit_buttons=deduped_buttons,
            has_iframes=has_iframes,
            detected_platform=detected_platform,
        )
        logger.info(
            f"Extracted FormSchema: platform={detected_platform}, fields={len(all_fields)}, "
            f"buttons={len(deduped_buttons)}, frames={len(frames)}"
        )
        return schema

    def _detect_platform(
        self,
        url: str,
        title: str,
        fields: List[FormField],
        form_indicators: Optional[List[str]] = None,
    ) -> str:
        """Infers the target application platform based on URL, title, selectors, and form attributes."""
        target_str = (url + " " + title).lower()
        field_names = " ".join([f.name_attr or "" for f in fields]).lower()
        field_selectors = " ".join([f.selector for f in fields]).lower()
        field_labels = " ".join([f.label for f in fields]).lower()
        indicators_str = " ".join(form_indicators or []).lower()

        if (
            "greenhouse.io" in target_str
            or "grnhse" in field_selectors
            or "application_form" in field_selectors
            or "application_form" in indicators_str
            or "job_application" in field_names
        ):
            return "greenhouse"
        if (
            "lever.co" in target_str
            or "urls[linkedin]" in field_names
            or "application-form" in field_selectors
            or "application-form" in indicators_str
        ):
            return "lever"
        if (
            "ashbyhq.com" in target_str
            or "_systemfield_" in field_selectors
            or "_systemfield_" in field_names
        ):
            return "ashby"
        if (
            "w-8ben" in target_str
            or "w8ben" in target_str
            or "ftin" in field_labels
            or "tax treaty" in field_labels
            or "beneficial owner" in target_str
        ):
            return "w8ben"

        return "generic"
