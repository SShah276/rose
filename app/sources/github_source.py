import re
import urllib.request
from datetime import date, timedelta
from html.parser import HTMLParser

from app.sources.base import JobSource, RawJob


KNOWN_REPOS = {
    "simplify": "https://raw.githubusercontent.com/SimplifyJobs/Summer2026-Internships/dev/README.md",
}


class _TableParser(HTMLParser):
    """Walks all HTML tables in a document, collecting (header, rows) pairs."""

    def __init__(self):
        super().__init__()
        self.tables = []           # list of (header: list[str], rows: list[list[dict]])
        self._header = []
        self._rows = []
        self._current_row = []
        self._current_cell = None  # {"text": str, "href": str} while inside a cell
        self._in_thead = False

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == "table":
            self._header = []
            self._rows = []
        elif tag == "thead":
            self._in_thead = True
        elif tag == "tr":
            self._current_row = []
        elif tag in ("th", "td"):
            self._current_cell = {"text": "", "href": ""}
        elif tag == "a" and self._current_cell is not None:
            href = attrs_dict.get("href", "")
            # Keep only the first href in each cell (the direct apply link)
            if href and not self._current_cell["href"]:
                self._current_cell["href"] = href

    def handle_endtag(self, tag):
        if tag == "table":
            if self._header:
                self.tables.append((self._header[:], self._rows[:]))
        elif tag == "thead":
            self._in_thead = False
        elif tag == "th":
            if self._current_cell is not None:
                self._header.append(self._current_cell["text"].strip().lower())
            self._current_cell = None
        elif tag == "td":
            if self._current_cell is not None:
                self._current_row.append(self._current_cell.copy())
            self._current_cell = None
        elif tag == "tr":
            if self._current_row and not self._in_thead:
                self._rows.append(self._current_row[:])
            self._current_row = []

    def handle_data(self, data):
        if self._current_cell is not None:
            self._current_cell["text"] += data


def _parse_html_tables(html: str, source_name: str) -> list[RawJob]:
    parser = _TableParser()
    parser.feed(html)

    jobs = []
    last_company = ""

    for header, rows in parser.tables:
        if not header:
            continue

        for row in rows:
            if len(row) < len(header):
                continue

            row_dict = {header[i]: row[i] for i in range(min(len(header), len(row)))}
            all_text = " ".join(cell["text"] for cell in row)

            # Company — handle ↳ continuation rows
            company_cell = row_dict.get("company", {"text": "", "href": ""})
            company_raw = company_cell["text"].strip()
            if company_raw.startswith("↳"):
                company = last_company
            elif company_raw:
                company = company_raw
                last_company = company
            else:
                continue

            # Role/title
            role_key = next((k for k in ("role", "title", "position") if k in row_dict), None)
            role_cell = row_dict[role_key] if role_key else {"text": "", "href": ""}
            title_text = role_cell["text"].strip()
            apply_url = role_cell["href"]

            # Apply URL falls back to the dedicated application column
            if not apply_url:
                app_key = next((k for k in ("application", "application/link", "link", "apply") if k in row_dict), None)
                if app_key:
                    apply_url = row_dict[app_key]["href"]

            location_cell = row_dict.get("location", {"text": "", "href": ""})
            location = location_cell["text"].strip()

            # Age column uses "Xd" format (e.g. "0d", "14d") — convert to ISO date
            age_key = next((k for k in ("age", "date posted", "date") if k in row_dict), None)
            age_raw = row_dict[age_key]["text"].strip() if age_key else ""
            age_match = re.match(r"^(\d+)d$", age_raw)
            if age_match:
                date_posted = str(date.today() - timedelta(days=int(age_match.group(1))))
            else:
                date_posted = age_raw

            # Skip closed/locked roles and blank titles
            if "🔒" in all_text or not title_text:
                continue

            jobs.append(RawJob(
                company=company,
                title=title_text,
                location=location,
                url=apply_url,
                date_posted=date_posted,
                source=source_name,
            ))

    return jobs


class GitHubSource(JobSource):
    name = "github"

    def __init__(self, repo_key: str = "simplify"):
        if repo_key not in KNOWN_REPOS:
            raise ValueError(f"Unknown repo: '{repo_key}'. Options: {list(KNOWN_REPOS)}")
        self.repo_key = repo_key
        self.url = KNOWN_REPOS[repo_key]

    def fetch_jobs(self) -> list[RawJob]:
        try:
            with urllib.request.urlopen(self.url, timeout=10) as resp:
                html = resp.read().decode("utf-8")
        except Exception as e:
            raise RuntimeError(f"Failed to fetch '{self.repo_key}': {e}")
        return _parse_html_tables(html, self.repo_key)
