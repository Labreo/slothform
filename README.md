# SlothForm 🦥

> **The Autonomous, Privacy-Preserving Form-Filling Agent**
> Built for the **Hacktoberfest Open-Source AI Challenge: Week 3 ("Slow and Steady")**

[![Render](https://img.shields.io/badge/Render-Deployed-brightgreen)](https://render.com)
[![Browserbase](https://img.shields.io/badge/Browserbase-Headless_Cloud-blue)](https://browserbase.com)
[![Auth0](https://img.shields.io/badge/Auth0-AI_Agents_CIBA-orange)](https://auth0.com)
[![Ultramarine](https://img.shields.io/badge/Ultramarine-Paper_Instruments-purple)](https://paperinstruments.com)

---

## 🎯 The Sloth Premise

Filling out 15-page ATS job applications with 6 custom technical essay questions, or navigating tedious international contractor compliance forms (W-8BEN, Wise payment setups), is the ultimate developer chore.

**SlothForm** channels your inner sloth:
1. Point it at any job application (Greenhouse, Lever, Ashby) or contractor onboarding URL.
2. **Browserbase** launches an isolated cloud browser session, navigates past bot checks, and maps the DOM.
3. **Ultramarine 1 Flash (Paper Instruments)** reasons through your verified career ground truth, synthesizes tailored answers to custom essay questions, and maps exact tax treaty fields.
4. **Auth0 for AI Agents** protects your identity vault and executes an asynchronous **Human-in-the-Loop (CIBA)** consent check—sending a push approval with a clean diff to your device.
5. You tap **"Approve"**, and SlothForm completes the submission while you relax.

---

## 🏗️ Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│                              SLOTHFORM                                 │
│         The Autonomous Contractor Onboarding & Form-Filling Agent      │
└────────────────────────────────────────────────────────────────────────┘
          │                                                │
          ▼                                                ▼
  [1. Auth0 for AI Agents]                      [2. Browserbase]
  • User authenticates identity vault           • Headless cloud browser
  • Scoped delegation token                     • Bypasses bot detection & captchas
  • Granular field-level consent                • Inspects live DOM & triggers clicks
  (e.g., allow PAN for W-8BEN, block SSN)       • Generates session replay WebP
          │                                                │
          └───────────────────────┬────────────────────────┘
                                  ▼
                    [3. Ultramarine 1 Flash]
                      (Paper Instruments)
                    • Specialized agentic reasoning
                    • Ingests live DOM + verified profile
                    • Resolves tricky tax/job logic
                    • Maps 6a (PAN) vs 6b (30% penalty)
                    • Emits deterministic fill plan
                                  │
                                  ▼
                    [4. Render + OpenTelemetry]
                    • Hosted on Render (Featured $200)
                    • Traced with OTel / Sentry spans
```

---

## 🚀 Key Features

* **Cloud Headless Execution**: Powered by Browserbase for remote Chromium automation, stealth CAPTCHA evasion, and shareable session replays.
* **Specialized Document Reasoning**: Native Paper Instruments Ultramarine client generates high-fidelity form payloads without hallucinating.
* **Human-in-the-Loop Security**: Auth0 CIBA protocol enforces one-tap authorization before any final dispatch.
* **Live Dry-Run Mode**: Safely test and preview live forms without submitting unintended applications.
* **Multi-Interface**: Responsive FastAPI web dashboard + developer CLI (`slothform fill <url>`).

---

## 🛠️ Quickstart

### 1. Prerequisites
* Python 3.11+
* Node.js 18+ (for frontend assets)

### 2. Setup
```bash
git clone https://github.com/Labreo/slothform.git
cd slothform
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### 3. Configure Credentials
Fill in `.env` with your API keys (see `.env.example`).

### 4. Run Locally
```bash
# Start backend server & dashboard
python -m uvicorn app.main:app --reload --port 8000

# Or run via CLI in dry-run mode:
python -m cli.main fill "https://boards.greenhouse.io/example/jobs/12345" --dry-run
```
