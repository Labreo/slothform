# Project: SlothForm — Autonomous Privacy-Preserving Form-Filling Agent

## Architecture
SlothForm automates modern ATS job applications (Greenhouse, Lever, Ashby) and contractor tax/onboarding compliance (IRS Form W-8BEN) while preserving user privacy and preventing accidental submissions:

```
┌────────────────────────────────────────────────────────────────────────┐
│                              SLOTHFORM                                 │
│         The Autonomous Contractor Onboarding & Form-Filling Agent      │
└────────────────────────────────────────────────────────────────────────┘
          │                                                │
          ▼                                                ▼
  [Auth0 for AI Agents & Vault]                 [Browserbase Cloud]
  • AES-256-GCM Encrypted Identity Store        • Headless Chromium sandbox
  • 4-Tier Field Sensitivity Classification     • Residential proxy & CAPTCHA bypass
  • OIDC CIBA Backchannel Approval              • In-page JS DOM extraction
  • RFC 9396 Rich Auth Request (RAR) diff       • Playwright CDP file upload streaming
  • Submission Refusal Invariant                • Amber outlined --dry-run safety guard
          │                                                │
          └───────────────────────┬────────────────────────┘
                                  ▼
                    [Ultramarine 1 Flash Client]
                      (Paper Instruments API)
                    • Native client with sticky prompt caching
                    • Structured Pydantic FillPlan generation
                    • W-8BEN Tax Treaty: PAN -> Box 6a, omit 6b, MM-DD-YYYY, Art 12(2) 15%
                    • Grounded essay synthesis (no hallucination)
                                  │
                                  ▼
                    [FastAPI Web & Typer CLI]
                    • Dark luxury Jinja2 web dashboard
                    • Server-Sent Events (SSE) live telemetry
                    • Embedded Browserbase session replays
                    • Developer CLI: slothform fill <url> [--dry-run]
                    • Render blueprint (render.yaml)
```

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Target Form Ingestion | Accepts Greenhouse, Lever, Ashby, and W-8BEN URLs | M2 | ORIGINAL_REQUEST R1 |
| 2 | Browserbase Session Lifecycle | Cloud session provisioning (`proxies=True`, `solveCaptchas=True`), debug inspection, and explicit `REQUEST_RELEASE` teardown | M2 | ORIGINAL_REQUEST R1, Survey |
| 3 | Remote CDP Connection | Playwright connects over remote CDP WebSocket (`wss://connect.browserbase.com`) | M2 | Survey |
| 4 | In-Page DOM Extractor | Injected JavaScript extracts inputs, selects, textareas, and submit buttons into `FormSchema` | M2 | Survey |
| 5 | Multi-Frame & Iframe Support | Recursive frame inspection for Greenhouse/ATS embedded application iframes | M2 | Survey |
| 6 | Anti-Bot & CAPTCHA Evasion | Native handling of Cloudflare Turnstile, reCAPTCHA, and hCaptcha via Browserbase | M2 | Survey |
| 7 | Dynamic Form Field Filling | Playwright filling of text inputs, native selects, and custom comboboxes | M2 | ORIGINAL_REQUEST R1 |
| 8 | CDP File Upload Streaming | Remote file upload streaming for resumes and tax PDFs via `set_input_files` | M2 | ORIGINAL_REQUEST R1 |
| 9 | Synthetic Document Generator | Fallback PDF resume/tax document generator when user has no uploaded resume file | M2 | Survey |
| 10 | Pre-Submission Dry-Run Guard | Fills all fields, outlines submit button in amber, captures screenshot and replay, halts safely without clicking submit | M2 | ORIGINAL_REQUEST R5 |
| 11 | Session Replay Generation | Retrieves and surfaces playable Browserbase session replay URL (`https://browserbase.com/sessions/...`) | M2 | ORIGINAL_REQUEST R1 |
| 12 | Ultramarine 1 Flash Client | Native async client for Paper Instruments Ultramarine (`https://api.paperinstruments.com/v1`) | M3 | ORIGINAL_REQUEST R2 |
| 13 | Sticky Caching & Structured Output | `x-session-id` sticky header and Pydantic `FillPlan` response validation | M3 | Survey |
| 14 | W-8BEN Tax Treaty Domain Logic | Indian PAN -> Box 6a, omit Box 6b, DOB to `MM-DD-YYYY`, DTAA Article 12(2) at 15% withholding | M3 | ORIGINAL_REQUEST R2 |
| 15 | Anti-Hallucination Essay Synthesizer | Tailored 150-250 word responses strictly grounded in candidate's verified career profile | M3 | ORIGINAL_REQUEST R2 |
| 16 | AES-256-GCM Encrypted Vault | Authenticated local profile store (`data/vault.enc`) with HKDF-SHA256 key derivation from `AUTH0_TOKEN_VAULT_KEY` | M1 | ORIGINAL_REQUEST R3 |
| 17 | 4-Tier Field Sensitivity Engine | Classification (`PUBLIC`, `SEMI_SENSITIVE`, `CRITICAL_TAX`, `CRITICAL_FINANCIAL`) and context policies | M1 | ORIGINAL_REQUEST R3, Survey |
| 18 | Auth0 CIBA Backchannel Initiation | `POST /bc-authorize` with `login_hint`, `binding_message`, and structured diff | M1 | ORIGINAL_REQUEST R3 |
| 19 | Auth0 CIBA Token Polling | `POST /oauth/token` with `grant_type=urn:openid:params:grant-type:ciba` and dynamic `slow_down` handling | M1 | ORIGINAL_REQUEST R3, Survey |
| 20 | RFC 9396 Rich Auth Requests (RAR) | Structured JSON `authorization_details` diff with SHA-256 digest | M1 | Survey |
| 21 | Submission Refusal Invariant | Halts execution until explicit user consent; refuses submission if unapproved or rejected | M1 | ORIGINAL_REQUEST R3 |
| 22 | CIBA & Vault Test Simulator | Deterministic in-memory simulation for offline test execution | M1 | Survey |
| 23 | End-to-End Fill Orchestrator | Pipeline stitching Ingestion -> DOM Extraction -> Ultramarine -> CIBA Gate -> Form Filler -> Dry-Run / Submit | M3 | PROJECT_PLAN |
| 24 | FastAPI Application Backend | REST API endpoints for triggers, task status, vault management, and `/health` check | M4 | ORIGINAL_REQUEST R4 |
| 25 | SSE Live Telemetry Stream | Server-Sent Events (`/api/tasks/{id}/events`) for real-time progress updates | M4 | Survey |
| 26 | Web Dashboard UI | Dark luxury Jinja2 interface with visual 5-stage progress indicator and embedded Browserbase replay iframe | M4 | ORIGINAL_REQUEST R4 |
| 27 | Developer CLI | `slothform fill <url> [--dry-run]` terminal application with Rich tables and dry-run safety warnings | M4 | ORIGINAL_REQUEST R4 |
| 28 | Render Blueprint Deployment | `render.yaml` with Python runtime, Uvicorn start command, `/health` check, and secure env vars | M4 | ORIGINAL_REQUEST R4 |
| 29 | Comprehensive E2E Test Suite | 4-Tier test suite (Feature Coverage, Boundaries, Interactions, Real-World Scenarios) + Tier 5 Hardening | E2E / M5 | ORIGINAL_REQUEST Acceptance Criteria |

## Milestones

| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Core Identity Vault & Auth0 CIBA Security | Features 16-22: Encrypted vault (`app/core/vault.py`), sensitivity tiers (`app/models/identity_schema.py`), context policies, Auth0 CIBA client (`app/core/auth0_client.py`), RAR diff (`app/models/ciba_schema.py`), approval gatekeeper, mock simulator. Tests: `tests/test_vault.py`, `tests/test_auth0_ciba.py`, `tests/test_vault_adversarial.py`, `tests/test_ciba_adversarial.py` (84 tests passing 100%, CLEAN audit) | none | DONE |
| M2 | Browserbase Cloud Automation & Dry-Run Guard | Features 1-11: BrowserbaseService (`app/services/browserbase_service.py`), DOMExtractor (`app/services/dom_extractor.py`), FormFiller with pre-flight DOM neutralization & route aborting (`app/services/form_filler.py`), SyntheticDocumentGenerator (`app/services/document_generator.py`), dry-run safety guard, replay generation. Tests: `tests/test_browserbase.py`, `tests/test_dom_extractor.py`, `tests/test_dry_run_guard.py`, `tests/test_dry_run_adversarial.py`, `tests/test_dom_extractor_adversarial.py` (45 tests passing 100%, CLEAN audit) | none | DONE |
| M3 | Ultramarine Reasoning Engine & Fill Pipeline | Features 12-15, 23: UltramarineClient (`app/core/ultramarine_client.py`), W-8BEN domain mapper & EssaySynthesizer (`app/services/essay_synthesizer.py`), FillOrchestrator pipeline (`app/services/fill_orchestrator.py`). Tests: `tests/test_ultramarine.py`, `tests/test_w8ben.py`, `tests/test_essay_synthesis.py`, `tests/test_orchestrator.py`, `tests/test_adversarial_m3.py`, `tests/test_orchestrator_adversarial.py` (133 tests passing 100%, 331 repo tests passing, CLEAN audit) | M1, M2 (interfaces) | DONE |
| M4 | Full-Stack Web Dashboard, Developer CLI & Render | Features 24-28: FastAPI REST API, SSE live telemetry, Jinja2 dark luxury dashboard (`app/web/`), Typer/Rich CLI (`cli/`), Render Blueprint (`render.yaml`). Tests: `tests/test_api.py`, `tests/test_cli.py`, `tests/test_render_blueprint.py`, `tests/test_api_adversarial.py`, `tests/test_cli_render_adversarial.py` (94 tests passing 100%, 425 repo tests passing, CLEAN audit) | M3 (interfaces) | DONE |
| M5 | Final Milestone: 100% E2E Test Pass & Coverage Hardening | Feature 29: Complete E2E test suite (Tiers 1-4, 69 tests) + Tier 5 Adversarial Coverage Hardening (60 tests in `test_tier5_adversarial_security.py` & `test_tier5_adversarial_pipeline.py`). Remediated SSE disconnect queue leaks & empty plan fallback. Tests: 485 tests passing 100% across entire repo, CLEAN audit. | M1, M2, M3, M4, TEST_READY.md | DONE |

## Interface Contracts

### 1. Vault & Security ↔ Orchestrator (`app/core/vault.py` & `app/core/auth0_client.py`)
- `VaultManager.get_profile(context: FormContext) -> MasterIdentityProfile`
- `VaultManager.save_profile(profile: MasterIdentityProfile) -> None`
- `Auth0CIBAClient.initiate_consent(target_url: str, diff: FormFillDiff, dry_run: bool) -> CIBARequest`
- `Auth0CIBAClient.poll_consent(auth_req_id: str, timeout: int = 300) -> ConsentResult`
  - `ConsentResult.approved: bool`
  - `ConsentResult.access_token: Optional[str]`
  - `ConsentResult.error: Optional[str]` (raises `RefusalToSubmitError` on rejection/timeout)

### 2. Browserbase Automation ↔ Orchestrator (`app/services/browserbase_service.py`, `dom_extractor.py`, `form_filler.py`)
- `BrowserbaseService.create_session(proxies: bool = True, solve_captchas: bool = True) -> BrowserbaseSession`
- `BrowserbaseService.release_session(session_id: str) -> None`
- `BrowserbaseService.get_replay_url(session_id: str) -> str`
- `DOMExtractor.extract_schema(page: Page) -> FormSchema`
- `FormFiller.fill(page: Page, fill_plan: FillPlan, dry_run: bool) -> FillResult`
  - When `dry_run=True`: Outlines submit button in amber `#f59e0b`, captures screenshot, halts before click.
  - When `dry_run=False`: Clicks submit button and waits for confirmation.

### 3. Ultramarine Reasoning Engine ↔ Orchestrator (`app/core/ultramarine_client.py`, `app/services/essay_synthesizer.py`)
- `UltramarineClient.generate_fill_plan(dom_schema: FormSchema, user_profile: MasterIdentityProfile, session_id: Optional[str]) -> FillPlan`
- `W8BENResolver.resolve_tax_fields(dom_schema: FormSchema, tax_profile: TaxProfile) -> List[FillPlanItem]`
  - Line 6a: maps Indian PAN
  - Line 6b: `action: "uncheck"` / `value: "false"`
  - Line 8: formatted `MM-DD-YYYY`
  - Line 10: Article 12(2) at 15%
- `EssaySynthesizer.synthesize_essay(prompt: str, career_profile: CareerProfile, max_words: int = 250) -> str`

### 4. Fill Orchestrator ↔ Web API & CLI (`app/services/fill_orchestrator.py`)
- `FillOrchestrator.run(target_url: str, dry_run: bool = True, progress_callback: Optional[Callable[[str, int], None]] = None) -> FillResult`

## Code Layout
```
slothform/
├── README.md                      # Overview, badge matrix, quickstart
├── PROJECT.md                     # Global project index, architecture & milestones
├── TEST_INFRA.md                  # E2E test suite index and methodology
├── render.yaml                    # Render Blueprint deployment definition
├── requirements.txt               # Pinned Python dependencies
├── .env.example                   # Environment variable template
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI entrypoint, REST API & SSE streaming
│   ├── config.py                  # Pydantic Settings & environment validation
│   ├── models/
│   │   ├── __init__.py
│   │   ├── browser_schema.py      # FormField, FormSchema, FillPlan, FillResult
│   │   ├── identity_schema.py     # MasterIdentityProfile, SensitivityTier, FormContext
│   │   └── ciba_schema.py         # CIBARequest, ConsentResult, RAR Diff
│   ├── core/
│   │   ├── __init__.py
│   │   ├── vault.py               # AES-256-GCM encrypted local store & policy engine
│   │   ├── auth0_client.py        # Auth0 CIBA flow & Token Vault integration
│   │   └── ultramarine_client.py  # Paper Instruments Ultramarine client & fallback
│   ├── services/
│   │   ├── __init__.py
│   │   ├── browserbase_service.py # Browserbase cloud session orchestrator
│   │   ├── dom_extractor.py       # In-page JS schema extractor
│   │   ├── form_filler.py         # Playwright form filler & dry-run guard
│   │   ├── essay_synthesizer.py   # Anti-hallucination essay & W-8BEN resolver
│   │   ├── document_generator.py  # Synthetic PDF resume & tax document generator
│   │   └── fill_orchestrator.py   # End-to-end execution pipeline
│   └── web/
│       ├── static/                # CSS/JS dashboard assets
│       └── templates/             # Jinja2 templates (index.html, history.html)
├── cli/
│   ├── __init__.py
│   └── main.py                    # Typer & Rich developer CLI (`slothform fill <url>`)
└── tests/
    ├── __init__.py
    ├── test_vault.py              # Vault encryption & classification tests
    ├── test_auth0_ciba.py         # CIBA approval gate & refusal tests
    ├── test_browserbase.py        # Browserbase session lifecycle tests
    ├── test_dom_extractor.py      # DOM schema extraction tests
    ├── test_dry_run_guard.py      # Safety verification tests
    ├── test_ultramarine.py        # Reasoning & fill plan tests
    ├── test_w8ben.py              # W-8BEN tax treaty mapping tests
    ├── test_essay_synthesis.py    # Anti-hallucination essay tests
    ├── test_api.py                # FastAPI endpoints & health checks
    ├── test_cli.py                # CLI commands & flags tests
    └── e2e/                       # E2E Testing Track test cases (Tiers 1-4)
```
