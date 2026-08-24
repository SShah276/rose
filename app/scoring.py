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


# Role desirability, 0-100. Tuned toward hardware / computer-engineering work:
# these values drive the score-ordered top-N window on /jobs, so a role scored
# below the SWE flood never reaches the page.
_ROLE_SCORES = {
    # Hardware, silicon & computer architecture — the target profile
    "Computer Architecture":  99,
    "Silicon/ASIC Design":    99,
    "FPGA Engineering":       98,
    "Embedded Systems":       98,
    "Hardware Verification":  97,
    "HW":                     96,
    "Analog/Mixed-Signal":    95,
    "Robotics/Controls":      93,

    # Low-level software — hardware-adjacent, still strongly preferred
    "Systems/Infra":          90,

    # General software
    "SWE":                    80,
    "Backend":                78,
    "DevOps/SRE":             68,
    "Fullstack":              68,
    "Mobile (iOS/Android)":   60,
    "Frontend":               55,

    # Data, AI & quant
    "AI/ML":                  78,
    "Quantitative Developer": 75,
    "Data Engineer":          70,
    "Quantitative Researcher":65,
    "Data Scientist":         60,

    # Product, design & security
    "Security/SecOps":                  70,
    "Technical Product Manager (TPM)":  65,
    "Solutions Architect":              55,
    "PM":                               50,
    "Product Designer / UX":            40,

    "Other": 45,
}


def calculate_job_score(job, weights: dict):
    role_score = _ROLE_SCORES.get(job["role_type"], 50)
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
