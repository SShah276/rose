# ROSE — Recruiting OS

A self-hosted job search command center built for one user. Aggregates job listings, scores them against your preferences, generates AI-tailored cover letters and outreach, and orchestrates a daily recruiting plan — all from a local FastAPI server you own and control.

---

## Problem

Job boards are passive. You have to check them manually, re-enter the same information for every application, and keep a separate spreadsheet to track status. Outreach to recruiters is ad-hoc and easy to forget.

ROSE closes that loop: it fetches listings automatically, scores and ranks them against your profile, drafts cover letters from your template, finds recruiter contacts, and gives you a prioritized daily action plan — all in one place, with no third-party cloud storage of your resume or job history.

---

## Architecture

```
Browser (Jinja2 templates)
        │
        ▼
FastAPI  (app/main.py)          ← single-file route layer
   ├── Scoring   (app/scoring.py)
   ├── AI layer  (app/ai.py)    ← Anthropic Claude API
   ├── Agents    (app/agents/)  ← discovery · evaluation · outreach · contact finder
   ├── Sources   (app/sources/) ← GitHub job list scrapers · ATS board APIs · CSV import
   ├── PDF       (app/pdf.py)   ← cover letter → downloadable PDF (fpdf2)
   └── DB        (app/db.py)    ← SQLite via sqlite3
        │
        ▼
jobs.db  (SQLite, local file)
```

**Auth:** Single-user password login via `starlette.middleware.sessions.SessionMiddleware` (signed cookies, 30-day sessions). All routes are gated by `_AuthMiddleware`. No user accounts or registration.

**Secrets:** All API keys and the session signing key live in `.env`, never in the database or source code.

---

## Data Model

| Table | Purpose |
|---|---|
| `jobs` | Raw listing: company, title, location, salary, URL, source, date_found, date_posted |
| `applications` | Per-job status + dates (applied, follow-up), notes, resume used |
| `contacts` | Recruiter/hiring manager: name, email, LinkedIn, company |
| `job_contacts` | Many-to-many join: contacts linked to jobs, with outreach status |
| `ai_outputs` | Cached AI text per job × output type (analysis, cover_letter, outreach) |
| `plans` | Daily recruiting plan snapshots with agent trace data |
| `plan_items` | Individual plan action items with user feedback (useful / not useful / done) |
| `settings` | Key–value store for score weights and cover letter template |
| `profile` | Single-row user profile (name, location, skills, experience) |

Deduplication: jobs are keyed by `dedupe_key` (company + title + location hash). Contacts are deduplicated by `linkedin_url` or email.

---

## Agent Workflow

The **Generate Today's Plan** button kicks off three sequential agents streamed via Server-Sent Events:

```
1. Discovery Agent
   Input:  Top-ranked unreviewed jobs from the DB
   Output: Which jobs to prioritize today and why

2. Evaluation Agent
   Input:  Discovery output + full job details + user profile
   Output: Scored recommendations (Apply / Save / Skip) with reasoning

3. Outreach Agent
   Input:  Applied jobs with no recruiter contact yet
   Output: Prioritized outreach queue with message drafts

→ Plan saved to DB, displayed on jobs dashboard with feedback buttons
```

AI outputs (cover letters, job analysis, outreach messages) are cached in `ai_outputs` and only regenerated when requested. Plan items collect thumbs-up / thumbs-down feedback that's stored for future model improvement.

**Contact finder:**
- **LinkedIn path:** DuckDuckGo `site:linkedin.com/in` search → filters for recruiter-keyword titles → returns up to 8 profiles
- **Hunter.io path:** Claude Haiku infers the company domain → Hunter.io `/domain-search` → filters recruiting contacts by department/position keywords

---

## Key Features

- **Job board:** Aggregates listings from SimplifyJobs, New Grad, SpeedyApply and Intern List job-list scrapers, plus per-company Greenhouse and Lever board APIs (see `app/sources/ats.py` for the company registry) and CSV import. Scored and ranked by role fit, location, compensation, and freshness using configurable weights.
- **AI analysis:** Per-job fit score, strengths/weaknesses, and tailored application notes via Claude.
- **Cover letter:** Adapts your template to each company. Outputs a formatted, downloadable PDF (fpdf2 with Unicode support via Windows Arial TTF).
- **Recruiter search:** LinkedIn search (DuckDuckGo) + Hunter.io email lookup, deduplicated and stored.
- **Outreach drafting:** AI-generated personalized outreach emails with approve/edit workflow before sending.
- **Tracker:** Full application pipeline (Not Applied → Interested → Saved → Applied → Interview → Offer).
- **Analytics:** Historical charts of applications, interviews, and pipeline conversion.
- **Auth:** Password-protected; all routes require a session cookie. Single `.env` file controls all secrets.

---

## Tradeoffs

| Decision | Rationale |
|---|---|
| SQLite over Postgres | Zero infrastructure — runs on any machine, state is one file, trivial to back up |
| Single-user auth (no accounts) | It's a personal tool; OAuth or multi-user would add complexity for no benefit |
| Jinja2 server-side templates over React | Faster to build, no build step, full control over HTML for PDF output |
| DuckDuckGo for LinkedIn search | Free, no OAuth, no API key — but rate-limited and returns profiles not emails |
| fpdf2 over WeasyPrint/Playwright | Lightweight, pure Python, no browser dependency — tradeoff is manual layout |
| Claude Haiku for domain inference | Fast and cheap for a one-shot lookup; Sonnet/Opus only for analysis and writing |
| Plan feedback stored but not yet used for reranking | Correct data collection pattern; fine-tuning loop is future work |

---

## Setup

```bash
python -m venv .venv
.venv/Scripts/activate        # Windows
pip install -r requirements.txt

# Create .env (see .env.example)
cp .env.example .env
# Fill in: ANTHROPIC_API_KEY, SECRET_KEY, APP_PASSWORD

uvicorn app.main:app --reload
# → http://localhost:8000
```

---

## Future Work

- **Email send:** Gmail compose integration — generate outreach in ROSE, click to open pre-filled Gmail compose window (`mailto:` or Gmail API with OAuth). Human-approved before sending.
- **Plan feedback loop:** Use thumbs-up/down data to tune scoring weights automatically.
- **Resume parsing:** Upload a PDF resume and auto-populate the profile + skills fields.
- **Job alerts:** Watch for new high-score listings and surface them without a manual fetch.
- **Deployment:** Fly.io or Cloudflare Tunnel for access outside localhost while keeping data private.
