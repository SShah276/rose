import csv
import io
import re
from datetime import date

from app.db import upsert_job


def clean_text(value):
    if value is None:
        return ""
    return str(value).strip()


def parse_salary(value) -> int | None:
    """
    Parse a salary string into an annual integer.

    Handles:
      - Hourly: "$25/hr", "$25.50 per hour", "25 hourly"  → × 2080
      - Range:  "100K–120K", "$100,000-$120,000"          → midpoint
      - Single: "95000", "$95k"
    """
    if not value:
        return None
    text = str(value).strip()

    # Hourly rate
    hourly = re.search(
        r"\$?([\d,]+(?:\.\d+)?)\s*(?:/hr\b|per\s*hour|/hour\b|\bhourly\b)",
        text, re.IGNORECASE,
    )
    if hourly:
        rate = float(hourly.group(1).replace(",", ""))
        return int(rate * 2080)

    # Strip $ and commas; expand K notation
    clean = re.sub(r"\$|,", "", text)
    clean = re.sub(r"(\d+(?:\.\d+)?)\s*[kK]\b",
                   lambda m: str(int(float(m.group(1)) * 1000)), clean)

    # Range: 100000-120000
    rng = re.match(r"(\d+)\s*[-–]\s*(\d+)", clean)
    if rng:
        lo, hi = int(rng.group(1)), int(rng.group(2))
        return (lo + hi) // 2

    # Single value — take first number
    num = re.match(r"[\d.]+", clean.strip())
    if num:
        try:
            return int(float(num.group(0)))
        except ValueError:
            pass

    return None
    
def infer_role_type(title):
    title_lower = title.lower()

    # --- 1. Quantitative Finance ---
    if "quant" in title_lower or "quantitative" in title_lower:
        if "dev" in title_lower or "software" in title_lower:
            return "Quantitative Developer"
        if "research" in title_lower or "analyst" in title_lower:
            return "Quantitative Researcher"

    # --- 2. Data, AI, and Machine Learning ---
    if "machine learning" in title_lower or "ml" in title_lower or "ai " in title_lower or title_lower.startswith("ai"):
        return "AI/ML"
    if "data scientist" in title_lower or "science" in title_lower:
        return "Data Scientist"
    if "data engineer" in title_lower:
        return "Data Engineer"

    # --- 3. Hardware & Physical Systems ---
    if "silicon" in title_lower or "asic" in title_lower:
        return "Silicon/ASIC Design"
    if "fpga" in title_lower:
        return "FPGA Engineering"
    if "embedded" in title_lower:
        return "Embedded Systems"
    if "robotics" in title_lower or "controls" in title_lower or "automation" in title_lower:
        return "Robotics/Controls"
    if "hardware" in title_lower or "electrical" in title_lower:
        return "HW"

    # --- 4. Specialized Software Engineering & Infrastructure ---
    if "backend" in title_lower:
        return "Backend"
    if "systems" in title_lower or "infra" in title_lower:
        return "Systems/Infra"
    if "fullstack" in title_lower or "full-stack" in title_lower:
        return "Fullstack"
    if "frontend" in title_lower or "ui" in title_lower:
        return "Frontend"
    if "mobile" in title_lower or "ios" in title_lower or "android" in title_lower:
        return "Mobile (iOS/Android)"
    if "devops" in title_lower or "sre" in title_lower or "reliability" in title_lower:
        return "DevOps/SRE"
    if "software" in title_lower or "swe" in title_lower or "developer" in title_lower:
        return "SWE"

    # --- 5. Product, Design, & Business Operations ---
    if "tpm" in title_lower or "technical product manager" in title_lower:
        return "Technical Product Manager (TPM)"
    if "product manager" in title_lower or title_lower == "pm" or "product" in title_lower:
        return "PM"
    if "designer" in title_lower or "ux" in title_lower or "ui/ux" in title_lower:
        return "Product Designer / UX"
    if "solutions architect" in title_lower or "solutions engineer" in title_lower:
        return "Solutions Architect"
    if "security" in title_lower or "secops" in title_lower or "cyber" in title_lower:
        return "Security/SecOps"

    # --- 6. Fallback ---
    return "Other"

def make_dedupe_key(company, title, location=""):
    # Location excluded — it varies too much across sources for the same posting
    return f"{company.strip().lower()}|{title.strip().lower()}"


def normalize_job(raw_row, source="csv", job_type=""):
    company = clean_text(raw_row.get("company", ""))
    title = clean_text(raw_row.get("title", ""))
    location = clean_text(raw_row.get("location", "")) or "Unknown"

    if not company or not title:
        raise ValueError("Missing required fields: company or title")

    pay_raw = clean_text(raw_row.get("pay_raw", ""))
    salary_str = clean_text(raw_row.get("salary", ""))
    # pay_raw takes precedence; salary_str is the fallback (numeric string or raw)
    salary = parse_salary(pay_raw or salary_str)

    url = clean_text(raw_row.get("url", ""))
    description = clean_text(raw_row.get("description", ""))
    date_posted = clean_text(raw_row.get("date_posted", ""))

    role_type = infer_role_type(title)
    dedupe_key = make_dedupe_key(company, title, location)

    return {
        "company": company,
        "title": title,
        "location": location,
        "salary": salary,
        "pay_raw": pay_raw,
        "url": url,
        "source": source,
        "source_url": "",
        "external_id": "",
        "dedupe_key": dedupe_key,
        "description": description,
        "date_posted": date_posted,
        "date_found": str(date.today()),
        "role_type": role_type,
        "job_type": job_type or raw_row.get("job_type", ""),
        "sponsorship": raw_row.get("sponsorship", "unknown"),
        "company_quality": 50,
        "growth_score": 50,
        "stability_score": 50,
        "is_active": 1
    }


def import_jobs_from_csv_bytes(file_bytes):
    decoded = file_bytes.decode("utf-8")
    csv_file = io.StringIO(decoded)
    reader = csv.DictReader(csv_file)

    summary = {
        "rows_read": 0,
        "inserted": 0,
        "updated": 0,
        "skipped": 0,
        "errors": []
    }

    for row_num, row in enumerate(reader, start=2):
        summary["rows_read"] += 1

        try:
            normalized_job = normalize_job(row, source="csv")
            result = upsert_job(normalized_job)

            if result == "inserted":
                summary["inserted"] += 1
            elif result == "updated":
                summary["updated"] += 1

        except Exception as e:
            summary["skipped"] += 1
            summary["errors"].append(f"Row {row_num}: {str(e)}")

    return summary