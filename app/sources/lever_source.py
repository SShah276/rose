"""
Lever board scraper — hardware / deep-tech company boards.

See `app/sources/ats.py` for the company registry and the early-career filter.
"""

from app.sources.ats import LEVER_BOARDS, fetch_all_boards, fetch_lever_board
from app.sources.base import JobSource, RawJob


class LeverSource(JobSource):
    name = "lever"

    def __init__(self, boards: dict | None = None):
        self.boards = boards if boards is not None else LEVER_BOARDS
        # Per-board failures from the last fetch — see GreenhouseSource.errors.
        self.errors: list[str] = []

    def fetch_jobs(self) -> list[RawJob]:
        jobs, self.errors = fetch_all_boards(self.boards, fetch_lever_board)
        if self.errors and not jobs:
            raise RuntimeError("; ".join(self.errors))
        return jobs
