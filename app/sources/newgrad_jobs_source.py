"""
Scraper for newgrad-jobs.com — server-rendered new-grad job list pages.

Pages scraped:
  /list-software-engineer-jobs  — SWE new-grad roles
  /list-data-analyst            — Data / AIML new-grad roles
"""

from app.sources.base import JobSource, RawJob
from app.sources.weblist import fetch_job_list_page

BASE_URL = "https://www.newgrad-jobs.com"

CATEGORIES = [
    "/list-software-engineer-jobs",
    "/list-data-analyst",
]


class NewGradJobsSource(JobSource):
    name = "newgrad-jobs"

    def fetch_jobs(self) -> list[RawJob]:
        jobs: list[RawJob] = []
        errors: list[str] = []
        for path in CATEGORIES:
            try:
                batch = fetch_job_list_page(
                    page_url=BASE_URL + path,
                    href_prefix=path,
                    base_url=BASE_URL,
                    source_name="newgrad-jobs",
                    job_type="new_grad",
                )
                jobs.extend(batch)
            except RuntimeError as e:
                errors.append(str(e))
        if errors and not jobs:
            raise RuntimeError("; ".join(errors))
        return jobs
