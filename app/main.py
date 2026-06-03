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