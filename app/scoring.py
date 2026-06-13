from datetime import date
from app.db import get_setting


_DEFAULT_WEIGHTS = {
    "role_weight":         0.40,
    "location_weight":     0.25,
    "compensation_weight": 0.25,
    "freshness_weight":    0.10,
}


def _load_weights() -> dict:
    weights = {}
    for key, default in _DEFAULT_WEIGHTS.items():
        try:
            weights[key] = float(get_setting(key, str(default)))
        except (ValueError, TypeError):
            weights[key] = default
    return weights


def _score_location(location: str) -> int:
    loc = location.lower().strip()
    if not loc or loc == "unknown":
        return 50
    if "remote" in loc:
        return 85
    if loc in ("hybrid", "flexible"):
        return 80
    if "united states" in loc or loc in ("us", "usa"):
        return 75
    if "multiple" in loc:
        return 70
    if "chicago" in loc:
        return 99
    if "new york" in loc or "nyc" in loc:
        return 96
    if "seattle" in loc or "bellevue" in loc:
        return 93
    if "austin" in loc:
        return 93
    if "boston" in loc or "cambridge, ma" in loc:
        return 93
    if "atlanta" in loc:
        return 90
    if "denver" in loc or "boulder" in loc:
        return 90
    if "san francisco" in loc:
        return 87
    if any(c in loc for c in ("santa clara", "san jose", "sunnyvale", "palo alto", "berkeley")):
        return 85
    if "los angeles" in loc:
        return 83
    if "san diego" in loc:
        return 85
    if "miami" in loc:
        return 83
    if "raleigh" in loc or "durham" in loc:
        return 83
    if "pittsburgh" in loc:
        return 80
    if "washington" in loc and ("dc" in loc or "d.c" in loc):
        return 79
    return 50


def calculate_job_score(job, weights: dict):
    role_scores = {
        # Software & Systems Engineering
        "SWE": 99,
        "Backend": 98,
        "Systems/Infra": 97,
        "Fullstack": 95,
        "Frontend": 90,
        "Mobile (iOS/Android)": 90,
        "DevOps/SRE": 90,

        # Hardware & Physical Systems
        "HW": 93,
        "Silicon/ASIC Design": 95,
        "FPGA Engineering": 95,
        "Embedded Systems": 95,
        "Robotics/Controls": 90,

        # Data, AI, and Advanced Computing
        "AI/ML": 90,
        "Data Scientist": 87,
        "Data Engineer": 90,
        "Quantitative Developer": 87,
        "Quantitative Researcher": 80,

        # Product, Design, & Business Operations
        "PM": 88,
        "Technical Product Manager (TPM)": 93,
        "Product Designer / UX": 84,
        "Solutions Architect": 88,
        "Security/SecOps": 93,

        "Other": 60
    }

    role_score = role_scores.get(job["role_type"], 50)
    location_score = _score_location(job.get("location") or "")

    salary = job["salary"] or 0
    if salary >= 130000:
        compensation_score = 100
    elif salary >= 120000:
        compensation_score = 90
    elif salary >= 100000:
        compensation_score = 80
    elif salary >= 90000:
        compensation_score = 78
    elif salary >= 85000:
        compensation_score = 75
    else:
        compensation_score = 70
    if salary == 0:
        compensation_score = 75

    _CALI = ["san francisco", "santa clara", "san jose", "sunnyvale", "palo alto", "berkeley"]
    if any(c in (job.get("location") or "").lower() for c in _CALI):
        compensation_score -= 5

    if job.get("date_posted"):
        try:
            posted = date.fromisoformat(job["date_posted"])
            days_old = (date.today() - posted).days
            if days_old <= 1:
                freshness_score = 100
            elif days_old <= 3:
                freshness_score = 90
            elif days_old <= 7:
                freshness_score = 75
            elif days_old <= 14:
                freshness_score = 55
            elif days_old <= 30:
                freshness_score = 35
            else:
                freshness_score = 10
        except ValueError:
            freshness_score = 50
    else:
        freshness_score = 50

    final_score = (
        role_score         * weights["role_weight"] +
        location_score     * weights["location_weight"] +
        compensation_score * weights["compensation_weight"] +
        freshness_score    * weights["freshness_weight"]
    )

    return {
        "role_score": role_score,
        "location_score": location_score,
        "compensation_score": compensation_score,
        "freshness_score": freshness_score,
        "final_score": round(final_score, 2)
    }


def rank_jobs(jobs):
    weights = _load_weights()
    scored_jobs = []

    for job in jobs:
        scores = calculate_job_score(job, weights)
        scored_jobs.append({**job, **scores})

    scored_jobs.sort(key=lambda x: x["final_score"], reverse=True)
    return scored_jobs
