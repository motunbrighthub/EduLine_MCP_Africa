"""
One-off migration: copy students and results from the old SQLite eduline.db into MySQL.

Old passwords were stored in plain text. This script hashes them on the way in, so
existing students can keep logging in with the same Student ID and password.

Usage:
    set MYSQL_HOST=... MYSQL_PORT=3306 MYSQL_USER=... MYSQL_PASSWORD=... MYSQL_DATABASE=eduline
    python migrate_sqlite_to_mysql.py eduline.db

Safe to re-run: existing students and already-copied results are skipped.
"""
import hashlib
import os
import secrets
import sqlite3
import sys
from datetime import datetime

import mysql.connector

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# Same format as app.py. 
PBKDF2_ITERATIONS = 200_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def parse_dt(value):
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return datetime.now()


USERS_DDL = """
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_uuid VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(100),
    area VARCHAR(10),
    password_hash VARCHAR(255) NOT NULL,
    created_at DATETIME NOT NULL
) CHARACTER SET utf8mb4
"""
RESULTS_DDL = """
CREATE TABLE IF NOT EXISTS results (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_uuid VARCHAR(20) NOT NULL,
    subject VARCHAR(50),
    score INT,
    total_questions INT,
    progress DOUBLE,
    weak_clusters_json TEXT,
    taken_at DATETIME NOT NULL,
    INDEX idx_results_student (student_uuid, subject, taken_at)
) CHARACTER SET utf8mb4
"""


def main():
    sqlite_path = sys.argv[1] if len(sys.argv) > 1 else "eduline.db"
    if not os.path.exists(sqlite_path):
        sys.exit(f"SQLite file not found: {sqlite_path}")

    src = sqlite3.connect(sqlite_path)
    dst = mysql.connector.connect(
        host=os.environ.get("MYSQL_HOST", "localhost"),
        port=int(os.environ.get("MYSQL_PORT", 3306)),
        user=os.environ["MYSQL_USER"],
        password=os.environ.get("MYSQL_PASSWORD"),
        database=os.environ.get("MYSQL_DATABASE", "EdulineDB"),
        charset="utf8mb4",
    )
    cur = dst.cursor()
    cur.execute(USERS_DDL)
    cur.execute(RESULTS_DDL)

    users_added = users_skipped = 0
    for student_uuid, name, area, password, created_at in src.execute(
        "SELECT student_uuid, name, area, password, created_at FROM users"
    ):
        stored = password if str(password).startswith("pbkdf2_sha256$") else hash_password(str(password))
        cur.execute(
            "INSERT IGNORE INTO users (student_uuid, name, area, password_hash, created_at) "
            "VALUES (%s, %s, %s, %s, %s)",
            (student_uuid, name, area, stored, parse_dt(created_at)),
        )
        if cur.rowcount:
            users_added += 1
        else:
            users_skipped += 1

    results_added = results_skipped = 0
    for student_uuid, subject, score, total, progress, weak_json, taken_at in src.execute(
        "SELECT student_uuid, subject, score, total_questions, progress, weak_clusters_json, taken_at FROM results"
    ):
        taken = parse_dt(taken_at)
        cur.execute(
            "SELECT 1 FROM results WHERE student_uuid=%s AND subject=%s AND taken_at=%s LIMIT 1",
            (student_uuid, subject, taken),
        )
        if cur.fetchone():
            results_skipped += 1
            continue
        cur.execute(
            "INSERT INTO results (student_uuid, subject, score, total_questions, progress, "
            "weak_clusters_json, taken_at) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (student_uuid, subject, score, total, progress, weak_json, taken),
        )
        results_added += 1

    dst.commit()
    cur.close()
    dst.close()
    src.close()
    print(f"Users: {users_added} added, {users_skipped} already present")
    print(f"Results: {results_added} added, {results_skipped} already present")


if __name__ == "__main__":
    main()
