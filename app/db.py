import sqlite3
from pathlib import Path
from datetime import date, timedelta

DB_PATH = Path(__file__).resolve().parent.parent / "jobs.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _migrate_v3(conn):
    """Add V3 columns to existing databases without losing data."""
    cursor = conn.cursor()
    for col, typedef in [("resume_used", "TEXT"), ("application_url", "TEXT")]:
        try:
            cursor.execute(f"ALTER TABLE applications ADD COLUMN {col} {typedef}")
        except sqlite3.OperationalError:
            pass


def _migrate_v6(conn):
    """Add V6 foundation columns: job_type, sponsorship, pay_raw on jobs table."""
    cursor = conn.cursor()
    for col, typedef in [
        ("job_type",    "TEXT DEFAULT ''"),
        ("sponsorship", "TEXT DEFAULT 'unknown'"),
        ("pay_raw",     "TEXT DEFAULT ''"),
    ]:
        try:
            cursor.execute(f"ALTER TABLE jobs ADD COLUMN {col} {typedef}")
        except sqlite3.OperationalError:
            pass


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company TEXT NOT NULL,
        title TEXT NOT NULL,
        location TEXT,
        salary INTEGER,
        url TEXT,
        source TEXT,
        source_url TEXT,
        external_id TEXT,
        dedupe_key TEXT UNIQUE,
        description TEXT,
        date_posted TEXT,
        date_found TEXT,
        role_type TEXT,
        company_quality INTEGER,
        growth_score INTEGER,
        stability_score INTEGER,
        is_active INTEGER DEFAULT 1
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS applications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id INTEGER UNIQUE,
        status TEXT DEFAULT 'not_applied',
        date_applied TEXT,
        follow_up_date TEXT,
        notes TEXT,
        resume_used TEXT,
        application_url TEXT,
        FOREIGN KEY(job_id) REFERENCES jobs(id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """)

    _weight_defaults = {
        "role_weight":         "0.40",
        "location_weight":     "0.25",
        "compensation_weight": "0.25",
        "freshness_weight":    "0.10",
    }
    # Remove deprecated weight keys from old 7-factor scoring
    cursor.execute(
        "DELETE FROM settings WHERE key IN ('company_quality_weight', 'growth_weight', 'stability_weight')"
    )
    # Seed missing weight keys
    for key, value in _weight_defaults.items():
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))
    # If existing weights don't sum to ~1.0 (e.g. leftover from 7-factor era), reset to new defaults
    rows = cursor.execute(
        "SELECT value FROM settings WHERE key IN ('role_weight','location_weight','compensation_weight','freshness_weight')"
    ).fetchall()
    if rows and abs(sum(float(r[0]) for r in rows) - 1.0) > 0.05:
        for key, value in _weight_defaults.items():
            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS candidate_profile (
        id          INTEGER PRIMARY KEY DEFAULT 1,
        name        TEXT DEFAULT '',
        email       TEXT DEFAULT '',
        school      TEXT DEFAULT '',
        degree      TEXT DEFAULT '',
        graduation_year TEXT DEFAULT '',
        gpa         TEXT DEFAULT '',
        personal_summary TEXT DEFAULT '',
        skills      TEXT DEFAULT '',
        experience  TEXT DEFAULT '',
        projects    TEXT DEFAULT '',
        strongest_bullets TEXT DEFAULT '',
        preferred_roles   TEXT DEFAULT '',
        resume_v1_name TEXT DEFAULT 'SWE General',
        resume_v2_name TEXT DEFAULT 'Data / ML',
        resume_v3_name TEXT DEFAULT 'Hardware / Embedded',
        resume_v4_name TEXT DEFAULT 'PM / Product',
        updated_at  TEXT
    )
    """)

    cursor.execute("INSERT OR IGNORE INTO candidate_profile (id) VALUES (1)")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ai_outputs (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id      INTEGER NOT NULL,
        type        TEXT NOT NULL,
        content     TEXT NOT NULL,
        created_at  TEXT NOT NULL,
        updated_at  TEXT,
        approved    INTEGER DEFAULT 0,
        FOREIGN KEY(job_id) REFERENCES jobs(id)
    )
    """)

    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_ai_outputs_job_type ON ai_outputs(job_id, type)"
    )

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS contacts (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        company          TEXT NOT NULL,
        name             TEXT NOT NULL,
        title            TEXT,
        email            TEXT,
        linkedin_url     TEXT,
        source           TEXT DEFAULT 'manual',
        confidence_score INTEGER DEFAULT 100,
        notes            TEXT,
        created_at       TEXT NOT NULL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS job_contacts (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id            INTEGER NOT NULL,
        contact_id        INTEGER NOT NULL,
        relationship_type TEXT DEFAULT 'recruiter',
        status            TEXT DEFAULT 'not_contacted',
        message_content   TEXT,
        date_sent         TEXT,
        follow_up_date    TEXT,
        response_notes    TEXT,
        created_at        TEXT NOT NULL,
        FOREIGN KEY(job_id)    REFERENCES jobs(id),
        FOREIGN KEY(contact_id) REFERENCES contacts(id),
        UNIQUE(job_id, contact_id)
    )
    """)

    _migrate_v3(conn)
    _migrate_v6(conn)
    conn.commit()
    conn.close()


def get_all_jobs():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT
        jobs.*,
        applications.status,
        applications.date_applied,
        applications.follow_up_date,
        applications.notes,
        applications.resume_used,
        applications.application_url
    FROM jobs
    LEFT JOIN applications ON jobs.id = applications.job_id
    WHERE jobs.is_active = 1
    """)

    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_job_by_dedupe_key(dedupe_key):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM jobs WHERE dedupe_key = ?", (dedupe_key,))
    row = cursor.fetchone()

    conn.close()
    return dict(row) if row else None


def insert_job(job_data):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO jobs (
        company,
        title,
        location,
        salary,
        url,
        source,
        source_url,
        external_id,
        dedupe_key,
        description,
        date_posted,
        date_found,
        role_type,
        job_type,
        sponsorship,
        pay_raw,
        company_quality,
        growth_score,
        stability_score,
        is_active
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        job_data["company"],
        job_data["title"],
        job_data.get("location"),
        job_data.get("salary"),
        job_data.get("url"),
        job_data.get("source"),
        job_data.get("source_url"),
        job_data.get("external_id"),
        job_data.get("dedupe_key"),
        job_data.get("description"),
        job_data.get("date_posted"),
        job_data.get("date_found", str(date.today())),
        job_data.get("role_type"),
        job_data.get("job_type", ""),
        job_data.get("sponsorship", "unknown"),
        job_data.get("pay_raw", ""),
        job_data.get("company_quality", 50),
        job_data.get("growth_score", 50),
        job_data.get("stability_score", 50),
        job_data.get("is_active", 1)
    ))

    job_id = cursor.lastrowid

    cursor.execute("""
    INSERT OR IGNORE INTO applications (job_id, status, date_applied, follow_up_date, notes)
    VALUES (?, 'not_applied', NULL, NULL, '')
    """, (job_id,))

    conn.commit()
    conn.close()


def update_job_by_dedupe_key(dedupe_key, job_data):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    UPDATE jobs
    SET
        company = ?,
        title = ?,
        location = ?,
        salary = ?,
        url = ?,
        source = ?,
        source_url = ?,
        external_id = ?,
        description = ?,
        date_posted = ?,
        date_found = ?,
        role_type = ?,
        job_type = ?,
        sponsorship = ?,
        pay_raw = ?,
        company_quality = ?,
        growth_score = ?,
        stability_score = ?,
        is_active = ?
    WHERE dedupe_key = ?
    """, (
        job_data["company"],
        job_data["title"],
        job_data.get("location"),
        job_data.get("salary"),
        job_data.get("url"),
        job_data.get("source"),
        job_data.get("source_url"),
        job_data.get("external_id"),
        job_data.get("description"),
        job_data.get("date_posted"),
        job_data.get("date_found", str(date.today())),
        job_data.get("role_type"),
        job_data.get("job_type", ""),
        job_data.get("sponsorship", "unknown"),
        job_data.get("pay_raw", ""),
        job_data.get("company_quality", 50),
        job_data.get("growth_score", 50),
        job_data.get("stability_score", 50),
        job_data.get("is_active", 1),
        dedupe_key
    ))

    conn.commit()
    conn.close()


def upsert_job(job_data):
    existing_job = get_job_by_dedupe_key(job_data["dedupe_key"])

    if existing_job:
        update_job_by_dedupe_key(job_data["dedupe_key"], job_data)
        return "updated"
    else:
        insert_job(job_data)
        return "inserted"


def set_job_salary(job_id: int, salary: int | None, pay_raw: str = ""):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE jobs SET salary = ?, pay_raw = ? WHERE id = ?", (salary, pay_raw, job_id))
    conn.commit()
    conn.close()


def update_application(job_id: int, **fields):
    allowed = {"status", "date_applied", "follow_up_date", "notes", "resume_used", "application_url"}
    safe = {k: v for k, v in fields.items() if k in allowed}
    if not safe:
        return
    conn = get_connection()
    cursor = conn.cursor()
    set_clause = ", ".join(f"{k} = ?" for k in safe)
    cursor.execute(
        f"UPDATE applications SET {set_clause} WHERE job_id = ?",
        list(safe.values()) + [job_id]
    )
    conn.commit()
    conn.close()


def get_followups_due() -> list:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT jobs.id, jobs.company, jobs.title, jobs.url,
               applications.status, applications.date_applied, applications.follow_up_date
        FROM jobs
        JOIN applications ON jobs.id = applications.job_id
        WHERE applications.status IN ('applied', 'interview')
          AND applications.follow_up_date IS NOT NULL
          AND applications.follow_up_date <= ?
          AND jobs.is_active = 1
        ORDER BY applications.follow_up_date ASC
    """, (str(date.today()),))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_tracked_applications() -> list:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT jobs.id, jobs.company, jobs.title, jobs.location, jobs.role_type, jobs.url,
               applications.status, applications.date_applied, applications.follow_up_date,
               applications.notes, applications.application_url, applications.resume_used
        FROM applications
        JOIN jobs ON jobs.id = applications.job_id
        WHERE applications.status NOT IN ('not_applied', 'not_reviewed')
          AND jobs.is_active = 1
        ORDER BY
          CASE applications.status
            WHEN 'interview'  THEN 1
            WHEN 'offer'      THEN 2
            WHEN 'applied'    THEN 3
            WHEN 'interested' THEN 4
            WHEN 'saved'      THEN 5
            WHEN 'rejected'   THEN 6
            WHEN 'closed'     THEN 7
            WHEN 'skipped'    THEN 8
            ELSE 9
          END,
          applications.date_applied DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_stats() -> dict:
    conn = get_connection()
    cursor = conn.cursor()
    today = str(date.today())
    week_ago = str(date.today() - timedelta(days=7))

    cursor.execute("SELECT COUNT(*) FROM jobs WHERE is_active = 1")
    total_jobs = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM applications WHERE status = 'applied' AND date_applied >= ?", (week_ago,))
    applied_week = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM applications WHERE status NOT IN ('not_applied', 'not_reviewed', 'skipped', 'interested', 'saved')")
    total_applied = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM applications WHERE status IN ('interview', 'offer')")
    interviews = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM applications WHERE status = 'offer'")
    offers = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*) FROM applications
        WHERE status IN ('applied', 'interview')
          AND follow_up_date IS NOT NULL
          AND follow_up_date <= ?
    """, (today,))
    followups_due = cursor.fetchone()[0]

    conn.close()

    interview_rate = round(interviews / total_applied * 100, 1) if total_applied > 0 else 0

    return {
        "total_jobs":    total_jobs,
        "total_applied": total_applied,
        "applied_week":  applied_week,
        "interviews":    interviews,
        "offers":        offers,
        "interview_rate": interview_rate,
        "followups_due": followups_due,
    }


def reset_all_statuses():
    """Testing helper: wipe all application tracking data, set every status to not_applied."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE applications
        SET status = 'not_applied', date_applied = NULL, follow_up_date = NULL,
            notes = '', resume_used = NULL, application_url = NULL
    """)
    conn.commit()
    conn.close()


def restore_skipped():
    """Testing helper: un-skip all skipped jobs, setting them back to not_applied."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE applications SET status = 'not_applied' WHERE status = 'skipped'")
    conn.commit()
    conn.close()


def get_setting(key: str, default: str = "") -> str:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key: str, value: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value)
    )
    conn.commit()
    conn.close()


# ---------- candidate profile ----------

_PROFILE_FIELDS = [
    "name", "email", "school", "degree", "graduation_year", "gpa",
    "personal_summary", "skills", "experience", "projects",
    "strongest_bullets", "preferred_roles",
    "resume_v1_name", "resume_v2_name", "resume_v3_name", "resume_v4_name",
]


def get_profile() -> dict:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM candidate_profile WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else {}


def save_profile(data: dict):
    allowed = {k: data.get(k, "") for k in _PROFILE_FIELDS}
    allowed["updated_at"] = str(date.today())
    conn = get_connection()
    cursor = conn.cursor()
    set_clause = ", ".join(f"{k} = ?" for k in allowed)
    cursor.execute(
        f"UPDATE candidate_profile SET {set_clause} WHERE id = 1",
        list(allowed.values())
    )
    conn.commit()
    conn.close()


# ---------- AI outputs ----------

def get_ai_outputs(job_id: int) -> dict:
    """Returns {type: output_dict} for all AI outputs belonging to a job."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM ai_outputs WHERE job_id = ? ORDER BY created_at DESC", (job_id,))
    rows = cursor.fetchall()
    conn.close()
    return {row["type"]: dict(row) for row in rows}


def upsert_ai_output(job_id: int, output_type: str, content: str) -> int:
    now = str(date.today())
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO ai_outputs (job_id, type, content, created_at, approved)
        VALUES (?, ?, ?, ?, 0)
        ON CONFLICT(job_id, type) DO UPDATE SET
            content    = excluded.content,
            updated_at = excluded.created_at,
            approved   = 0
    """, (job_id, output_type, content, now))
    output_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return output_id


def save_ai_output_content(output_id: int, content: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE ai_outputs SET content = ?, updated_at = ? WHERE id = ?",
        (content, str(date.today()), output_id)
    )
    conn.commit()
    conn.close()


def toggle_ai_output_approved(output_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE ai_outputs SET approved = 1 - approved WHERE id = ?", (output_id,))
    conn.commit()
    conn.close()


# ---------- contacts ----------

_CONTACT_FIELDS = ["company", "name", "title", "email", "linkedin_url", "source", "confidence_score", "notes"]


def get_all_contacts() -> list:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.*, COUNT(jc.id) as linked_jobs
        FROM contacts c
        LEFT JOIN job_contacts jc ON jc.contact_id = c.id
        GROUP BY c.id
        ORDER BY c.company, c.name
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_contact(contact_id: int) -> dict:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else {}


def insert_contact(data: dict) -> int:
    safe = {k: data.get(k, "") for k in _CONTACT_FIELDS}
    safe["confidence_score"] = int(safe.get("confidence_score") or 100)
    safe["created_at"] = str(date.today())
    conn = get_connection()
    cursor = conn.cursor()
    cols = ", ".join(safe.keys())
    placeholders = ", ".join("?" for _ in safe)
    cursor.execute(f"INSERT INTO contacts ({cols}) VALUES ({placeholders})", list(safe.values()))
    contact_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return contact_id


def update_contact(contact_id: int, data: dict):
    safe = {k: data.get(k, "") for k in _CONTACT_FIELDS}
    safe["confidence_score"] = int(safe.get("confidence_score") or 100)
    conn = get_connection()
    cursor = conn.cursor()
    set_clause = ", ".join(f"{k} = ?" for k in safe)
    cursor.execute(f"UPDATE contacts SET {set_clause} WHERE id = ?", list(safe.values()) + [contact_id])
    conn.commit()
    conn.close()


def delete_contact(contact_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM job_contacts WHERE contact_id = ?", (contact_id,))
    cursor.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))
    conn.commit()
    conn.close()


# ---------- job_contacts ----------

def get_contacts_for_job(job_id: int) -> list:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT jc.*, c.name as contact_name, c.title as contact_title,
               c.email, c.linkedin_url, c.company as contact_company
        FROM job_contacts jc
        JOIN contacts c ON c.id = jc.contact_id
        WHERE jc.job_id = ?
        ORDER BY CASE jc.relationship_type
            WHEN 'alumni'          THEN 1
            WHEN 'recruiter'       THEN 2
            WHEN 'hiring_manager'  THEN 3
            WHEN 'engineer'        THEN 4
            ELSE 5 END
    """, (job_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_jobs_for_contact(contact_id: int) -> list:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT jc.*, j.company, j.title as job_title, j.location, j.role_type, j.url
        FROM job_contacts jc
        JOIN jobs j ON j.id = jc.job_id
        WHERE jc.contact_id = ?
        ORDER BY jc.created_at DESC
    """, (contact_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def link_contact_to_job(job_id: int, contact_id: int, relationship_type: str = "recruiter") -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO job_contacts (job_id, contact_id, relationship_type, status, created_at)
        VALUES (?, ?, ?, 'not_contacted', ?)
    """, (job_id, contact_id, relationship_type, str(date.today())))
    jc_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return jc_id


def unlink_contact_from_job(jc_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM job_contacts WHERE id = ?", (jc_id,))
    conn.commit()
    conn.close()


def get_job_contact(jc_id: int) -> dict:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT jc.*, c.name as contact_name, c.title as contact_title,
               c.email, c.linkedin_url, c.company as contact_company,
               j.company as job_company, j.title as job_title, j.role_type
        FROM job_contacts jc
        JOIN contacts c ON c.id = jc.contact_id
        JOIN jobs j ON j.id = jc.job_id
        WHERE jc.id = ?
    """, (jc_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else {}


def update_job_contact(jc_id: int, **fields):
    allowed = {"status", "message_content", "date_sent", "follow_up_date", "response_notes"}
    safe = {k: v for k, v in fields.items() if k in allowed}
    if not safe:
        return
    conn = get_connection()
    cursor = conn.cursor()
    set_clause = ", ".join(f"{k} = ?" for k in safe)
    cursor.execute(f"UPDATE job_contacts SET {set_clause} WHERE id = ?", list(safe.values()) + [jc_id])
    conn.commit()
    conn.close()


def get_outreach_queue() -> dict:
    conn = get_connection()
    cursor = conn.cursor()
    today = str(date.today())

    cursor.execute("""
        SELECT jc.*, c.name as contact_name, c.title as contact_title,
               c.email, c.linkedin_url,
               j.company, j.title as job_title, j.id as job_id
        FROM job_contacts jc
        JOIN contacts c ON c.id = jc.contact_id
        JOIN jobs j ON j.id = jc.job_id
        WHERE jc.status = 'drafted'
        ORDER BY jc.created_at DESC
    """)
    drafts = [dict(r) for r in cursor.fetchall()]

    cursor.execute("""
        SELECT jc.*, c.name as contact_name, c.title as contact_title,
               c.email, c.linkedin_url,
               j.company, j.title as job_title, j.id as job_id
        FROM job_contacts jc
        JOIN contacts c ON c.id = jc.contact_id
        JOIN jobs j ON j.id = jc.job_id
        WHERE jc.status = 'sent'
          AND jc.follow_up_date IS NOT NULL
          AND jc.follow_up_date <= ?
        ORDER BY jc.follow_up_date ASC
    """, (today,))
    follow_ups = [dict(r) for r in cursor.fetchall()]

    cursor.execute("""
        SELECT jc.*, c.name as contact_name, c.title as contact_title,
               j.company, j.title as job_title, j.id as job_id
        FROM job_contacts jc
        JOIN contacts c ON c.id = jc.contact_id
        JOIN jobs j ON j.id = jc.job_id
        WHERE jc.status = 'responded'
        ORDER BY jc.date_sent DESC
    """)
    responded = [dict(r) for r in cursor.fetchall()]

    conn.close()
    return {"drafts": drafts, "follow_ups": follow_ups, "responded": responded}
