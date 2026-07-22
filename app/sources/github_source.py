import re
import urllib.request
from datetime import date, timedelta
from html.parser import HTMLParser

from app.sources.base import JobSource, RawJob


# Each entry: url, format ("html" | "markdown"), job_type
KNOWN_REPOS = {
    "simplify": {
        "url":      "https://raw.githubusercontent.com/SimplifyJobs/Summer2026-Internships/dev/README.md",
        "format":   "html",
        "job_type": "internship",
    },
    "new-grad": {
        "url":      "https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/dev/README.md",
        "format":   "html",
        "job_type": "new_grad",
    },
    "speedyapply": {
        "url":      "https://raw.githubusercontent.com/speedyapply/2026-SWE-College-Jobs/main/README.md",
        "format":   "markdown",
        "job_type": "internship",
    },
    "ouckah": {
        "url":      "https://raw.githubusercontent.com/Ouckah/Summer2026-Internships/main/README.md",
        "format":   "html",
        "job_type": "internship",
    },
    "cvrve-newgrad": {
        "url":      "https://raw.githubusercontent.com/cvrve/New-Grad-2026/dev/README.md",
        "format":   "html",
        "job_type": "new_grad",
    },
}


# ── HTML table parser ─────────────────────────────────────────────────────────

class _TableParser(HTMLParser):
    """Walks all HTML tables in a document, collecting (header, rows) pairs."""

    def __init__(self):
        super().__init__()
        self.tables = []
        self._header = []
        self._rows = []
        self._current_row = []
        self._current_cell = None
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


def _age_to_date(age_raw: str) -> str:
    m = re.match(r"^(\d+)d$", age_raw)
    if m:
        return str(date.today() - timedelta(days=int(m.group(1))))
    return age_raw


def _parse_html_tables(html: str, source_name: str, job_type: str) -> list[RawJob]:
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

            company_cell = row_dict.get("company", {"text": "", "href": ""})
            company_raw = company_cell["text"].strip()
            if company_raw.startswith("↳"):
                company = last_company
            elif company_raw:
                company = company_raw
                last_company = company
            else:
                continue

            role_key = next((k for k in ("role", "title", "position") if k in row_dict), None)
            role_cell = row_dict[role_key] if role_key else {"text": "", "href": ""}
            title_text = role_cell["text"].strip()
            apply_url = role_cell["href"]

            if not apply_url:
                app_key = next((k for k in ("application", "application/link", "link", "apply") if k in row_dict), None)
                if app_key:
                    apply_url = row_dict[app_key]["href"]

            location = row_dict.get("location", {"text": "", "href": ""})["text"].strip()

            age_key = next((k for k in ("age", "date posted", "date") if k in row_dict), None)
            age_raw = row_dict[age_key]["text"].strip() if age_key else ""
            date_posted = _age_to_date(age_raw)

            if "🔒" in all_text or not title_text:
                continue

            jobs.append(RawJob(
                company=company,
                title=title_text,
                location=location,
                url=apply_url,
                date_posted=date_posted,
                source=source_name,
                job_type=job_type,
                pay_raw="",
            ))

    return jobs


# ── Markdown pipe table parser ────────────────────────────────────────────────

def _md_cells(line: str) -> list[str]:
    """Split '| A | B | C |' into ['A', 'B', 'C']."""
    parts = line.split("|")
    return [p.strip() for p in parts[1:-1]]


def _is_separator(line: str) -> bool:
    return bool(re.match(r"^\|[-:\s|]+\|$", line.strip()))


def _clean_text(raw: str) -> str:
    """Strip HTML tags and markdown bold/italic markers, return plain text."""
    text = re.sub(r"<[^>]+>", "", raw)   # strip HTML tags
    text = re.sub(r"\*+", "", text)       # strip ** bold / * italic
    return text.strip()


def _md_link(cell: str) -> tuple[str, str]:
    """
    Return (plain_text, href) from a cell that may contain:
      - Markdown link:  [**Company**](https://...)
      - HTML anchor:    <a href="https://..."><strong>Company</strong></a>
      - Plain text:     Company
    """
    # Markdown link [text](url)
    m = re.search(r"\[([^\]]+)\]\(([^)]+)\)", cell)
    if m:
        return _clean_text(m.group(1)), m.group(2).strip()

    # HTML anchor href
    href_m = re.search(r'href=["\']([^"\']+)["\']', cell)
    href = href_m.group(1).strip() if href_m else ""

    return _clean_text(cell), href


def _parse_markdown_tables(text: str, source_name: str, job_type: str) -> list[RawJob]:
    jobs: list[RawJob] = []
    table_block: list[str] = []

    def _flush(block: list[str]) -> list[RawJob]:
        if len(block) < 2:
            return []
        header_line = block[0]
        if _is_separator(header_line):
            return []
        headers = [h.lower() for h in _md_cells(header_line)]
        result: list[RawJob] = []
        last_company = ""

        for line in block[1:]:
            if _is_separator(line):
                continue
            cells = _md_cells(line)
            if len(cells) < len(headers):
                continue
            row = dict(zip(headers, cells))

            # Company
            company_text, _ = _md_link(row.get("company", ""))
            if company_text.startswith("↳") or not company_text:
                company = last_company
            else:
                company = company_text
                last_company = company

            # Title / apply URL
            title_key = next((k for k in ("position", "role", "title") if k in row), None)
            title_cell = row.get(title_key, "") if title_key else ""
            title, apply_url = _md_link(title_cell)

            if not apply_url:
                url_key = next((k for k in ("posting", "application", "apply", "link") if k in row), None)
                if url_key:
                    _, apply_url = _md_link(row[url_key])

            # Location
            location = row.get("location", "").strip() or "Unknown"

            # Salary
            sal_key = next((k for k in ("salary", "pay", "compensation") if k in row), None)
            pay_raw = row.get(sal_key, "").strip() if sal_key else ""

            # Age → date
            age_key = next((k for k in ("age", "date posted", "date") if k in row), None)
            age_raw = row.get(age_key, "").strip() if age_key else ""
            date_posted = _age_to_date(age_raw)

            if "🔒" in " ".join(cells) or not title:
                continue

            result.append(RawJob(
                company=company,
                title=title,
                location=location,
                url=apply_url,
                date_posted=date_posted,
                source=source_name,
                job_type=job_type,
                pay_raw=pay_raw,
            ))
        return result

    for line in text.splitlines():
        stripped = line.strip()
        if re.match(r"^\|.+\|$", stripped):
            table_block.append(stripped)
        else:
            if table_block:
                jobs.extend(_flush(table_block))
                table_block = []

    if table_block:
        jobs.extend(_flush(table_block))

    return jobs


# ── Source class ──────────────────────────────────────────────────────────────

class GitHubSource(JobSource):
    name = "github"

    def __init__(self, repo_key: str = "simplify"):
        if repo_key not in KNOWN_REPOS:
            raise ValueError(f"Unknown repo: '{repo_key}'. Options: {list(KNOWN_REPOS)}")
        self.repo_key = repo_key
        cfg = KNOWN_REPOS[repo_key]
        self.url      = cfg["url"]
        self.format   = cfg["format"]
        self.job_type = cfg["job_type"]

    def fetch_jobs(self) -> list[RawJob]:
        try:
            with urllib.request.urlopen(self.url, timeout=15) as resp:
                text = resp.read().decode("utf-8")
        except Exception as e:
            raise RuntimeError(f"Failed to fetch '{self.repo_key}': {e}")

        if self.format == "markdown":
            return _parse_markdown_tables(text, self.repo_key, self.job_type)
        return _parse_html_tables(text, self.repo_key, self.job_type)
