"""
Shared client for hosted ATS job-board APIs (Greenhouse, Lever).

Unlike the aggregator lists in `weblist.py`, these are per-company endpoints:
one HTTP call returns a company's entire public board as JSON, no auth needed.
That makes them the only practical way to reach hardware / computer-engineering
roles at volume — the community job-list repos this app already scrapes are
overwhelmingly software-focused.

Because a board returns *every* open req (Waymo alone posts 364, Anduril 2000+),
postings are filtered down to early-career openings before they reach the DB.

Company tokens below were each verified live: a token that looks obvious is
often the wrong company (`archer` is a veterinary clinic, `figure` is a lending
startup, `lattice` is an HR tool, `sila` is an HVAC contractor rather than Sila
Nanotechnologies). Check the board's own company_name and department list before
adding an entry here.
"""

import concurrent.futures
import json
import re
import urllib.request
from datetime import date

from app.sources.base import RawJob

_TIMEOUT = 15
_MAX_WORKERS = 10
_DESC_LIMIT = 2000
_UA = "Mozilla/5.0 (compatible; ROSE-bot/1.0)"


# ── Company registries ────────────────────────────────────────────────────────
# token -> canonical display name. The display name is what lands in the
# `company` column, so it must stay stable: dedupe_key is company|title, and
# renaming an entry duplicates every posting from that board.

GREENHOUSE_BOARDS = {
    # Silicon, AI compute & quantum
    "asteralabs":        "Astera Labs",
    "tenstorrent":       "Tenstorrent",
    "lightmatter":       "Lightmatter",
    "etchedai":          "Etched",
    "ionq":              "IonQ",
    "psiquantum":        "PsiQuantum",

    # Robotics & autonomy
    "waymo":             "Waymo",
    "nuro":              "Nuro",
    "motional":          "Motional",
    "kodiak":            "Kodiak Robotics",
    "figureai":          "Figure",
    "apptronik":         "Apptronik",
    "agilityrobotics":   "Agility Robotics",
    "diligentrobotics":  "Diligent Robotics",
    "carbonrobotics":    "Carbon Robotics",

    # Aerospace & defense
    "andurilindustries": "Anduril Industries",
    "astranis":          "Astranis",
    "muonspace":         "Muon Space",
    "relativity":        "Relativity Space",
    "ursamajor":         "Ursa Major",
    "vast":              "Vast",
    "skyryse":           "Skyryse",
    "divergent":         "Divergent",

    # Devices & consumer hardware
    "neuralink":         "Neuralink",
    "oura":              "Oura",
    "peloton":           "Peloton",
    "samsara":           "Samsara",
    "verkada":           "Verkada",
    "formlabs":          "Formlabs",
    "markforged":        "Markforged",
    "carbon":            "Carbon",

    # Energy, EV & materials
    "lucidmotors":       "Lucid Motors",
    "redwoodmaterials":  "Redwood Materials",
    "oklo":              "Oklo",
    "solidpower":        "Solid Power",
    "sonatus":           "Sonatus",
}

LEVER_BOARDS = {
    "shieldai":      "Shield AI",
    "zoox":          "Zoox",
    "aeva":          "Aeva",
    "hermeus":       "Hermeus",
    "velo3d":        "Velo3D",
    "dexterity":     "Dexterity",
    "atomcomputing": "Atom Computing",
    "rigetti":       "Rigetti Computing",
    "merlinlabs":    "Merlin Labs",
    "latch":         "Latch",
}


# ── Early-career filter ───────────────────────────────────────────────────────

_EARLY_CAREER = re.compile(
    r"\bintern(ship|s)?\b"
    r"|\bco-?op\b"
    r"|\bnew\s*grad(uate)?\b"
    r"|\bearly\s+career\b"
    r"|\bentry[-\s]?level\b"
    r"|\buniversity\s+(grad\w*|hire|recruit\w*|program|relations)\b"
    r"|\bcampus\s+(hire|recruit\w*|program)\b"
    r"|\bgraduate\s+(engineer\w*|program|rotation\w*|analyst|developer|scientist)\b"
    r"|\b20(2[5-9]|3\d)\s+grad(uate)?s?\b"
    r"|\bapprentice(ship)?\b"
    r"|\brotational\s+program\b"
    r"|\bstudent\b",
    re.IGNORECASE,
)

# Seniority markers veto an early-career match: "Intern Program Manager" and
# "Early Career Program Lead" are staff roles, not openings for a new grad.
_SENIOR = re.compile(
    r"\b(senior|sr\.?|staff|principal|lead|leader|director|head\s+of|vp|"
    r"vice\s+president|manager|distinguished|fellow|chief|executive)\b"
    r"|\blevel\s*[3-9]\b"
    r"|\b(ii|iii|iv|vi{0,3})\s*$",
    re.IGNORECASE,
)

# Lever's `commitment` is free text and varies per company, so it must be
# matched whole — "International Office Entity" contains the substring "intern".
_INTERN_COMMITMENT = re.compile(r"^intern(ship)?$", re.IGNORECASE)


def is_early_career(title: str, commitment: str = "") -> bool:
    """True if a posting looks open to an intern or new grad."""
    if _SENIOR.search(title):
        return False
    if _EARLY_CAREER.search(title):
        return True
    return bool(commitment and _INTERN_COMMITMENT.match(commitment.strip()))


def _job_type(title: str, commitment: str = "") -> str:
    text = f"{title} {commitment}"
    if re.search(r"\bintern(ship|s)?\b|\bco-?op\b|\bstudent\b", text, re.IGNORECASE):
        return "internship"
    return "new_grad"


# ── HTTP ──────────────────────────────────────────────────────────────────────

def _get_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


# ── Greenhouse ────────────────────────────────────────────────────────────────

def fetch_greenhouse_board(token: str, company: str) -> list[RawJob]:
    """
    Fetch one Greenhouse board.

    Descriptions are skipped on purpose: adding `?content=true` inflates the
    response roughly 8x (Waymo: 355 KB -> 2.9 MB) and Greenhouse double-escapes
    the HTML, for text the scoring pipeline never reads.
    """
    data = _get_json(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs")

    jobs = []
    for post in data.get("jobs", []):
        title = (post.get("title") or "").strip()
        if not title or not is_early_career(title):
            continue

        stamp = post.get("first_published") or post.get("updated_at") or ""
        jobs.append(RawJob(
            company=company,
            title=title,
            location=(post.get("location") or {}).get("name", "").strip() or "Unknown",
            url=post.get("absolute_url", ""),
            date_posted=stamp[:10],
            source="greenhouse",
            job_type=_job_type(title),
        ))
    return jobs


# ── Lever ─────────────────────────────────────────────────────────────────────

def _lever_pay(salary_range) -> str:
    """Render Lever's structured salaryRange into a string parse_salary handles."""
    if not salary_range or salary_range.get("currency") not in (None, "USD"):
        return ""
    low, high = salary_range.get("min"), salary_range.get("max")
    if not low:
        return ""
    interval = salary_range.get("interval") or ""
    if "hour" in interval:
        return f"${low}/hr"
    if "month" in interval:
        return f"${int(low) * 12}"
    return f"${low}-${high}" if high else f"${low}"


def fetch_lever_board(token: str, company: str) -> list[RawJob]:
    """Fetch one Lever board. Lever supplies salary and plain-text descriptions."""
    data = _get_json(f"https://api.lever.co/v0/postings/{token}?mode=json")

    jobs = []
    for post in data:
        title = (post.get("text") or "").strip()
        categories = post.get("categories") or {}
        commitment = categories.get("commitment") or ""
        if not title or not is_early_career(title, commitment):
            continue

        created = post.get("createdAt")
        try:
            posted = date.fromtimestamp(created / 1000).isoformat() if created else ""
        except (TypeError, ValueError, OSError, OverflowError):
            posted = ""

        jobs.append(RawJob(
            company=company,
            title=title,
            location=(categories.get("location") or "").strip() or "Unknown",
            url=post.get("hostedUrl", ""),
            description=(post.get("descriptionPlain") or "")[:_DESC_LIMIT],
            date_posted=posted,
            source="lever",
            job_type=_job_type(title, commitment),
            pay_raw=_lever_pay(post.get("salaryRange")),
        ))
    return jobs


# ── Concurrent fan-out ────────────────────────────────────────────────────────

def fetch_all_boards(boards: dict, fetcher) -> tuple[list[RawJob], list[str]]:
    """
    Run `fetcher(token, company)` across every board in parallel.

    Dozens of sequential 15s-timeout requests would make a fetch run crawl, and
    one unreachable board must not sink the rest — failures are collected and
    returned alongside whatever succeeded.
    """
    jobs: list[RawJob] = []
    errors: list[str] = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        futures = {
            pool.submit(fetcher, token, company): token
            for token, company in boards.items()
        }
        for future in concurrent.futures.as_completed(futures):
            token = futures[future]
            try:
                jobs.extend(future.result())
            except Exception as e:
                errors.append(f"{token}: {e}")

    return jobs, errors
