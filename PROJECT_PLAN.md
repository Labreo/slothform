# SlothForm — Production Blueprint & Execution Plan

## 1. Executive Summary

**SlothForm** is an autonomous, privacy-preserving form-filling agent built for **Hacktoberfest Open-Source AI Challenge: Week 3 ("Slow and Steady")**.

### The Core Problem
Applying to modern engineering jobs and onboarding as an international contractor is rife with cognitive toil:
- ATS platforms (Greenhouse, Lever, Ashby, Screenloop) feature 10+ page forms with 5–8 custom essay prompts.
- Contractor compliance forms (W-8BEN, Wise/Stripe recipient fields) involve tricky tax questions (e.g. DTAA Article 12(2) for 15% Indian treaty rate vs 30% IRS default withholding).
- Manually re-typing this information takes 25–45 minutes per form, causing developer burnout.

### The SlothForm Solution
SlothForm automates this entire loop while keeping identity data strictly protected:
1. **Target Ingestion**: Point SlothForm at any job board or onboarding link.
2. **Stealth Cloud Browsing**: **Browserbase** boots a remote Chromium sandbox, bypasses bot detection, and maps the DOM inputs.
3. **Domain Reasoning**: **Ultramarine 1 Flash** (Paper Instruments) reconciles the form inputs against the user's verified career and tax profile, drafting truthful, tailored essay responses.
4. **Human-in-the-Loop Consent**: **Auth0 for AI Agents** safeguards the identity vault and executes an asynchronous **Backchannel Authentication (CIBA)** prompt to the user's mobile device with a diff.
5. **Execution & Audit Replay**: Upon one-tap user approval, Browserbase types the fields and produces a verifiable session replay recording.

---

## 2. DEV.to Winning Strategy & Editorial Playbook

Based on our analysis of past DEV Hacktoberfest challenge winners:
1. **Relatable, Visceral Narrative**:
   - Past winners won because they anchored their projects in personal, real-world friction.
   - Proposed Article Title:
     > *"SlothForm: How I Automated 14 Greenhouse Forms and W-8BEN Tax Compliance with Open AI, Browserbase, and a 1-Tap Phone Approval"*
2. **The "Lazy Payoff" Metric**:
   - Week 3 explicitly rewards empirical proof of laziness:
     > *"14 forms filled this week. Average manual time: 28 minutes. SlothForm execution time: 42 seconds + 5 seconds to review the diff on my phone. Total saved: 6.4 hours."*
3. **Why Open Innovation Matters**:
   - Closed LLM APIs leak sensitive tax IDs (PAN/SSN), home addresses, and bank details.
   - SlothForm's architecture guarantees that sensitive identity attributes never leave the user's controlled perimeter without cryptographic scoped authorization.
4. **Interactive Artifacts for Judges**:
   - Direct embedded **Browserbase Session Replays** (judges can watch the browser fill out the form in real time).
   - Render live demo dashboard URL.
   - Clear architectural diagram rendered via Mermaid.

---

## 3. Sponsor Category Matrix & Bounty Alignment

| Sponsor | Category | Bounty | Technical Integration |
| :--- | :--- | :---: | :--- |
| **Browserbase** | *Best Use of Browserbase* 🆕 | $100 | Cloud headless browser execution via `@browserbasehq/stagehand` / Python SDK; handles anti-bot, extracts dynamic DOM, triggers input events, outputs session replay URL. |
| **Auth0** | *Best Use of Auth0 for AI Agents* 🆕 | $100 | Client-Initiated Backchannel Authentication (CIBA) flow + Token Vault for scoped identity credential retrieval and Human-in-the-Loop approval gate. |
| **Paper Instruments** | *Best Use of Ultramarine* 🆕 | $100 | Native API client for Ultramarine 1 Flash reasoning over unstructured job prompts, essay synthesis, and W-8BEN legal mapping. |
| **Render** | *Best Use of Render* (Featured) | $200 | Full-stack deployment via `render.yaml` with managed environment variables and auto-deploy. |
| **Potential Total** | **4 Target Categories** | **$500+** | Plus eligibility for the **$250 Overall Winner** prize. |

---

## 4. Technical Architecture & Component Design

```
slothform/
├── README.md                      # Overview, badge matrix, quickstart
├── PROJECT_PLAN.md                # This comprehensive plan
├── render.yaml                    # Render Blueprint deployment definition
├── requirements.txt               # Python dependencies
├── .env.example                   # Environment variable template
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI entrypoint & REST API
│   ├── config.py                  # Pydantic Settings & environment validation
│   ├── core/
│   │   ├── vault.py               # Local encrypted identity & resume store
│   │   ├── auth0_client.py        # Auth0 CIBA flow & Token Vault integration
│   │   └── ultramarine_client.py  # Paper Instruments Ultramarine client
│   ├── services/
│   │   ├── browserbase_service.py # Browserbase cloud session orchestrator
│   │   ├── dom_parser.py          # Form field schema extraction
│   │   └── fill_orchestrator.py   # End-to-end execution pipeline
│   └── web/
│       ├── static/                # CSS/JS dashboard assets
│       └── templates/             # Jinja2 dashboard templates
├── cli/
│   ├── __init__.py
│   └── main.py                    # Developer CLI (`slothform fill <url>`)
└── tests/
    ├── test_ultramarine.py        # Reasoning & fill plan tests
    ├── test_auth0_ciba.py         # CIBA approval gate tests
    └── test_browserbase.py        # Browserbase session initialization tests
```

---

## 5. Execution Roadmap

### Phase 1: Core Engine & SDK Integrations
- [ ] Implement `UltramarineClient` connecting to Paper Instruments API.
- [ ] Implement `BrowserbaseService` with session lifecycle and DOM inspector.
- [ ] Implement `Auth0CIBAClient` with async approval polling and Token Vault decryption.

### Phase 2: Orchestration & Dry-Run Guard
- [ ] Connect `FillOrchestrator`: Ingest URL $\to$ Browserbase inspect $\to$ Ultramarine plan $\to$ Auth0 CIBA gate $\to$ Browserbase fill.
- [ ] Implement `--dry-run` safety guard to halt before the final submit button.

### Phase 3: Web Dashboard & CLI
- [ ] Build FastAPI web routes: Vault management, trigger new fill, live task progress, replay embed.
- [ ] Package Typer/Rich CLI interface for terminal power users.

### Phase 4: Production Deployment & Verification
- [ ] Validate `render.yaml` and deploy to Render.
- [ ] Execute live `--dry-run` on a sample Greenhouse job application and generate a recorded session replay.

### Phase 5: DEV Submission Article
- [ ] Write the DEV article adhering to the Hacktoberfest Week 3 template.
- [ ] Embed the live Browserbase session replay and architecture diagrams.
- [ ] Publish under `#hf26challenge` and `#devchallenge` before October 25, 2026 at 11:59 PM PDT.
