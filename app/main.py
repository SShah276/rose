import hmac
import os
from datetime import date, timedelta

from dotenv import load_dotenv
load_dotenv()

import json as _json

from fastapi import FastAPI, Request, UploadFile, File
from fastapi.responses import RedirectResponse, StreamingResponse, Response
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

import time as _time

_SECRET_KEY  = os.environ.get("SECRET_KEY", "")
_APP_PASSWORD = os.environ.get("APP_PASSWORD", "")

from app.db import (
    init_db, get_all_jobs, get_visible_jobs, get_hidden_jobs,
    has_unscored_jobs, bulk_update_scores,
    update_application, get_followups_due, get_tracked_applications, get_stats,
    get_setting, set_setting, upsert_job, set_job_salary,
    reset_all_statuses, restore_skipped,
    get_profile, save_profile,
    get_ai_outputs, upsert_ai_output, save_ai_output_content, toggle_ai_output_approved,
    get_contact,
    get_contacts_for_job, upsert_contact_by_email, upsert_contact_by_linkedin,
    link_contact_to_job, unlink_contact_from_job, get_job_contact, update_job_contact,
    get_outreach_queue,
    get_uncontacted_job_contacts, set_plan_cache,
    create_plan, add_plan_items, get_today_plan, set_plan_item_feedback,
    get_plan_history, get_plan_detail, get_analytics_data,
)
from app.ai import (
    generate_job_analysis, generate_cover_letter, generate_outreach,
    generate_contact_outreach,
)
from app.scoring import rank_jobs
from app.ingestion import import_jobs_from_csv_bytes, normalize_job
from app.sources.github_source import GitHubSource, KNOWN_REPOS
from app.sources.intern_list_source import InternListSource
from app.sources.newgrad_jobs_source import NewGradJobsSource
import urllib.request

app = FastAPI()
templates = Jinja2Templates(directory="app/templates")

# ── Auth middleware (runs after SessionMiddleware populates request.session) ──
class _AuthMiddleware(BaseHTTPMiddleware):
    _PUBLIC = frozenset({"/login"})

    async def dispatch(self, request: Request, call_next):
        if request.url.path in self._PUBLIC:
            return await call_next(request)
        if not request.session.get("authenticated"):
            return RedirectResponse(url=f"/login?next={request.url.path}", status_code=303)
        return await call_next(request)

# Order matters: last add_middleware call = outermost = runs first
app.add_middleware(_AuthMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=_SECRET_KEY or "dev-only-change-me",
    max_age=86400 * 30,   # 30-day session
    same_site="lax",
    https_only=False,
)


@app.on_event("startup")
def startup():
    init_db()
    missing = [k for k in ("SECRET_KEY", "APP_PASSWORD", "ANTHROPIC_API_KEY") if not os.environ.get(k)]
    if missing:
        import warnings
        warnings.warn(f"⚠  Missing env vars: {', '.join(missing)}", stacklevel=1)


# ── Login / logout ──
@app.get("/login")
def login_page(request: Request, next: str = "/jobs"):
    if request.session.get("authenticated"):
        return RedirectResponse(url=next, status_code=303)
    return templates.TemplateResponse(request=request, name="login.html", context={"next": next})


@app.post("/login")
async def login_post(request: Request):
    form = await request.form()
    password  = str(form.get("password", ""))
    next_url  = str(form.get("next", "/jobs"))
    if _APP_PASSWORD and hmac.compare_digest(password.encode(), _APP_PASSWORD.encode()):
        request.session["authenticated"] = True
        return RedirectResponse(url=next_url, status_code=303)
    return templates.TemplateResponse(
        request=request, name="login.html",
        context={"error": "Incorrect password.", "next": next_url},
        status_code=401,
    )


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


@app.get("/")
def root():
    return RedirectResponse(url="/jobs")


# ---------- helpers ----------

def _build_daily_plan(ranked_jobs: list) -> list:
    plan = []
    today = date.today()
    for job in ranked_jobs:
        if len(plan) >= 8:
            break
        status = job.get("status") or "not_applied"

        if status in ("not_applied", "not_reviewed", "interested") and job.get("final_score", 0) >= 75:
            plan.append({
                "action": "Apply",
                "job_id": job["id"],
                "label": f"{job['company']} — {job['title']}",
                "reason": f"Score {job['final_score']}",
            })

        elif status == "applied" and job.get("date_applied"):
            try:
                days = (today - date.fromisoformat(job["date_applied"])).days
                if days >= 7:
                    plan.append({
                        "action": "Follow Up",
                        "job_id": job["id"],
                        "label": f"{job['company']} — {job['title']}",
                        "reason": f"Applied {days} days ago — no response yet",
                    })
            except ValueError:
                pass

        elif status == "saved" and job.get("date_posted"):
            try:
                if (today - date.fromisoformat(job["date_posted"])).days <= 7:
                    plan.append({
                        "action": "Review",
                        "job_id": job["id"],
                        "label": f"{job['company']} — {job['title']}",
                        "reason": "Saved role — posting is still fresh",
                    })
            except ValueError:
                pass

    return plan


# ---------- jobs dashboard ----------

@app.get("/jobs")
def jobs_page(request: Request):
    _RENDER_LIMIT = 150

    # Recompute and persist scores if any job is missing one (first run or new import)
    if has_unscored_jobs():
        ranked_all = rank_jobs(get_all_jobs())
        bulk_update_scores([(j["id"], j["final_score"]) for j in ranked_all])

    # Fast DB fetch — pre-sorted, pre-filtered, capped at render limit
    visible, total_visible = get_visible_jobs(limit=_RENDER_LIMIT)

    # Closed/skipped section — usually tiny, no cap needed
    hidden = get_hidden_jobs()

    # Use AI-generated plan from DB if generated today, else fall back to rule-based
    plan_db, plan_items = get_today_plan()
    if plan_db:
        plan      = plan_items
        plan_meta = {
            "source":          plan_db["source"],
            "generated_at":    plan_db["date"],
            "discovery_count": plan_db["discovery_count"],
            "error":           plan_db["error"],
            "plan_id":         plan_db["id"],
        }
    else:
        plan      = _build_daily_plan(visible)
        plan_meta = {"source": "rules"}

    return templates.TemplateResponse(
        request=request,
        name="jobs.html",
        context={
            "jobs":          visible,
            "hidden_jobs":   hidden,
            "total_visible": total_visible,
            "render_limit":  _RENDER_LIMIT,
            "plan":          plan,
            "plan_meta":     plan_meta,
            "followups":     get_followups_due(),
            "stats":         get_stats(),
        }
    )


@app.get("/plan/progress")
def plan_progress(request: Request):
    return templates.TemplateResponse(request=request, name="progress.html", context={})


@app.get("/plan/stream")
def plan_stream():
    from app.agents import discovery, evaluation, outreach_agent

    def _stream():
        t0          = _time.time()
        jobs        = get_all_jobs()
        ranked_jobs = rank_jobs(jobs)
        uncontacted = get_uncontacted_job_contacts()
        profile     = get_profile()
        errors      = []
        today       = date.today()
        today_str   = str(today)

        # Compact snapshot of discovery candidates for trace storage
        disc_input = [
            {"id": j["id"], "company": j["company"], "title": j["title"],
             "score": j.get("final_score", 0), "status": j.get("status") or "not_applied"}
            for j in ranked_jobs
            if (j.get("status") or "not_applied") in ("not_applied", "not_reviewed", "interested", "saved")
        ][:20]

        # Agent 1: Discovery
        yield f"data: {_json.dumps({'step': 'discovery', 'status': 'running'})}\n\n"
        opportunities = []
        try:
            opportunities = discovery.run(ranked_jobs, profile=profile)
            yield f"data: {_json.dumps({'step': 'discovery', 'status': 'done', 'count': len(opportunities)})}\n\n"
        except Exception as e:
            errors.append(f"Discovery: {e}")
            yield f"data: {_json.dumps({'step': 'discovery', 'status': 'error'})}\n\n"

        # Agent 2: Evaluation
        yield f"data: {_json.dumps({'step': 'evaluation', 'status': 'running'})}\n\n"
        pipeline = [j for j in ranked_jobs if (j.get("status") or "not_applied") in ("interested", "saved", "applied")]
        priorities = []
        try:
            priorities = evaluation.run(opportunities, pipeline, profile=profile)
            yield f"data: {_json.dumps({'step': 'evaluation', 'status': 'done', 'count': len(priorities)})}\n\n"
        except Exception as e:
            errors.append(f"Evaluation: {e}")
            yield f"data: {_json.dumps({'step': 'evaluation', 'status': 'error'})}\n\n"

        # Agent 3: Outreach
        yield f"data: {_json.dumps({'step': 'outreach', 'status': 'running'})}\n\n"
        stale = []
        for j in ranked_jobs:
            if j.get("status") == "applied" and j.get("date_applied"):
                try:
                    days = (today - date.fromisoformat(j["date_applied"])).days
                    if days >= 7:
                        stale.append({**j, "days_since": days})
                except ValueError:
                    pass
        outreach_actions = []
        try:
            outreach_actions = outreach_agent.run(uncontacted, stale, profile=profile)
            yield f"data: {_json.dumps({'step': 'outreach', 'status': 'done', 'count': len(outreach_actions)})}\n\n"
        except Exception as e:
            errors.append(f"Outreach: {e}")
            yield f"data: {_json.dumps({'step': 'outreach', 'status': 'error'})}\n\n"

        # Merge plan items
        plan = []
        for item in priorities:
            plan.append({"action": item.get("action", "Review"), "job_id": item.get("job_id"),
                         "label": item.get("label", ""), "reason": item.get("reason", ""), "source": "agent"})
        for item in outreach_actions:
            plan.append({"action": item.get("action", "Follow Up"), "job_id": item.get("job_id"),
                         "label": item.get("label", ""), "reason": item.get("reason", ""), "source": "agent"})

        latency_ms = int((_time.time() - t0) * 1000)

        # Store in plan history tables (V7)
        plan_id = create_plan(
            date_str          = today_str,
            source            = "agent",
            discovery_count   = len(opportunities),
            error             = "; ".join(errors) if errors else None,
            latency_ms        = latency_ms,
            discovery_input   = disc_input,
            discovery_output  = opportunities,
            evaluation_output = priorities,
            outreach_output   = outreach_actions,
        )
        add_plan_items(plan_id, plan)

        # Keep legacy cache for backwards compat
        set_plan_cache({
            "plan":            plan,
            "generated_at":    today_str,
            "discovery_count": len(opportunities),
            "error":           "; ".join(errors) if errors else None,
        })

        yield f"data: {_json.dumps({'step': 'complete', 'redirect': '/jobs'})}\n\n"

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------- plan feedback + analytics + traces ----------

@app.post("/plan-items/{item_id}/feedback")
async def plan_item_feedback(item_id: int, request: Request):
    form = await request.form()
    set_plan_item_feedback(item_id, form.get("feedback", ""))
    return RedirectResponse(url="/jobs", status_code=303)


@app.get("/analytics")
def analytics_page(request: Request):
    return templates.TemplateResponse(
        request=request, name="analytics.html",
        context={"history": get_plan_history(14), "data": get_analytics_data()}
    )


@app.get("/admin/traces/{plan_id}")
def plan_trace(plan_id: int, request: Request):
    import json as _jmod
    plan, items = get_plan_detail(plan_id)
    if not plan:
        return RedirectResponse(url="/analytics", status_code=303)
    for field in ("discovery_input", "discovery_output", "evaluation_output", "outreach_output"):
        if plan.get(field):
            try:
                plan[field] = _jmod.loads(plan[field])
            except Exception:
                pass
    return templates.TemplateResponse(
        request=request, name="traces.html",
        context={"plan": plan, "items": items}
    )


# ---------- job actions ----------

@app.post("/jobs/bulk-action")
async def bulk_action(request: Request):
    form = await request.form()
    action = str(form.get("action", ""))
    ids = [int(x) for x in form.getlist("job_ids") if str(x).isdigit()]
    status_map = {"skip": "skipped", "close": "closed", "restore": "not_applied"}
    if action in status_map:
        for job_id in ids:
            update_application(job_id, status=status_map[action])
    return RedirectResponse(url="/jobs", status_code=303)


@app.post("/jobs/archive-old")
async def archive_old_jobs():
    cutoff = str(date.today() - timedelta(days=14))
    jobs = get_all_jobs()
    for j in jobs:
        status = j.get("status") or "not_applied"
        date_found = j.get("date_found") or ""
        if status in ("not_applied", "not_reviewed") and date_found and date_found < cutoff:
            update_application(j["id"], status="closed")
    return RedirectResponse(url="/jobs", status_code=303)


@app.post("/jobs/{job_id}/action")
async def job_action(job_id: int, request: Request):
    form = await request.form()
    action = form.get("action", "")
    status_map = {
        "interested": "interested",
        "skip":       "skipped",
        "save":       "saved",
        "interview":  "interview",
        "rejected":   "rejected",
        "offer":      "offer",
        "restore":    "not_applied",
        "close":      "closed",
    }
    if action == "apply":
        return RedirectResponse(url=f"/jobs/{job_id}/apply", status_code=303)
    if action in status_map:
        update_application(job_id, status=status_map[action])
    return RedirectResponse(url="/jobs", status_code=303)


@app.post("/jobs/{job_id}/set-salary")
async def set_salary(job_id: int, request: Request):
    form = await request.form()
    raw = form.get("salary", "").strip()
    from app.ingestion import parse_salary
    salary = parse_salary(raw) if raw else None
    set_job_salary(job_id, salary, pay_raw=raw)
    return RedirectResponse(url="/jobs", status_code=303)


@app.get("/jobs/{job_id}/apply")
def apply_form(job_id: int, request: Request):
    jobs = get_all_jobs()
    job = next((j for j in jobs if j["id"] == job_id), None)
    if not job:
        return RedirectResponse(url="/jobs", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="apply_form.html",
        context={"job": job, "today": str(date.today())}
    )


@app.post("/jobs/{job_id}/apply")
async def mark_applied(job_id: int, request: Request):
    form = await request.form()
    date_applied = form.get("date_applied") or str(date.today())
    try:
        follow_up_date = str(date.fromisoformat(date_applied) + timedelta(days=7))
    except ValueError:
        follow_up_date = str(date.today() + timedelta(days=7))
    update_application(
        job_id,
        status="applied",
        date_applied=date_applied,
        follow_up_date=follow_up_date,
        notes=form.get("notes", ""),
        application_url=form.get("application_url", ""),
        resume_used=form.get("resume_used", ""),
    )
    return RedirectResponse(url="/jobs", status_code=303)


# ---------- tracker ----------

@app.get("/tracker")
def tracker_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="tracker.html",
        context={
            "applications": get_tracked_applications(),
            "stats": get_stats(),
            "followups": get_followups_due(),
        }
    )


# ---------- CSV import ----------

@app.get("/import/csv")
def import_csv_form(request: Request):
    return templates.TemplateResponse(request=request, name="import_csv.html", context={})


@app.post("/import/csv")
async def import_csv(request: Request, file: UploadFile = File(...)):
    file_bytes = await file.read()
    summary = import_jobs_from_csv_bytes(file_bytes)
    return templates.TemplateResponse(
        request=request,
        name="import_result.html",
        context={"summary": summary, "filename": file.filename}
    )


# ---------- GitHub fetch ----------

@app.get("/debug/github")
def debug_github(repo: str = "simplify"):
    url = KNOWN_REPOS.get(repo)
    if not url:
        return {"error": f"Unknown repo '{repo}'"}
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            html = resp.read().decode("utf-8")
        lines = html.splitlines()
        html_table_lines = [
            {"n": i + 1, "line": line}
            for i, line in enumerate(lines)
            if any(tag in line.lower() for tag in ["<table", "<tr", "<th", "<td"])
        ]
        return {
            "url": url,
            "total_lines": len(lines),
            "html_table_line_count": len(html_table_lines),
            "first_20_html_table_lines": html_table_lines[:20],
        }
    except Exception as e:
        return {"error": str(e)}


@app.post("/fetch/github")
def fetch_github(request: Request, repo: str = "simplify"):
    source = GitHubSource(repo_key=repo)
    raw_jobs = source.fetch_jobs()

    summary = {"fetched": len(raw_jobs), "inserted": 0, "updated": 0, "skipped": 0, "errors": []}

    for raw in raw_jobs:
        try:
            job_data = normalize_job({
                "company":     raw.company,
                "title":       raw.title,
                "location":    raw.location,
                "salary":      str(raw.salary or ""),
                "pay_raw":     raw.pay_raw,
                "url":         raw.url,
                "description": raw.description,
                "date_posted": raw.date_posted,
            }, source=raw.source, job_type=raw.job_type)
            result = upsert_job(job_data)
            summary["inserted" if result == "inserted" else "updated"] += 1
        except Exception as e:
            summary["skipped"] += 1
            summary["errors"].append(str(e))

    return templates.TemplateResponse(
        request=request,
        name="import_result.html",
        context={"summary": summary, "filename": f"github/{repo}"}
    )


@app.post("/fetch/intern-list")
def fetch_intern_list(request: Request):
    source = InternListSource()
    try:
        raw_jobs = source.fetch_jobs()
    except RuntimeError as e:
        return templates.TemplateResponse(
            request=request, name="import_result.html",
            context={"summary": {"fetched": 0, "inserted": 0, "updated": 0, "skipped": 0, "errors": [str(e)]},
                     "filename": "intern-list.com"}
        )
    summary = {"fetched": len(raw_jobs), "inserted": 0, "updated": 0, "skipped": 0, "errors": []}
    for raw in raw_jobs:
        try:
            job_data = normalize_job(
                {"company": raw.company, "title": raw.title, "location": raw.location,
                 "salary": str(raw.salary or ""), "url": raw.url,
                 "description": raw.description, "date_posted": raw.date_posted},
                source=raw.source, job_type=raw.job_type,
            )
            result = upsert_job(job_data)
            summary["inserted" if result == "inserted" else "updated"] += 1
        except Exception as e:
            summary["skipped"] += 1
            summary["errors"].append(str(e))
    return templates.TemplateResponse(
        request=request, name="import_result.html",
        context={"summary": summary, "filename": "intern-list.com"}
    )


@app.post("/fetch/newgrad-jobs")
def fetch_newgrad_jobs(request: Request):
    source = NewGradJobsSource()
    try:
        raw_jobs = source.fetch_jobs()
    except RuntimeError as e:
        return templates.TemplateResponse(
            request=request, name="import_result.html",
            context={"summary": {"fetched": 0, "inserted": 0, "updated": 0, "skipped": 0, "errors": [str(e)]},
                     "filename": "newgrad-jobs.com"}
        )
    summary = {"fetched": len(raw_jobs), "inserted": 0, "updated": 0, "skipped": 0, "errors": []}
    for raw in raw_jobs:
        try:
            job_data = normalize_job(
                {"company": raw.company, "title": raw.title, "location": raw.location,
                 "salary": str(raw.salary or ""), "url": raw.url,
                 "description": raw.description, "date_posted": raw.date_posted},
                source=raw.source, job_type=raw.job_type,
            )
            result = upsert_job(job_data)
            summary["inserted" if result == "inserted" else "updated"] += 1
        except Exception as e:
            summary["skipped"] += 1
            summary["errors"].append(str(e))
    return templates.TemplateResponse(
        request=request, name="import_result.html",
        context={"summary": summary, "filename": "newgrad-jobs.com"}
    )


# ---------- settings ----------

# ---------- candidate profile ----------

@app.get("/profile")
def profile_page(request: Request):
    return templates.TemplateResponse(
        request=request, name="profile.html", context={"profile": get_profile()}
    )


@app.post("/profile")
async def save_profile_route(request: Request):
    form = await request.form()
    save_profile(dict(form))
    return RedirectResponse(url="/profile", status_code=303)


# ---------- AI assistant ----------

_AI_GENERATORS = {
    "job_analysis":  generate_job_analysis,
    "cover_letter":  generate_cover_letter,
    "outreach":      generate_outreach,
}


@app.get("/jobs/{job_id}/ai")
def job_ai_page(job_id: int, request: Request):
    jobs = get_all_jobs()
    job = next((j for j in jobs if j["id"] == job_id), None)
    if not job:
        return RedirectResponse(url="/jobs", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="job_ai.html",
        context={
            "job":          job,
            "outputs":      get_ai_outputs(job_id),
            "job_contacts": get_contacts_for_job(job_id),
            "profile_set":  bool(get_profile().get("name")),
            "today":        str(date.today()),
        }
    )


@app.post("/jobs/{job_id}/ai/generate")
async def ai_generate(job_id: int, request: Request, type: str = "job_analysis"):
    if type not in _AI_GENERATORS:
        return RedirectResponse(url=f"/jobs/{job_id}/ai", status_code=303)

    jobs = get_all_jobs()
    job = next((j for j in jobs if j["id"] == job_id), None)
    if not job:
        return RedirectResponse(url="/jobs", status_code=303)

    error = None
    try:
        profile = get_profile()
        if type == "cover_letter":
            template = get_setting("cover_letter_template") or None
            content = generate_cover_letter(job, profile, template=template)
        else:
            content = _AI_GENERATORS[type](job, profile)
        upsert_ai_output(job_id, type, content)
    except Exception as e:
        error = str(e)

    return templates.TemplateResponse(
        request=request,
        name="job_ai.html",
        context={
            "job":          job,
            "outputs":      get_ai_outputs(job_id),
            "job_contacts": get_contacts_for_job(job_id),
            "profile_set":  bool(get_profile().get("name")),
            "today":        str(date.today()),
            "error":        error,
        }
    )


@app.post("/jobs/{job_id}/ai/{output_id}/save")
async def ai_save_output(job_id: int, output_id: int, request: Request):
    form = await request.form()
    content = form.get("content", "")
    save_ai_output_content(output_id, content)
    return RedirectResponse(url=f"/jobs/{job_id}/ai", status_code=303)


@app.post("/jobs/{job_id}/ai/{output_id}/approve")
def ai_approve_output(job_id: int, output_id: int):
    toggle_ai_output_approved(output_id)
    return RedirectResponse(url=f"/jobs/{job_id}/ai", status_code=303)


@app.get("/jobs/{job_id}/cover-letter/pdf")
def cover_letter_pdf(job_id: int):
    from app.pdf import cover_letter_to_pdf
    jobs = get_all_jobs()
    job  = next((j for j in jobs if j["id"] == job_id), None)
    if not job:
        return RedirectResponse(url="/jobs", status_code=303)
    outputs = get_ai_outputs(job_id)
    cl = outputs.get("cover_letter")
    if not cl:
        return RedirectResponse(url=f"/jobs/{job_id}/ai", status_code=303)
    profile = get_profile()
    first_name = (profile.get("name") or "").split()[0] or "Shreyas"
    pdf_bytes = cover_letter_to_pdf(
        company=job["company"],
        title=job["title"],
        content=cl["content"],
        location=job.get("location") or "",
        candidate_name=first_name,
    )
    slug = job["company"].replace(" ", "_").replace("/", "_")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="CoverLetter_{slug}.pdf"'},
    )


@app.post("/jobs/{job_id}/find-recruiters/linkedin")
def find_linkedin_recruiters(job_id: int, request: Request):
    from app.agents.contact_finder import run_linkedin
    jobs = get_all_jobs()
    job  = next((j for j in jobs if j["id"] == job_id), None)
    if not job:
        return RedirectResponse(url="/jobs", status_code=303)

    result = run_linkedin(job["company"])

    if not result.get("error") and result.get("contacts"):
        for c in result["contacts"]:
            contact_id = upsert_contact_by_linkedin({
                "company":      job["company"],
                "name":         c["name"],
                "title":        c["position"],
                "email":        "",
                "linkedin_url": c["linkedin"],
                "source":       "linkedin",
                "confidence_score": 0,
            })
            link_contact_to_job(job_id, contact_id, "recruiter")

    return templates.TemplateResponse(
        request=request, name="job_ai.html",
        context={
            "job":            job,
            "outputs":        get_ai_outputs(job_id),
            "job_contacts":   get_contacts_for_job(job_id),
            "profile_set":    bool(get_profile().get("name")),
            "today":          str(date.today()),
            "linkedin_result": result,
        }
    )


@app.post("/jobs/{job_id}/find-contacts")
def find_job_contacts(job_id: int, request: Request):
    from app.agents.contact_finder import run as find_contacts
    jobs = get_all_jobs()
    job  = next((j for j in jobs if j["id"] == job_id), None)
    if not job:
        return RedirectResponse(url="/jobs", status_code=303)

    result = find_contacts(job["company"], job.get("title", ""))

    if not result.get("error") and result.get("contacts"):
        for c in result["contacts"]:
            if c["email"]:
                contact_id = upsert_contact_by_email({
                    "company":          job["company"],
                    "name":             c["name"],
                    "title":            c["position"],
                    "email":            c["email"],
                    "linkedin_url":     c["linkedin"],
                    "source":           "hunter",
                    "confidence_score": c["confidence"],
                    "notes":            c.get("department", ""),
                })
                link_contact_to_job(job_id, contact_id, "recruiter")

    return templates.TemplateResponse(
        request=request, name="job_ai.html",
        context={
            "job":           job,
            "outputs":       get_ai_outputs(job_id),
            "job_contacts":  get_contacts_for_job(job_id),
            "profile_set":   bool(get_profile().get("name")),
            "today":         str(date.today()),
            "hunter_result": result,
        }
    )


# ---------- contacts (AI-discovered only — manual CRUD removed) ----------

@app.post("/jobs/{job_id}/contacts/{jc_id}/unlink")
def unlink_contact(job_id: int, jc_id: int):
    unlink_contact_from_job(jc_id)
    return RedirectResponse(url=f"/jobs/{job_id}/ai", status_code=303)


# ---------- outreach actions ----------

@app.post("/job-contacts/{jc_id}/generate")
def jc_generate_message(jc_id: int, request: Request):
    jc = get_job_contact(jc_id)
    if not jc:
        return RedirectResponse(url="/outreach", status_code=303)

    jobs = get_all_jobs()
    job = next((j for j in jobs if j["id"] == jc["job_id"]), {})
    contact = get_contact(jc["contact_id"])

    error = None
    try:
        content = generate_contact_outreach(job, contact, jc["relationship_type"], get_profile())
        update_job_contact(jc_id, status="drafted", message_content=content)
    except Exception as e:
        error = str(e)

    if error:
        return templates.TemplateResponse(
            request=request, name="job_ai.html",
            context={
                "job": job, "outputs": get_ai_outputs(jc["job_id"]),
                "job_contacts": get_contacts_for_job(jc["job_id"]),
                "profile_set": bool(get_profile().get("name")),
                "today": str(date.today()), "error": error,
            }
        )
    return RedirectResponse(url=f"/jobs/{jc['job_id']}/ai", status_code=303)


@app.post("/job-contacts/{jc_id}/save-message")
async def jc_save_message(jc_id: int, request: Request):
    form = await request.form()
    jc = get_job_contact(jc_id)
    update_job_contact(jc_id, message_content=form.get("message_content", ""))
    return RedirectResponse(url=f"/jobs/{jc['job_id']}/ai", status_code=303)


@app.post("/job-contacts/{jc_id}/status")
async def jc_update_status(jc_id: int, request: Request):
    form = await request.form()
    action = form.get("action", "")
    jc = get_job_contact(jc_id)

    if action == "sent":
        sent_date = form.get("date_sent") or str(date.today())
        try:
            follow_up = str(date.fromisoformat(sent_date) + timedelta(days=7))
        except ValueError:
            follow_up = str(date.today() + timedelta(days=7))
        update_job_contact(jc_id, status="sent", date_sent=sent_date, follow_up_date=follow_up)

    elif action == "responded":
        update_job_contact(jc_id, status="responded",
                           response_notes=form.get("response_notes", ""))

    elif action == "close":
        update_job_contact(jc_id, status="closed")

    return RedirectResponse(url=f"/jobs/{jc['job_id']}/ai", status_code=303)


# ---------- outreach queue ----------

@app.get("/outreach")
def outreach_page(request: Request):
    queue = get_outreach_queue()
    # High-priority jobs with no contacts at all
    jobs = get_all_jobs()
    ranked = rank_jobs(jobs)
    # Exclude jobs that already have any contact linked
    from app.db import get_connection as _gc
    conn = _gc()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT job_id FROM job_contacts")
    all_linked = {r[0] for r in cur.fetchall()}
    conn.close()

    uncontacted = [
        j for j in ranked
        if j["id"] not in all_linked
        and (j.get("status") or "not_applied") not in ("skipped", "rejected")
        and j.get("final_score", 0) >= 75
    ][:10]

    return templates.TemplateResponse(
        request=request, name="outreach.html",
        context={**queue, "uncontacted": uncontacted, "today": str(date.today())}
    )


# ---------- test / admin resets ----------

@app.post("/admin/reset-statuses")
def admin_reset_statuses():
    reset_all_statuses()
    return RedirectResponse(url="/settings", status_code=303)


@app.post("/admin/restore-skipped")
def admin_restore_skipped():
    restore_skipped()
    return RedirectResponse(url="/settings", status_code=303)


_WEIGHT_KEYS = [
    "role_weight", "location_weight", "compensation_weight", "freshness_weight",
]


@app.get("/settings")
def settings_page(request: Request):
    weights = {key: float(get_setting(key, "0.0")) for key in _WEIGHT_KEYS}
    return templates.TemplateResponse(
        request=request, name="settings.html",
        context={
            "weights": weights,
            "cover_letter_template": get_setting("cover_letter_template") or "",
        }
    )


@app.post("/settings")
async def save_settings(request: Request):
    form = await request.form()
    weights_changed = False
    for key in _WEIGHT_KEYS:
        if key in form:
            try:
                set_setting(key, str(round(float(form[key]), 4)))
                weights_changed = True
            except ValueError:
                pass
    if "cover_letter_template" in form:
        set_setting("cover_letter_template", str(form["cover_letter_template"]).strip())
    if weights_changed:
        # Invalidate cached scores so they're recomputed on next page load
        from app.db import get_connection as _gc
        conn = _gc()
        conn.cursor().execute("UPDATE jobs SET final_score = NULL")
        conn.commit()
        conn.close()
    return RedirectResponse(url="/settings", status_code=303)
