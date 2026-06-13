"""
Scraper for intern-list.com — server-rendered internship job list pages.

Pages scraped:
  /swe-intern-list   — Software Engineering internships
  /da-intern-list    — Data / AIML internships
  /pm-intern-list    — Product Management internships
"""

from app.sources.base import JobSource, RawJob
from app.sources.weblist import fetch_job_list_page

BASE_URL = "https://www.intern-list.com"

CATEGORIES = [
    "/swe-intern-list",
    "/da-intern-list",
    "/pm-intern-list",
]


class InternListSource(JobSource):
    name = "intern-list"

    def fetch_jobs(self) -> list[RawJob]:
        jobs: list[RawJob] = []
        errors: list[str] = []
        for path in CATEGORIES:
            try:
                batch = fetch_job_list_page(
                    page_url=BASE_URL + path,
                    href_prefix=path,
                    base_url=BASE_URL,
                    source_name="intern-list",
                    job_type="internship",
                )
                jobs.extend(batch)
            except RuntimeError as e:
                errors.append(str(e))
        if errors and not jobs:
            raise RuntimeError("; ".join(errors))
        return jobs
