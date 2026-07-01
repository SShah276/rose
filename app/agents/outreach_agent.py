"""
Outreach Agent — identifies who to contact and what applications need follow-up.

Input:  uncontacted job contacts, stale applications (applied 7+ days)
Output: [{action, job_id, label, reason}]  action ∈ {Message, Follow Up}
"""
import json
import re
from app.ai import _get_client

_SYSTEM = """\
You are an outreach coordinator for a software engineering student's job search.

Given contacts linked to jobs and stale applications, identify the most valuable outreach actions for TODAY.

Actions:
- "Message": Send initial outreach to a recruiter/contact not yet contacted
- "Follow Up": Check in on an application submitted 7+ days ago with no response

Rules:
- Max 2 Message actions, max 2 Follow Up actions
- Only suggest Message for contacts with real names and a company
- Only suggest Follow Up for applications with 7+ days since applying
- Prioritize high-value contacts (recruiters, hiring managers) over general contacts
- One-sentence reason per item, be specific about timing and why it matters

Return ONLY valid JSON, no markdown:
{"actions": [{"action": "<Message|Follow Up>", "job_id": <int>, "label": "<descriptive str>", "reason": "<1-sentence str>"}]}"""


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
    if profile.get("name"):
        parts.append(f"- Name: {profile['name']}")
    if profile.get("preferred_roles"):
        parts.append(f"- Seeking: {profile['preferred_roles']}")
    year = profile.get("graduation_year") or ""
    school = " ".join(filter(None, [profile.get("school"), f"({year})" if year else ""]))
    if school.strip():
        parts.append(f"- Education: {school.strip()}")
    if not parts:
        return ""
    return "Candidate profile:\n" + "\n".join(parts) + "\n\n"


def run(uncontacted: list[dict], stale_applications: list[dict], profile: dict = None) -> list[dict]:
    if not uncontacted and not stale_applications:
        return []

    context = {
        "uncontacted_contacts": [
            {
                "contact_name":    c.get("contact_name", ""),
                "relationship":    c.get("relationship_type", ""),
                "company":         c.get("company", ""),
                "job_title":       c.get("job_title", ""),
                "job_id":          c.get("job_id"),
            }
            for c in uncontacted[:6]
        ],
        "stale_applications": [
            {
                "company":     a["company"],
                "title":       a["title"],
                "job_id":      a["id"],
                "days_since":  a.get("days_since", 0),
                "date_applied": a.get("date_applied", ""),
            }
            for a in stale_applications[:6]
        ],
    }

    prof = _profile_block(profile)
    client = _get_client()
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        system=_SYSTEM,
        messages=[{
            "role": "user",
            "content": f"{prof}Outreach context:\n{json.dumps(context, indent=2)}\n\nWhat outreach should I do today?"
        }]
    )

    try:
        return _parse(resp.content[0].text).get("actions", [])
    except Exception:
        return []
