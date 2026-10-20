# Original User Request

## 2026-10-20T11:26:31Z

SlothForm is an autonomous, privacy-preserving form-filling agent that pairs Paper Instruments Ultramarine document reasoning with Browserbase cloud headless browser automation and Auth0 for AI Agents (CIBA Human-in-the-Loop authorization) to eliminate repetitive tech job applications (Greenhouse, Lever, Ashby) and international contractor onboarding forms (W-8BEN, payment recipient profiles).

Working directory: /Users/sanjaywaradkar/learning/hackathons/slothform
Integrity mode: development

Note on Production Standard:
This must be a real, functioning end-to-end implementation with no fake mocks or hollow stubs. Code must execute against live endpoints and real dynamic forms via Browserbase with a pre-submission `--dry-run` safety guard. The private git repository is linked at `https://github.com/Labreo/slothform` with full `.gitignore` enforcement.

## Requirements

### R1. Target Form Ingestion & Browserbase Cloud Automation
The agent must accept target form URLs (ATS job applications and contractor onboarding/tax forms), navigate via Browserbase headless cloud browser with stealth bot bypass, extract the interactive DOM schema (inputs, selects, textareas, file uploads), fill the validated payload, and produce a verifiable session replay URL.

### R2. Strict Ultramarine Document Reasoning Engine
The agent must evaluate the extracted form schema against the user's verified identity vault using the Paper Instruments Ultramarine model via its native API client. It must map profile fields, synthesize contextual essay responses grounded in the user's master career truth, resolve domain logic (e.g. W-8BEN tax treaty lines vs Indian PAN), and emit a structured, typed fill plan.

### R3. Auth0 for AI Agents Identity Vault & CIBA Human-in-the-Loop Consent
The agent must store sensitive identity attributes (PAN, tax status, banking, address, resume) in a secured vault protected by Auth0 Token Vault. Before applying or submitting any form, the agent must trigger an asynchronous Backchannel Authentication (CIBA) request to the user's registered device with a diff of proposed answers; execution is halted until the user explicitly grants approval.

### R4. Full-Stack Web Dashboard & Developer CLI
The project must provide a FastAPI backend and responsive web interface deployed on Render alongside a developer CLI (`slothform fill <url>`). The interface allows managing vault data, submitting target URLs, monitoring live fills, viewing embedded Browserbase session replays, and inspecting audit logs.

### R5. Live Verification with Dry-Run Safety Guard
The agent must support a mandatory `--dry-run` flag that navigates real live target forms, completes DOM filling, captures screenshots and session replays, and cleanly halts right before the final submission action.

## Acceptance Criteria

### Browser & Automation Execution
- [ ] Browserbase cloud session successfully navigates to a live job board (e.g. Greenhouse/Lever) and extracts all input field selectors and labels.
- [ ] Browserbase fills text fields, selects options, and simulates file uploads in the remote cloud session.
- [ ] The agent retrieves and outputs a playable Browserbase session replay URL (`https://browserbase.com/sessions/...`).

### Reasoning & Model Synthesis
- [ ] The Ultramarine client ingests the DOM schema + user profile and generates a validated JSON fill plan adhering to the target schema.
- [ ] Custom essay prompts are answered with high-relevance technical detail without hallucinating experience.
- [ ] W-8BEN tax fields correctly map Indian PAN to Box 6a, omit Box 6b, and format birthdates into `MM-DD-YYYY`.

### Identity, Security & Approvals
- [ ] Identity vault stores encrypted user credentials and profile metadata.
- [ ] The Auth0 CIBA flow triggers an approval poll/webhook; the agent refuses to submit if unapproved or rejected.
- [ ] User approval unlocks the final dispatch action.

### Safety & Deployment
- [ ] Running with `--dry-run` against a live target completes all form fills and stops safely before triggering submission buttons.
- [ ] FastAPI backend serves the dashboard, provides REST endpoints for triggers, and exposes health checks.
- [ ] A valid `render.yaml` blueprint is present for one-click deployment to Render.
