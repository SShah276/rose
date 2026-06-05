import csv
import io

from app.sources.base import JobSource, RawJob
from app.ingestion import parse_salary, clean_text


class CSVSource(JobSource):
    name = "csv"

    def __init__(self, file_bytes: bytes):
        self.file_bytes = file_bytes

    def fetch_jobs(self) -> list[RawJob]:
        decoded = self.file_bytes.decode("utf-8")
        reader = csv.DictReader(io.StringIO(decoded))
        jobs = []
        for row in reader:
            company = clean_text(row.get("company", ""))
            title = clean_text(row.get("title", ""))
            location = clean_text(row.get("location", ""))
            if not company or not title or not location:
                continue
            jobs.append(RawJob(
                company=company,
                title=title,
                location=location,
                salary=parse_salary(row.get("salary")),
                url=clean_text(row.get("url", "")),
                description=clean_text(row.get("description", "")),
                date_posted=clean_text(row.get("date_posted", "")),
                source="csv",
            ))
        return jobs
