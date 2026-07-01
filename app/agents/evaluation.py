"""
Evaluation Agent — decides what to prioritize from discovered opportunities.

Input:  opportunities (from discovery), current pipeline (interested/saved/applied jobs)
Output: [{action, job_id, label, reason}]  action ∈ {Apply, Review}
"""
import json
import re
from app.ai import _get_client

_SYSTEM = """\
You are a job evaluation agent for a software engineering student.

Given new job opportunities and the current application pipeline, decide what to prioritize TODAY.

Actions:
- "Apply": Strong fit, fresh posting, ready to submit — act now
- "Review": Good opportunity but warrants evaluation before deciding

Rules:
- Max 3 Apply actions, max 3 Review actions
- If the candidate already has many active applications, be more selective about Apply
- Order items by urgency (Apply before Review; fresher before older)
- One-sentence reason per item, referencing score or timing concretely

Return ONLY valid JSON, no markdown:
{"priorities": [{"action": "<Apply|Review>", "job_id": <int>, "label": "<Company — Title>", "reason": "<1-sentence str>"}]}"""


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
    if profile.get("experience"):
        parts.append(f"- Experience: {profile['experience'][:250]}")
    year = profile.get("graduation_year") or ""
    school = " ".join(filter(None, [profile.get("school"), profile.get("degree"), f"({year})" if year else ""]))
    if school.strip():
        parts.append(f"- Education: {school.strip()}")
    if not parts:
        return ""
    return "Candidate profile:\n" + "\n".join(parts) + "\n\n"


def run(opportunities: list[dict], pipeline: list[dict], profile: dict = None) -> list[dict]:
    if not opportunities:
        return []

    context = {
        "new_opportunities": opportunities,
        "current_pipeline": [
            {
                "company":      j["company"],
                "title":        j["title"],
                "status":       j.get("status"),
                "date_applied": j.get("date_applied") or "",
            }
            for j in pipeline
        ],
        "active_applications": sum(1 for j in pipeline if j.get("status") == "applied"),
    }

    prof = _profile_block(profile)
    client = _get_client()
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=700,
        system=_SYSTEM,
        messages=[{
            "role": "user",
            "content": f"{prof}Context:\n{json.dumps(context, indent=2)}\n\nWhat should I prioritize today?"
        }]
    )

    try:
        return _parse(resp.content[0].text).get("priorities", [])
    except Exception:
        return []
