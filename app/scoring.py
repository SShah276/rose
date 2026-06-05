from datetime import date
from app.db import get_setting


_DEFAULT_WEIGHTS = {
    "role_weight":            0.27,
    "location_weight":        0.19,
    "compensation_weight":    0.19,
    "company_quality_weight": 0.15,
    "growth_weight":          0.07,
    "stability_weight":       0.04,
    "freshness_weight":       0.09,
}


def _load_weights() -> dict:
    weights = {}
    for key, default in _DEFAULT_WEIGHTS.items():
        try:
            weights[key] = float(get_setting(key, str(default)))
        except (ValueError, TypeError):
            weights[key] = default
    return weights


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

    location_scores = {
        "Chicago": 99,
        "New York": 96,
        "Remote": 85,

        # California
        "San Francisco": 87,
        "Santa Clara": 85,
        "Los Angeles": 83,
        "San Jose": 85,
        "Sunnyvale": 85,
        "Palo Alto": 85,
        "Berkeley": 85,
        "San Diego": 85,

        # Major US Tech Hubs
        "Seattle": 93,
        "Bellevue": 93,
        "Austin": 93,
        "Boston": 93,

        # Secondary Hubs
        "Atlanta": 90,
        "Denver/Boulder": 90,
        "Miami": 83,
        "Pittsburgh": 80,
        "Washington DC": 79,
        "Raleigh/Durham": 83,
    }

    role_score = role_scores.get(job["role_type"], 50)
    location_score = location_scores.get(job["location"], 50)

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

    cali_cities = ["San Francisco", "Santa Clara", "San Jose", "Sunnyvale", "Palo Alto", "Berkeley"]
    if job["location"] in cali_cities:
        compensation_score -= 5

    company_quality_score = job["company_quality"]
    growth_score = job["growth_score"]
    stability_score = job["stability_score"]

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
        role_score              * weights["role_weight"] +
        location_score          * weights["location_weight"] +
        compensation_score      * weights["compensation_weight"] +
        company_quality_score   * weights["company_quality_weight"] +
        growth_score            * weights["growth_weight"] +
        stability_score         * weights["stability_weight"] +
        freshness_score         * weights["freshness_weight"]
    )

    return {
        "role_score": role_score,
        "location_score": location_score,
        "compensation_score": compensation_score,
        "company_quality_score": company_quality_score,
        "growth_score": growth_score,
        "stability_score": stability_score,
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
