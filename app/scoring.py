def calculate_job_score(job):
    role_scores = {
        # Software & Systems Engineering (Top Tier Base)
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
        "AI/ML": 90,          # Kept matching your log output
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
        # Your Core Favorites
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
        "San Diego": 85,       # Big hardware/qualcomm presence
        
        # Major US Tech Hubs (High Density)
        "Seattle": 93,        # No state income tax boost
        "Bellevue": 93,
        "Austin": 93,         # Strong tech scene, lower cost than coasts
        "Boston": 93,         # Massive robotics/biotech hub

        # Emerging & Secondary US Tech Hubs
        "Atlanta": 90,
        "Denver/Boulder": 90,
        "Miami": 83,
        "Pittsburgh": 80,     # Autonomous vehicles/AI hub
        "Washington DC": 79,   # Defense tech/Aerospace
        "Raleigh/Durham": 83,  # Research Triangle Park
    }

    role_score = role_scores.get(job["role_type"], 50)
    location_score = location_scores.get(job["location"], 60)

    salary = job["salary"]
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
    
    cali_cities = ["San Francisco", "Santa Clara", "San Jose", "Sunnyvale", "Palo Alto", "Berkeley"]
    is_cali = job["location"] in cali_cities

    if is_cali:
        compensation_score -= 5

    company_quality_score = job["company_quality"]
    growth_score = job["growth_score"]
    stability_score = job["stability_score"]

    final_score = (
        role_score * 0.29 +
        location_score * 0.21 +
        compensation_score * 0.21 +
        company_quality_score * 0.17 +
        growth_score * 0.08 +
        stability_score * 0.04
    )

    return {
        "role_score": role_score,
        "location_score": location_score,
        "compensation_score": compensation_score,
        "company_quality_score": company_quality_score,
        "growth_score": growth_score,
        "stability_score": stability_score,
        "final_score": round(final_score, 2)
    }


def rank_jobs(jobs):
    scored_jobs = []

    for job in jobs:
        scores = calculate_job_score(job)
        scored_jobs.append({**job, **scores})

    scored_jobs.sort(key=lambda x: x["final_score"], reverse=True)
    return scored_jobs