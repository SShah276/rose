from fastapi import FastAPI, Request, UploadFile, File
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.db import init_db, get_all_jobs
from app.scoring import rank_jobs
from app.ingestion import import_jobs_from_csv_bytes

app = FastAPI()
templates = Jinja2Templates(directory="app/templates")


@app.on_event("startup")
def startup():
    init_db()


@app.get("/")
def root():
    return RedirectResponse(url="/jobs")


@app.get("/jobs")
def jobs_page(request: Request):
    jobs = get_all_jobs()
    ranked_jobs = rank_jobs(jobs)

    return templates.TemplateResponse(
        request=request,
        name="jobs.html",
        context={
            "jobs": ranked_jobs
        }
    )


@app.get("/import/csv")
def import_csv_form(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="import_csv.html",
        context={}
    )


@app.post("/import/csv")
async def import_csv(request: Request, file: UploadFile = File(...)):
    file_bytes = await file.read()
    summary = import_jobs_from_csv_bytes(file_bytes)

    return templates.TemplateResponse(
        request=request,
        name="import_result.html",
        context={
            "summary": summary,
            "filename": file.filename
        }
    )

# V2: GitHub Fetch Route
# Pulls from a public internship markdown repo, normalizes,
# and upserts into the DB — same pipeline as CSV import.
#
# Prerequisites:
#   - app/sources/github_source.py  (already created)
#   - normalize_job already exists in app.ingestion
#   - upsert_job already exists in app.db

from app.sources.github_source import GitHubSource, KNOWN_REPOS
from app.ingestion import normalize_job
from app.db import upsert_job
import urllib.request


@app.get("/debug/github")
def debug_github(repo: str = "simplify"):
    url = KNOWN_REPOS.get(repo)
    if not url:
        return {"error": f"Unknown repo '{repo}'"}
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            markdown = resp.read().decode("utf-8")
        lines = markdown.splitlines()
        table_lines = [
            {"n": i + 1, "line": line}
            for i, line in enumerate(lines)
            if line.strip().startswith("|")
        ]
        html_table_lines = [
            {"n": i + 1, "line": line}
            for i, line in enumerate(lines)
            if any(tag in line.lower() for tag in ["<table", "<tr", "<th", "<td"])
        ]
        return {
            "url": url,
            "total_lines": len(lines),
            "total_table_lines": len(table_lines),
            "html_table_line_count": len(html_table_lines),
            "first_20_html_table_lines": html_table_lines[:20],
        }
    except Exception as e:
        return {"error": str(e)}


@app.post("/fetch/github")
def fetch_github(request: Request, repo: str = "simplify"):
    source = GitHubSource(repo_key=repo)
    raw_jobs = source.fetch_jobs()

    summary = {
        "fetched": len(raw_jobs),
        "inserted": 0,
        "updated": 0,
        "skipped": 0,
        "errors": []
    }

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

# V2: User Preferences / Settings Route
# Reads and writes score weights from the settings DB table.

from app.db import get_setting, set_setting

_WEIGHT_KEYS = [
    "role_weight", "location_weight", "compensation_weight",
    "company_quality_weight", "growth_weight", "stability_weight",
    "freshness_weight",
]

@app.get("/settings")
def settings_page(request: Request):
    weights = {key: float(get_setting(key, "0.0")) for key in _WEIGHT_KEYS}
    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={"weights": weights}
    )

@app.post("/settings")
async def save_settings(request: Request):
    form = await request.form()
    for key in _WEIGHT_KEYS:
        if key in form:
            try:
                val = float(form[key])
                set_setting(key, str(round(val, 4)))
            except ValueError:
                pass
    return RedirectResponse(url="/settings", status_code=303)
