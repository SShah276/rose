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


class JobSource:
    name: str = "base"

    def fetch_jobs(self) -> list[RawJob]:
        raise NotImplementedError(f"{self.__class__.__name__} must implement fetch_jobs()")
