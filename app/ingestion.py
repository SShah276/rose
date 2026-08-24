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
    
# Ordered (role_type, regex) rules — first match wins.
#
# Hardware / computer-engineering rules deliberately precede the software and
# AI/ML rules: "Hardware Engineer, AI Accelerators" is a hardware role, and
# "Embedded Software Engineer" is an embedded role, not a generic SWE one.
_ROLE_RULES = [
    # ── Hardware & computer architecture ──────────────────────────────────
    ("Computer Architecture", r"\b(computer|systems?|cpu|gpu|soc|processor|memory|cache|accelerator|performance|platform)\s+"
                              r"(micro)?architect(ure|s)?\b|\bmicroarchitecture\b"),
    ("Silicon/ASIC Design",   r"\b(asic|vlsi|rtl|silicon|soc|chip|semiconductor|integrated\s+circuit|"
                              r"physical\s+design|dft|design\s+for\s+test|static\s+timing|logic\s+synthesis|"
                              r"place\s*(and|&)\s*route|standard\s+cell|tape-?out|foundry|process\s+integration)\b"),
    ("FPGA Engineering",      r"\b(fpga|hdl|verilog|systemverilog|vhdl|digital\s+design|logic\s+design)\b"),
    ("Hardware Verification", r"\b(design\s+verification|hardware\s+verification|dv\s+engineer|verification\s+engineer|"
                              r"uvm|(post|pre)-?silicon\s+validation|silicon\s+bring-?up|hardware\s+validation|"
                              r"emulation\s+engineer)\b"),
    ("Analog/Mixed-Signal",   r"\b(analog|mixed[-\s]?signal|rf|radio\s+frequency|antenna|power\s+electronics|"
                              r"power\s+management|circuit\s+design|ic\s+design|photonics?|mems|"
                              r"optical\s+(packaging|engineer\w*|design|characteri[sz]ation)|"
                              r"high[-\s]?speed\s+(serdes|io|i/o))\b"),
    ("Embedded Systems",      r"\b(embedded|firmware|bare[-\s]?metal|rtos|device\s+driver|driver\s+(engineer|development)|"
                              r"board\s+support|bsp|bootloader|microcontroller|mcu|avionics|"
                              r"kernel\s+(engineer|developer|development))\b"),
    ("Robotics/Controls",     r"\b(robotics?|mechatronics?|controls?\s+(engineer|systems?|intern)|motion\s+control|"
                              r"autonomy|perception\s+engineer|guidance,?\s+navigation|gnc|actuator)\b"),
    ("HW",                    r"\b(hardware|electronics|pcb|printed\s+circuit|board\s+design|schematic\s+capture|"
                              r"electrical\s+(engineer\w*|test|design|power|systems?|hardware|reliability)|"
                              r"power\s+(systems?|integration|integrity|delivery)|signal\s+integrity|"
                              r"(board|bench|environmental|reliability|system)\s+(test|validation|bring-?up)|"
                              r"radiation\s+effects|cad\s+(engineer|design|librarian)|"
                              r"thermal\s+engineer|electro-?mechanical|computer\s+engineer\w*|ee)\b"),

    # ── Quantitative finance ──────────────────────────────────────────────
    ("Quantitative Developer",  r"\bquant\w*\b(?=.*\b(dev|developer|software|engineer|technology)\b)"),
    ("Quantitative Researcher", r"\bquant\w*\b(?=.*\b(research\w*|analyst|trading|trader|strateg\w*)\b)|\bquant\w*\b"),

    # ── Data, AI & machine learning ───────────────────────────────────────
    ("AI/ML",          r"\b(machine\s+learning|ml|mle|ai|a\.i\.|artificial\s+intelligence|deep\s+learning|"
                       r"llm|nlp|computer\s+vision|generative\s+ai)\b"),
    ("Data Engineer",  r"\bdata\s+(engineer\w*|platform|infrastructure)\b"),
    ("Data Scientist", r"\b(data\s+scientist|data\s+science)\b"),

    # ── Specialized software engineering & infrastructure ─────────────────
    ("Backend",              r"\b(backend|back-?end|server-?side|distributed\s+systems|api\s+engineer)\b"),
    ("Systems/Infra",        r"\b(systems?\s+(engineer|software|programming)|infra(structure)?|compiler|operating\s+system|"
                             r"performance\s+engineer|low-?level)\b"),
    ("Fullstack",            r"\b(full-?stack)\b"),
    ("Frontend",             r"\b(frontend|front-?end|ui|ux/ui|client-?side|web\s+develop\w*|react)\b"),
    ("Mobile (iOS/Android)", r"\b(mobile|ios|android|swift|kotlin)\b"),
    ("DevOps/SRE",           r"\b(devops|sre|site\s+reliability|platform\s+engineer|cloud\s+engineer)\b"),
    ("Security/SecOps",      r"\b(security|secops|cyber\w*|appsec|cryptograph\w*|penetration\s+test\w*)\b"),
    ("SWE",                  r"\b(software|swe|sde|developer|programmer)\b"),

    # ── Product, design & business operations ─────────────────────────────
    ("Technical Product Manager (TPM)", r"\b(tpm|technical\s+product\s+manag\w*|technical\s+program\s+manag\w*)\b"),
    ("PM",                              r"\b(product\s+manag\w*|product\s+owner|pm)\b"),
    ("Product Designer / UX",           r"\b(designer|ux|user\s+experience)\b"),
    ("Solutions Architect",             r"\b(solutions?\s+(architect|engineer)|sales\s+engineer)\b"),
]


def infer_role_type(title):
    """
    Map a job title to a role_type using the ordered rules above.

    Word boundaries matter: the previous bare-substring tests silently misfired
    ("ui" matched "circuit", "ai"/"ml" matched arbitrary words), which routed
    hardware titles into Frontend and AI/ML.
    """
    t = title.lower()
    for role, pattern in _ROLE_RULES:
        if re.search(pattern, t):
            return role
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