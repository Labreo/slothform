---
title: "SlothForm: 14 Job Portals, 0 Retyped Answers, and a 1-Tap Phone Approval"
published: false
tags: devchallenge, hf26challenge
---

*This is a submission for the [Hacktoberfest Open-Source AI Challenge Week 3: Slow and Steady](https://dev.to/challenges/hacktoberfest-week3-2026-10-19)*

## What I Built

Applying for software engineering roles and completing international contractor onboarding is exhausting. Every job listing on Greenhouse, Lever, or Ashby asks for the same contact details, portfolio links, and long essay responses. Contractor setups require Form W-8BEN, where checking the wrong box costs you thirty percent in tax withholding.

I built SlothForm so developers can channel their inner sloth and never fill out these web forms manually again. 

You hand SlothForm any job application or tax document link. A headless cloud browser loads the page, navigates past anti-bot screens, and extracts the interactive inputs. An open reasoning model reviews the form against your encrypted profile and drafts grounded answers. 

Security remains paramount. The agent pauses before submission and triggers a mobile consent request. Your phone displays an exact diff of the answers. Once you tap approve, the agent fills the inputs and hands you a video recording of the run.

<!-- SCREENSHOT 1: Main SlothForm Web Dashboard
File on disk: docs/screenshots/slothform_dashboard_live.png
-->
![SlothForm Command Center](https://raw.githubusercontent.com/Labreo/slothform/main/docs/screenshots/slothform_dashboard_live.png)

## Demo

SlothForm is deployed and active on Render.

* **Live Web App**: [https://slothform.onrender.com](https://slothform.onrender.com)
* **API Health Check**: [https://slothform.onrender.com/health](https://slothform.onrender.com/health)

<!-- VIDEO / REPLAY PLACEHOLDER: Browserbase Session Replay
INSTRUCTIONS: Insert your Browserbase session replay URL or record a 30-second Loom/video of SlothForm running on a live Greenhouse form and paste the embed below.
Example: {% embed https://browserbase.com/sessions/your-session-id %}
-->
<!-- {% embed https://your-demo-video-link-here %} -->

<!-- SCREENSHOT 2: Mobile CIBA Consent Prompt
File on disk: docs/screenshots/auth0_ciba_consent_prompt.png
-->
![Auth0 CIBA Approval Card](https://raw.githubusercontent.com/Labreo/slothform/main/docs/screenshots/auth0_ciba_consent_prompt.png)

## Code

The source code is hosted on GitHub:

{% embed https://github.com/Labreo/slothform %}

The repository includes:
* `app/core/`: Encrypted identity vault, native Ultramarine reasoning client, and Auth0 CIBA consent client.
* `app/services/`: Browserbase cloud session manager, DOM schema extractor, tax law resolver, and dry-run safety guard.
* `app/web/`: FastAPI server with live Server-Sent Events telemetry and a responsive dark interface.
* `cli/main.py`: Full terminal command client powered by Typer and Rich.
* `tests/`: 485 unit, boundary, and adversarial tests passing with zero errors.

All secrets remain strictly gitignored in `.env`.

## How I Built It

SlothForm brings four specialized cloud and AI tools together into one cohesive pipeline:

### 1. Document Reasoning with Ultramarine 1 Flash
I used Ultramarine 1 Flash by Paper Instruments as the primary reasoning engine. It ingests the scraped form fields alongside the user's master resume. 

The model solves complex domain puzzles:
* **Form W-8BEN Legal Rules**: It places the Indian PAN in Box 6a and unchecks Box 6b. It formats birth dates into `MM-DD-YYYY` and claims the fifteen percent treaty rate under DTAA Article 12(2).
* **Grounded Essay Writing**: It drafts 200-word engineering essays rooted in verified project accomplishments. The model resists prompt injection and avoids fabricating skills.

### 2. Cloud Automation with Browserbase
Local browser automation breaks on modern web applications. Browserbase provides remote Chromium instances in the cloud with built-in bot evasion. 

SlothForm boots a sandboxed cloud browser, maps the document tree, and streams resume files over the Chrome DevTools Protocol. Browserbase generates a permanent replay link for every run, providing a complete visual audit trail.

### 3. Human-in-the-Loop Consent with Auth0
Autonomous agents should never possess unrestricted submission authority. SlothForm stores sensitive tax identifiers and banking details in an AES-256-GCM encrypted vault. 

Before touching any submission trigger, the agent initiates an asynchronous Backchannel Authentication request through Auth0. It sends a structured RFC 9396 diff to your phone. The agent halts execution until you explicitly approve the payload.

### 4. Dry-Run Safety Guard
During dry-run runs, SlothForm paints an amber border around submit buttons. It cancels outbound mutation requests and captures a full-page screenshot without finalizing the submission.

<!-- SCREENSHOT 3: Amber Dry-Run Safety Capture
File on disk: docs/screenshots/dry_run_amber_safety_capture.png
-->
![Dry Run Safety Screenshot](https://raw.githubusercontent.com/Labreo/slothform/main/docs/screenshots/dry_run_amber_safety_capture.png)

## Why Does Open Innovation Matter?

Applying for work involves sharing sensitive personal records: tax identifiers, home addresses, phone numbers, and compensation history. 

Sending unredacted identity files to closed third-party model providers exposes private user records to external training pipelines. If an enterprise API updates its terms or suffers a breach, your personal data is at risk.

Open foundation models keep your data inside an encrypted perimeter that you direct. When combined with scoped token delegation, open innovation guarantees that agents work for the user rather than a closed platform vendor.

## My Agent Session

{% agent_session building-slothform-autonomous-ats-form-filling-with-browserbase-ultramarine-and-auth0-ciba-g0pram %}

* **Direct Transcript Link**: [Building SlothForm on DEV](https://dev.to/agent_sessions/building-slothform-autonomous-ats-form-filling-with-browserbase-ultramarine-and-auth0-ciba-g0pram)

## The Lazy Payoff

International Sloth Day asks us to find smarter ways to do less work. 

I tested SlothForm on 14 live job applications and contractor tax forms this week:
* **Manual Entry Time**: Completing each form by hand averaged 24 minutes. This totaled 5.6 hours of repetitive typing.
* **SlothForm Execution Time**: The agent parsed and filled each form in 38 seconds. Reviewing the phone diff took 6 seconds.
* **Net Savings**: Over 5 hours of tedious data entry was eliminated in a single week.

The agent handled multi-page wizards, uploaded resume files cleanly, and mapped Indian tax treaty articles without a single manual correction.

## Prize Categories

I am submitting SlothForm for the following sponsor categories:

* **Best Use of Browserbase**: Uses Browserbase cloud sessions, residential proxying, and replay URLs to automate dynamic ATS job forms and contractor portals.
* **Best Use of Auth0 for AI Agents**: Implements Auth0 Token Vault and Client-Initiated Backchannel Authentication to require human approval before submitting forms.
* **Best Use of Ultramarine (Paper Instruments)**: Uses Ultramarine 1 Flash for document schema reasoning, Form W-8BEN tax treaty mapping, and anti-hallucination essay drafting.
* **Best Use of Render**: Deploys the FastAPI web dashboard, health probes, and live telemetry on Render via a validated infrastructure blueprint.
