"""
Greenhouse board scraper — hardware / deep-tech company boards.

See `app/sources/ats.py` for the company registry and the early-career filter.
"""

from app.sources.ats import GREENHOUSE_BOARDS, fetch_all_boards, fetch_greenhouse_board
from app.sources.base import JobSource, RawJob


class GreenhouseSource(JobSource):
    name = "greenhouse"

    def __init__(self, boards: dict | None = None):
        self.boards = boards if boards is not None else GREENHOUSE_BOARDS
        # Per-board failures from the last fetch. A board that times out would
        # otherwise vanish silently and just look like a company with no
        # openings, so callers read this to report partial runs.
        self.errors: list[str] = []

    def fetch_jobs(self) -> list[RawJob]:
        jobs, self.errors = fetch_all_boards(self.boards, fetch_greenhouse_board)
        if self.errors and not jobs:
            raise RuntimeError("; ".join(self.errors))
        return jobs
