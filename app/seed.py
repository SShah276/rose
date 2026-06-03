from db import init_db, insert_job, get_connection

def clear_jobs():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM applications")
    cursor.execute("DELETE FROM jobs")
    conn.commit()
    conn.close()


def seed_jobs():
    sample_jobs = [
        {
            "company": "Databricks",
            "title": "Software Engineer Intern",
            "location": "Chicago",
            "salary": 90000,
            "url": "https://example.com/databricks",
            "description": "Build backend systems.",
            "date_posted": "2026-06-01",
            "role_type": "SWE",
            "company_quality": 95,
            "growth_score": 90,
            "stability_score": 85
        },
        {
            "company": "Stripe",
            "title": "Software Engineer Intern",
            "location": "San Francisco",
            "salary": 95000,
            "url": "https://example.com/stripe",
            "description": "Work on payments infrastructure.",
            "date_posted": "2026-06-01",
            "role_type": "SWE",
            "company_quality": 90,
            "growth_score": 85,
            "stability_score": 80
        },
        {
            "company": "NVIDIA",
            "title": "Hardware Engineer Intern",
            "location": "Santa Clara",
            "salary": 92000,
            "url": "https://example.com/nvidia",
            "description": "Design hardware systems.",
            "date_posted": "2026-06-01",
            "role_type": "HW",
            "company_quality": 98,
            "growth_score": 95,
            "stability_score": 90
        },
        {
            "company": "OpenAI",
            "title": "AI/ML Intern",
            "location": "San Francisco",
            "salary": 100000,
            "url": "https://example.com/openai",
            "description": "Work on cutting-edge AI research.",
            "date_posted": "2026-06-01",
            "role_type": "AI/ML",
            "company_quality": 95,
            "growth_score": 99,
            "stability_score": 70
        },
        {
            "company": "Ramp",
            "title": "Product Manager Intern",
            "location": "New York",
            "salary": 80000,
            "url": "https://example.com/ramp",
            "description": "Support product roadmap and experiments.",
            "date_posted": "2026-06-01",
            "role_type": "PM",
            "company_quality": 85,
            "growth_score": 85,
            "stability_score": 75
        },
        {
            "company": "Jane Street",
            "title": "Software Engineer Intern",
            "location": "New York",
            "salary": 150000,
            "url": "https://example.com/janestreet",
            "description": "Develop high-frequency trading systems.",
            "date_posted": "2026-06-01",
            "role_type": "SWE",
            "company_quality": 99,
            "growth_score": 90,
            "stability_score": 95
        },
        {
            "company": "Citadel",
            "title": "AI/ML Intern",
            "location": "Chicago",
            "salary": 140000,
            "url": "https://example.com/citadel",
            "description": "Apply machine learning to quantitative strategy.",
            "date_posted": "2026-06-01",
            "role_type": "AI/ML",
            "company_quality": 97,
            "growth_score": 88,
            "stability_score": 92
        },
        {
            "company": "Apple",
            "title": "Hardware Engineer Intern",
            "location": "Santa Clara",
            "salary": 115000,
            "url": "https://example.com/apple",
            "description": "Prototyping next-generation silicon architecture.",
            "date_posted": "2026-06-01",
            "role_type": "HW",
            "company_quality": 96,
            "growth_score": 85,
            "stability_score": 95
        },
        {
            "company": "Google",
            "title": "Software Engineer Intern",
            "location": "New York",
            "salary": 110000,
            "url": "https://example.com/google",
            "description": "Optimize distributed search infrastructure.",
            "date_posted": "2026-06-01",
            "role_type": "SWE",
            "company_quality": 94,
            "growth_score": 80,
            "stability_score": 90
        },
        {
            "company": "Meta",
            "title": "AI/ML Intern",
            "location": "Remote",
            "salary": 135000,
            "url": "https://example.com/meta",
            "description": "Train large-scale recommendation models.",
            "date_posted": "2026-06-01",
            "role_type": "AI/ML",
            "company_quality": 93,
            "growth_score": 92,
            "stability_score": 85
        },
        {
            "company": "Snowflake",
            "title": "Software Engineer Intern",
            "location": "San Francisco",
            "salary": 105000,
            "url": "https://example.com/snowflake",
            "description": "Enhance cloud-native data warehousing engine.",
            "date_posted": "2026-06-01",
            "role_type": "SWE",
            "company_quality": 88,
            "growth_score": 85,
            "stability_score": 80
        },
        {
            "company": "Palantir",
            "title": "Software Engineer Intern",
            "location": "New York",
            "salary": 102000,
            "url": "https://example.com/palantir",
            "description": "Build deployment infrastructure for enterprise data fabrics.",
            "date_posted": "2026-06-01",
            "role_type": "SWE",
            "company_quality": 89,
            "growth_score": 87,
            "stability_score": 85
        },
        {
            "company": "AMD",
            "title": "Hardware Engineer Intern",
            "location": "Santa Clara",
            "salary": 98000,
            "url": "https://example.com/amd",
            "description": "Verify low-power microarchitecture design blocks.",
            "date_posted": "2026-06-01",
            "role_type": "HW",
            "company_quality": 85,
            "growth_score": 88,
            "stability_score": 88
        },
        {
            "company": "Duolingo",
            "title": "Product Manager Intern",
            "location": "Remote",
            "salary": 90000,
            "url": "https://example.com/duolingo",
            "description": "Design and A/B test gamification mechanics.",
            "date_posted": "2026-06-01",
            "role_type": "PM",
            "company_quality": 87,
            "growth_score": 84,
            "stability_score": 85
        },
        {
            "company": "Atlassian",
            "title": "Software Engineer Intern",
            "location": "Remote",
            "salary": 95000,
            "url": "https://example.com/atlassian",
            "description": "Develop collaboration tools scaling across platforms.",
            "date_posted": "2026-06-01",
            "role_type": "SWE",
            "company_quality": 86,
            "growth_score": 80,
            "stability_score": 85
        },
        {
            "company": "HubSpot",
            "title": "Product Manager Intern",
            "location": "Remote",
            "salary": 85000,
            "url": "https://example.com/hubspot",
            "description": "Define requirements for modern CRM integration portals.",
            "date_posted": "2026-06-01",
            "role_type": "PM",
            "company_quality": 84,
            "growth_score": 82,
            "stability_score": 83
        },
        {
            "company": "Qualcomm",
            "title": "Hardware Engineer Intern",
            "location": "San Diego",
            "salary": 88000,
            "url": "https://example.com/qualcomm",
            "description": "Assist with modern 5G/6G RF baseband processing layers.",
            "date_posted": "2026-06-01",
            "role_type": "HW",
            "company_quality": 83,
            "growth_score": 75,
            "stability_score": 89
        },
        {
            "company": "Anthropic",
            "title": "AI/ML Intern",
            "location": "San Francisco",
            "salary": 125000,
            "url": "https://example.com/anthropic",
            "description": "Investigate alignment protocols for frontier model reasoning.",
            "date_posted": "2026-06-01",
            "role_type": "AI/ML",
            "company_quality": 92,
            "growth_score": 98,
            "stability_score": 65
        },
        {
            "company": "Scale AI",
            "title": "AI/ML Intern",
            "location": "San Francisco",
            "salary": 112000,
            "url": "https://example.com/scaleai",
            "description": "Refine reinforcement learning pipelines for model evaluation.",
            "date_posted": "2026-06-01",
            "role_type": "AI/ML",
            "company_quality": 88,
            "growth_score": 95,
            "stability_score": 60
        },
        {
            "company": "Figma",
            "title": "Software Engineer Intern",
            "location": "San Francisco",
            "salary": 100000,
            "url": "https://example.com/figma",
            "description": "Implement high-performance multi-user rendering logic.",
            "date_posted": "2026-06-01",
            "role_type": "SWE",
            "company_quality": 90,
            "growth_score": 89,
            "stability_score": 80
        },
        {
            "company": "Vercel",
            "title": "Software Engineer Intern",
            "location": "Remote",
            "salary": 92000,
            "url": "https://example.com/vercel",
            "description": "Accelerate serverless edge compute route distributions.",
            "date_posted": "2026-06-01",
            "role_type": "SWE",
            "company_quality": 87,
            "growth_score": 91,
            "stability_score": 75
        },
        {
            "company": "StartupX",
            "title": "Software Engineer Intern",
            "location": "Remote",
            "salary": 70000,
            "url": "https://example.com/startupx",
            "description": "Help ship fast MVP iterations across fullstack interfaces.",
            "date_posted": "2026-06-01",
            "role_type": "SWE",
            "company_quality": 60,
            "growth_score": 70,
            "stability_score": 40
        },
        {
            "company": "BioTech_AI",
            "title": "AI/ML Intern",
            "location": "New York",
            "salary": 85000,
            "url": "https://example.com/biotechai",
            "description": "Analyze genomic sequence targets via neural networks.",
            "date_posted": "2026-06-01",
            "role_type": "AI/ML",
            "company_quality": 75,
            "growth_score": 85,
            "stability_score": 50
        },
        {
            "company": "CryptoMoon",
            "title": "Software Engineer Intern",
            "location": "Remote",
            "salary": 110000,
            "url": "https://example.com/cryptomoon",
            "description": "Write and audit complex EVM smart contracts.",
            "date_posted": "2026-06-01",
            "role_type": "SWE",
            "company_quality": 50,
            "growth_score": 90,
            "stability_score": 20
        },
        {
            "company": "LocalTech",
            "title": "Product Manager Intern",
            "location": "Chicago",
            "salary": 65000,
            "url": "https://example.com/localtech",
            "description": "Drive metrics for localized SMB management utilities.",
            "date_posted": "2026-06-01",
            "role_type": "PM",
            "company_quality": 55,
            "growth_score": 50,
            "stability_score": 70
        },
        {
            "company": "Robotics_Inc",
            "title": "Hardware Engineer Intern",
            "location": "Boston",
            "salary": 78000,
            "url": "https://example.com/roboticsinc",
            "description": "Debug low-level sensor telemetry actuator circuits.",
            "date_posted": "2026-06-01",
            "role_type": "HW",
            "company_quality": 78,
            "growth_score": 83,
            "stability_score": 55
        }
    ]

    for job in sample_jobs:
        insert_job(job)


if __name__ == "__main__":
    init_db()
    clear_jobs()
    seed_jobs()
    print("Database seeded successfully.")