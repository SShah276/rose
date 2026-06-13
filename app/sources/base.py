from dataclasses import dataclass
from typing import Optional


@dataclass
class RawJob:
    company: str
    title: str
    location: str
    salary: Optional[int] = None
    url: str = ""
    description: str = ""
    date_posted: str = ""
    source: str = ""
    job_type: str = ""   # internship | new_grad | full_time | contract
    pay_raw:  str = ""   # original salary string, e.g. "$62/hr" or "$100K-$120K"


class JobSource:
    name: str = "base"

    def fetch_jobs(self) -> list[RawJob]:
        raise NotImplementedError(f"{self.__class__.__name__} must implement fetch_jobs()")
