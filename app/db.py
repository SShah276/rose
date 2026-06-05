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
            pass  # Column already exists


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

    _setting_defaults = {
        "role_weight":             "0.27",
        "location_weight":         "0.19",
        "compensation_weight":     "0.19",
        "company_quality_weight":  "0.15",
        "growth_weight":           "0.07",
        "stability_weight":        "0.04",
        "freshness_weight":        "0.09",
    }
    for key, value in _setting_defaults.items():
        cursor.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value)
        )

    _migrate_v3(conn)
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
        company_quality,
        growth_score,
        stability_score,
        is_active
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            WHEN 'interview' THEN 1
            WHEN 'offer'     THEN 2
            WHEN 'applied'   THEN 3
            WHEN 'interested' THEN 4
            WHEN 'saved'     THEN 5
            WHEN 'rejected'  THEN 6
            WHEN 'skipped'   THEN 7
            ELSE 8
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
