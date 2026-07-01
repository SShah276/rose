"""
Contact Finder Agent — discovers recruiter contacts for a company via Hunter.io.

Flow:
  1. Infer the company's website domain via Claude Haiku (cheap, fast)
  2. Call Hunter.io /domain-search API
  3. Filter + rank results for recruiting relevance
  4. Return structured contact list
"""
import json
import os
import re
import urllib.error
import urllib.request
import urllib.parse

from app.ai import _get_client

_RECRUITING_KEYWORDS = {
    "recruit", "talent", "hiring", "hr", "people", "staffing",
    "acquisition", "sourcing", "university", "campus", "intern",
}

_RECRUITING_DEPARTMENTS = {"hr"}


def _infer_domain(company: str) -> str:
    """Ask Claude Haiku for the company's primary website domain."""
    client = _get_client()
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=60,
        messages=[{
            "role": "user",
            "content": (
                f"What is the primary website domain for the company '{company}'? "
                "Return ONLY the bare domain, e.g. 'stripe.com'. "
                "No http, no www, no path, no explanation."
            ),
        }],
    )
    raw = resp.content[0].text.strip().lower()
    # Strip any prefix the model might add
    raw = re.sub(r"^https?://(www\.)?", "", raw)
    raw = raw.split("/")[0].strip(".")
    return raw


def _is_recruiting(email_obj: dict) -> bool:
    position = (email_obj.get("position") or "").lower()
    dept = (email_obj.get("department") or "").lower()
    return (
        dept in _RECRUITING_DEPARTMENTS
        or any(kw in position for kw in _RECRUITING_KEYWORDS)
    )


def run_linkedin(company: str) -> dict:
    """
    Find US technical recruiter LinkedIn profiles via DuckDuckGo site: search.
    Returns {contacts: [{name, position, linkedin}], error: str|None}
    """
    try:
        from ddgs import DDGS
    except ImportError:
        return {"contacts": [], "error": "ddgs not installed. Run: pip install ddgs"}

    _RECRUITER_KWS = {
        "recruit", "talent", "hiring", "acquisition", "staffing",
        "sourcing", "university", "campus", "intern", "hr",
    }

    def _parse_results(raw: list) -> list:
        out, seen = [], set()
        for r in raw:
            url = (r.get("href") or "").strip()
            if "linkedin.com/in/" not in url or url in seen:
                continue
            seen.add(url)
            title = re.sub(r'\s*\|\s*LinkedIn\s*$', '', r.get("title", "")).strip()
            parts = re.split(r'\s[-–—]\s', title, maxsplit=1)
            name = parts[0].strip() if parts else "Unknown"
            position = parts[1].strip() if len(parts) > 1 else ""
            out.append({"name": name, "position": position, "linkedin": url,
                        "email": "", "confidence": 0, "department": ""})
        return out

    def _is_recruiter(c: dict) -> bool:
        pos = c["position"].lower()
        return any(kw in pos for kw in _RECRUITER_KWS)

    # Primary: US-scoped recruiter search (no quotes around company name)
    query = f"site:linkedin.com/in {company} United States recruiter"
    contacts = []
    try:
        with DDGS() as d:
            contacts = _parse_results(list(d.text(query, max_results=15)))
    except Exception as e:
        return {"contacts": [], "error": f"LinkedIn search failed: {e}"}

    # Prefer profiles whose title contains recruiter keywords
    recruiting = [c for c in contacts if _is_recruiter(c)]
    if recruiting:
        contacts = recruiting

    # Fallback: drop "United States" if nothing found
    if not contacts:
        query2 = f"site:linkedin.com/in {company} recruiter talent acquisition"
        try:
            with DDGS() as d:
                contacts = _parse_results(list(d.text(query2, max_results=12)))
            recruiting2 = [c for c in contacts if _is_recruiter(c)]
            if recruiting2:
                contacts = recruiting2
        except Exception:
            pass

    if not contacts:
        return {"contacts": [], "error": f'No LinkedIn recruiters found for "{company}" — try Hunter.io instead.'}

    return {"contacts": contacts[:8], "error": None}


def run(company: str, job_title: str = "") -> dict:
    """
    Find recruiter contacts for a company using Hunter.io.

    Returns:
        {
          domain: str | None,
          email_pattern: str | None,
          contacts: [{name, email, position, linkedin, confidence, department}],
          error: str | None,
        }
    """
    api_key = os.environ.get("HUNTER_API_KEY", "")
    if not api_key:
        return {
            "domain": None, "email_pattern": None, "contacts": [],
            "error": "HUNTER_API_KEY not set. Add it to your .env file.",
        }

    # Step 1: Infer domain
    try:
        domain = _infer_domain(company)
    except Exception as e:
        return {"domain": None, "email_pattern": None, "contacts": [], "error": f"Domain inference failed: {e}"}

    # Step 2: Hunter.io domain search
    params = urllib.parse.urlencode({"domain": domain, "limit": 10, "api_key": api_key})
    url = f"https://api.hunter.io/v2/domain-search?{params}"
    try:
        with urllib.request.urlopen(url, timeout=12) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            err_detail = json.loads(raw).get("errors", [{}])[0].get("details", raw)
        except Exception:
            err_detail = raw or str(e)
        return {"domain": domain, "email_pattern": None, "contacts": [],
                "error": f"Hunter.io error (domain tried: {domain}): {err_detail}"}
    except Exception as e:
        return {"domain": domain, "email_pattern": None, "contacts": [], "error": f"Hunter.io request failed: {e}"}

    if "errors" in data and data["errors"]:
        err = data["errors"][0].get("details", str(data["errors"][0]))
        return {"domain": domain, "email_pattern": None, "contacts": [], "error": f"Hunter.io: {err}"}

    body = data.get("data", {})
    email_pattern = body.get("pattern")  # e.g. "{first}.{last}"
    emails = body.get("emails", [])

    # Step 3: Filter — recruiting contacts first, then top-confidence others
    recruiting = [e for e in emails if _is_recruiting(e)]
    others = sorted(
        [e for e in emails if not _is_recruiting(e)],
        key=lambda x: x.get("confidence", 0),
        reverse=True,
    )

    selected = recruiting if recruiting else others[:5]
    selected.sort(key=lambda x: x.get("confidence", 0), reverse=True)

    contacts = []
    for e in selected[:8]:
        name = " ".join(filter(None, [e.get("first_name"), e.get("last_name")])).strip()
        contacts.append({
            "name":       name or "Unknown",
            "email":      e.get("value", ""),
            "position":   e.get("position") or "",
            "department": e.get("department") or "",
            "linkedin":   e.get("linkedin") or "",
            "confidence": e.get("confidence", 0),
        })

    return {
        "domain":        domain,
        "email_pattern": email_pattern,
        "contacts":      contacts,
        "error":         None,
    }
