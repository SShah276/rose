"""
Discovery Agent — finds the best new opportunities to act on today.

Input:  ranked job list (all statuses)
Output: [{job_id, company, title, reason}]  (3-5 items)
"""
import json
import re
from app.ai import _get_client

_SYSTEM = """\
You are a job discovery agent helping a software engineering student find the best opportunities to act on TODAY.

Given a list of ranked jobs, select 3-5 that deserve immediate attention. Focus on:
1. Fresh postings (≤7 days old, freshness_score ≥ 70)
2. High overall score (≥70)
3. Strong role and location fit
4. Not yet acted on (status: not_applied, interested, or saved only)

Be selective — only surface genuinely strong opportunities, not just the top N by score.
Write a one-sentence reason that explains WHY this job deserves action today (score + freshness + fit).

Return ONLY valid JSON, no markdown, no explanation:
{"opportunities": [{"job_id": <int>, "company": "<str>", "title": "<str>", "reason": "<1-sentence str>"}]}"""


def _parse(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text.strip())
    return json.loads(text)


def _profile_block(profile: dict | None) -> str:
    if not profile:
        return ""
    parts = []
    if profile.get("preferred_roles"):
        parts.append(f"- Targeting: {profile['preferred_roles']}")
    if profile.get("skills"):
        parts.append(f"- Skills: {profile['skills']}")
    year = profile.get("graduation_year") or ""
    school = " ".join(filter(None, [profile.get("school"), profile.get("degree"), f"({year})" if year else ""]))
    if school.strip():
        parts.append(f"- Education: {school.strip()}")
    if not parts:
        return ""
    return "Candidate profile:\n" + "\n".join(parts) + "\n\n"


def run(ranked_jobs: list[dict], profile: dict = None) -> list[dict]:
    actionable_statuses = {"not_applied", "not_reviewed", "interested", "saved"}
    candidates = [
        {
            "job_id":      j["id"],
            "company":     j["company"],
            "title":       j["title"],
            "location":    j.get("location") or "Unknown",
            "role_type":   j.get("role_type") or "",
            "score":       j.get("final_score", 0),
            "freshness":   j.get("freshness_score", 50),
            "date_posted": j.get("date_posted") or "",
            "salary":      j.get("pay_raw") or (f"${j['salary']:,}/yr" if j.get("salary") else "N/A"),
            "status":      j.get("status") or "not_applied",
        }
        for j in ranked_jobs
        if (j.get("status") or "not_applied") in actionable_statuses
    ][:40]

    if not candidates:
        return []

    prof = _profile_block(profile)
    client = _get_client()
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=800,
        system=_SYSTEM,
        messages=[{
            "role": "user",
            "content": f"{prof}Available jobs (ranked by score):\n{json.dumps(candidates, indent=2)}\n\nSelect the 3-5 best opportunities for today."
        }]
    )

    try:
        return _parse(resp.content[0].text).get("opportunities", [])
    except Exception:
        return []
