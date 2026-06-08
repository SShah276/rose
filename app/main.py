from datetime import date, timedelta

from fastapi import FastAPI, Request, UploadFile, File
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.db import (
    init_db, get_all_jobs,
    update_application, get_followups_due, get_tracked_applications, get_stats,
    get_setting, set_setting, upsert_job,
    reset_all_statuses, restore_skipped,
    get_profile, save_profile,
    get_ai_outputs, upsert_ai_output, save_ai_output_content, toggle_ai_output_approved,
)
from app.ai import generate_job_analysis, generate_cover_letter, generate_outreach
from app.scoring import rank_jobs
from app.ingestion import import_jobs_from_csv_bytes, normalize_job
from app.sources.github_source import GitHubSource, KNOWN_REPOS
import urllib.request

app = FastAPI()
templates = Jinja2Templates(directory="app/templates")


@app.on_event("startup")
def startup():
    init_db()


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
    jobs = get_all_jobs()
    ranked_jobs = rank_jobs(jobs)
    visible = [j for j in ranked_jobs if (j.get("status") or "not_applied") != "skipped"]
    return templates.TemplateResponse(
        request=request,
        name="jobs.html",
        context={
            "jobs": visible,
            "plan": _build_daily_plan(ranked_jobs),
            "followups": get_followups_due(),
            "stats": get_stats(),
        }
    )


# ---------- job actions ----------

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
    }
    if action == "apply":
        return RedirectResponse(url=f"/jobs/{job_id}/apply", status_code=303)
    if action in status_map:
        update_application(job_id, status=status_map[action])
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
                "url":         raw.url,
                "description": raw.description,
                "date_posted": raw.date_posted,
            }, source=raw.source)
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
            "job": job,
            "outputs": get_ai_outputs(job_id),
            "profile_set": bool(get_profile().get("name")),
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
        content = _AI_GENERATORS[type](job, get_profile())
        upsert_ai_output(job_id, type, content)
    except Exception as e:
        error = str(e)

    return templates.TemplateResponse(
        request=request,
        name="job_ai.html",
        context={
            "job": job,
            "outputs": get_ai_outputs(job_id),
            "profile_set": bool(get_profile().get("name")),
            "error": error,
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
    "role_weight", "location_weight", "compensation_weight",
    "company_quality_weight", "growth_weight", "stability_weight",
    "freshness_weight",
]


@app.get("/settings")
def settings_page(request: Request):
    weights = {key: float(get_setting(key, "0.0")) for key in _WEIGHT_KEYS}
    return templates.TemplateResponse(request=request, name="settings.html", context={"weights": weights})


@app.post("/settings")
async def save_settings(request: Request):
    form = await request.form()
    for key in _WEIGHT_KEYS:
        if key in form:
            try:
                set_setting(key, str(round(float(form[key]), 4)))
            except ValueError:
                pass
    return RedirectResponse(url="/settings", status_code=303)
