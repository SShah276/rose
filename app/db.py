import sqlite3
from pathlib import Path
from datetime import date

DB_PATH = Path(__file__).resolve().parent.parent / "jobs.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


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
        FOREIGN KEY(job_id) REFERENCES jobs(id)
    )
    """)

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
        applications.notes
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