"""
Shared parser for server-rendered job-list pages (intern-list.com, newgrad-jobs.com).

Both sites render jobs as <a href="/CATEGORY/slug"> blocks containing the
job title, company name, and an optional date as text nodes.
"""

import re
import urllib.request
from datetime import datetime
from html.parser import HTMLParser

from app.sources.base import RawJob


class _JobLinkParser(HTMLParser):
    """Collects all <a href="PREFIX/..."> elements and their text content."""

    def __init__(self, href_prefix: str):
        super().__init__()
        self._prefix = href_prefix + "/"
        self.jobs: list[dict] = []
        self._cur: dict | None = None
        self._nested_a = 0

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            if self._cur is None:
                href = dict(attrs).get("href", "")
                if href.startswith(self._prefix) and len(href) > len(self._prefix):
                    self._cur = {"href": href, "texts": []}
            else:
                self._nested_a += 1

    def handle_endtag(self, tag):
        if tag == "a" and self._cur is not None:
            if self._nested_a == 0:
                self.jobs.append(self._cur)
                self._cur = None
            else:
                self._nested_a -= 1

    def handle_data(self, data):
        if self._cur is not None:
            text = data.strip()
            if text:
                self._cur["texts"].append(text)


def _parse_date(text: str) -> str:
    """Convert 'June 10, 2026' → '2026-06-10'. Returns '' on failure."""
    try:
        return datetime.strptime(text.strip(), "%B %d, %Y").strftime("%Y-%m-%d")
    except ValueError:
        return ""


def _slug_company(href: str) -> str:
    """Fallback: derive company from slug ending in _at_COMPANY_ID."""
    slug = href.rsplit("/", 1)[-1]
    at_idx = slug.rfind("_at_")
    if at_idx == -1:
        return ""
    company_part = re.sub(r"_\d+$", "", slug[at_idx + 4:])
    return company_part.replace("_", " ").title()


def _extract_fields(texts: list[str], href: str) -> tuple[str, str, str]:
    """
    Return (title, company, date_posted) from the text nodes inside the link.

    Layout on intern-list.com:  [title, date, company]
    Layout on newgrad-jobs.com: [title, company] or [title, company, date]
    The date is distinguished by its 'Month DD, YYYY' format.
    """
    date_posted = ""
    others: list[str] = []
    for t in texts:
        d = _parse_date(t)
        if d:
            date_posted = d
        else:
            others.append(t)

    title = others[0] if others else ""
    company = others[-1] if len(others) >= 2 else ""
    if not company:
        company = _slug_company(href)
    return title, company, date_posted


def fetch_job_list_page(
    page_url: str,
    href_prefix: str,
    base_url: str,
    source_name: str,
    job_type: str = "",
) -> list[RawJob]:
    """Fetch one job-list page and return parsed RawJob entries."""
    req = urllib.request.Request(
        page_url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; ROSE-bot/1.0)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        raise RuntimeError(f"Failed to fetch {page_url}: {e}")

    parser = _JobLinkParser(href_prefix)
    parser.feed(html)

    jobs: list[RawJob] = []
    for entry in parser.jobs:
        title, company, date_posted = _extract_fields(entry["texts"], entry["href"])
        if not title or not company:
            continue
        jobs.append(RawJob(
            company=company,
            title=title,
            location="Unknown",
            url=base_url + entry["href"],
            date_posted=date_posted,
            source=source_name,
            job_type=job_type,
        ))
    return jobs
