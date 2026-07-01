"""
Planner — orchestrates Discovery → Evaluation → Outreach agents
and returns a unified daily recruiting plan.
"""
from datetime import date
from app.agents import discovery, evaluation, outreach_agent
from app.db import get_profile


def generate_plan(ranked_jobs: list[dict], uncontacted_contacts: list[dict]) -> dict:
    """
    Run all three agents sequentially and merge their outputs into one plan.
    Returns: {plan, generated_at, discovery_count, error}
    """
    today = str(date.today())
    errors = []
    profile = get_profile()

    # ── Agent 1: Discovery ─────────────────────────────────────────────────
    try:
        opportunities = discovery.run(ranked_jobs, profile=profile)
    except Exception as e:
        opportunities = []
        errors.append(f"Discovery: {e}")

    # ── Agent 2: Evaluation (needs discovery output) ───────────────────────
    pipeline = [
        j for j in ranked_jobs
        if (j.get("status") or "not_applied") in ("interested", "saved", "applied")
    ]
    try:
        priorities = evaluation.run(opportunities, pipeline, profile=profile)
    except Exception as e:
        priorities = []
        errors.append(f"Evaluation: {e}")

    # ── Agent 3: Outreach (independent of 1 & 2) ──────────────────────────
    stale = []
    for j in ranked_jobs:
        if j.get("status") == "applied" and j.get("date_applied"):
            try:
                days = (date.today() - date.fromisoformat(j["date_applied"])).days
                if days >= 7:
                    stale.append({**j, "days_since": days})
            except ValueError:
                pass

    try:
        outreach_actions = outreach_agent.run(uncontacted_contacts, stale, profile=profile)
    except Exception as e:
        outreach_actions = []
        errors.append(f"Outreach: {e}")

    # ── Merge ──────────────────────────────────────────────────────────────
    plan = []
    for item in priorities:
        plan.append({
            "action":  item.get("action", "Review"),
            "job_id":  item.get("job_id"),
            "label":   item.get("label", ""),
            "reason":  item.get("reason", ""),
            "source":  "agent",
        })
    for item in outreach_actions:
        plan.append({
            "action":  item.get("action", "Follow Up"),
            "job_id":  item.get("job_id"),
            "label":   item.get("label", ""),
            "reason":  item.get("reason", ""),
            "source":  "agent",
        })

    return {
        "plan":              plan,
        "generated_at":      today,
        "discovery_count":   len(opportunities),
        "error":             "; ".join(errors) if errors else None,
    }
