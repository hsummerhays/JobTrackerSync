import csv
import os
import sqlite3
import pytest
from datetime import datetime, timedelta

from parse_jobs import handle_archive, clean_existing_tracker, parse_manual_job_block, save_to_sqlite
from utils import TRACKER_HEADERS

def test_parse_manual_job_block_extracts_requisition_id():
    text = """
CGI — Senior Full Stack Java Engineer
Job ID: J0926-1775
Recruiter/agency: Yatharth Singh / Mastech Digital
Location: Salt Lake City, onsite
Contract: 6 months, W-2
Rate: $57/hour
Conversion: CGI FTE at $115K base
RTR: Given to Mastech Digital
Status: Submission/prescreen process underway
"""
    result = parse_manual_job_block(text)
    assert result["company"] == "CGI"
    assert "Senior Full Stack Java Engineer" in result["position"]
    assert result["requisition_id"] == "J0926-1775"
    assert result["location"] == "Salt Lake City, onsite"


def test_archive_dry_run_and_execution(tmp_path):
    csv_file = tmp_path / "master_tracker.csv"
    db_file = tmp_path / "jobs.db"

    # Setup test rows:
    # 1. Old Expired (70 days old) -> Should archive
    # 2. Recent Expired (10 days old) -> Should NOT archive
    # 3. Old Rejected (100 days old) -> Should archive
    # 4. Recent Rejected (30 days old) -> Should NOT archive
    # 5. Active Applied (80 days old) -> Should NOT archive
    # 6. Cancelled / Do Not Pursue (40 days old) -> Should archive
    today = datetime.today().date()
    old_expired_date = (today - timedelta(days=70)).strftime("%Y-%m-%d")
    recent_expired_date = (today - timedelta(days=10)).strftime("%Y-%m-%d")
    old_rejected_date = (today - timedelta(days=100)).strftime("%Y-%m-%d")
    recent_rejected_date = (today - timedelta(days=30)).strftime("%Y-%m-%d")
    active_date = (today - timedelta(days=80)).strftime("%Y-%m-%d")
    cancelled_date = (today - timedelta(days=40)).strftime("%Y-%m-%d")

    test_jobs = [
        {"job_id": "job1", "company": "OldCorp", "position": "Dev", "location": "Remote", "date_added": old_expired_date, "tracker_status": "Expired", "source_pdf": "test.pdf", "notes": ""},
        {"job_id": "job2", "company": "RecentCorp", "position": "Dev", "location": "Remote", "date_added": recent_expired_date, "tracker_status": "Expired", "source_pdf": "test.pdf", "notes": ""},
        {"job_id": "job3", "company": "RejectCorp", "position": "Dev", "location": "Remote", "date_added": old_rejected_date, "tracker_status": "Rejected", "source_pdf": "test.pdf", "notes": ""},
        {"job_id": "job4", "company": "NewRejectCorp", "position": "Dev", "location": "Remote", "date_added": recent_rejected_date, "tracker_status": "Rejected", "source_pdf": "test.pdf", "notes": ""},
        {"job_id": "job5", "company": "ActiveCorp", "position": "Dev", "location": "Remote", "date_added": active_date, "tracker_status": "Applied", "source_pdf": "test.pdf", "notes": ""},
        {"job_id": "job6", "company": "CancelCorp", "position": "Dev", "location": "Remote", "date_added": cancelled_date, "tracker_status": "Cancelled", "source_pdf": "test.pdf", "notes": "Do Not Pursue"},
    ]

    # Save to SQLite and CSV
    save_to_sqlite(str(db_file), test_jobs)

    fieldnames = TRACKER_HEADERS
    with open(csv_file, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for j in test_jobs:
            writer.writerow({
                "Job ID": j["job_id"],
                "Date Added": j["date_added"],
                "Company": j["company"],
                "Position": j["position"],
                "Location": j["location"],
                "Tracker Status": j["tracker_status"],
                "Source PDF": j["source_pdf"],
                "Notes": j["notes"],
                "Archived": "No",
            })

    # 1. Dry run
    res_dry = handle_archive(dry_run=True, expired_days=60, rejected_days=90, db_path=str(db_file), tracker_csv=str(csv_file))
    assert res_dry == 0

    # Verify CSV and DB were unchanged by dry run
    with open(csv_file, mode="r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 6

    conn = sqlite3.connect(str(db_file))
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM jobs WHERE archived = 'Yes'")
    assert c.fetchone()[0] == 0
    conn.close()

    # 2. Live run
    res_live = handle_archive(dry_run=False, expired_days=60, rejected_days=90, db_path=str(db_file), tracker_csv=str(csv_file))
    assert res_live == 0

    # Verify CSV only contains the 3 active / recent rows (job2, job4, job5)
    with open(csv_file, mode="r", encoding="utf-8") as f:
        active_rows = list(csv.DictReader(f))
    active_ids = {r["Job ID"] for r in active_rows}
    assert active_ids == {"job2", "job4", "job5"}

    # Verify DB still contains all 6 rows (permanent system of record)
    conn = sqlite3.connect(str(db_file))
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM jobs")
    assert c.fetchone()[0] == 6

    c.execute("SELECT job_id, archived, archive_date FROM jobs WHERE archived = 'Yes'")
    archived_rows = c.fetchall()
    archived_ids = {r[0] for r in archived_rows}
    assert archived_ids == {"job1", "job3", "job6"}
    for r in archived_rows:
        assert r[1] == "Yes"
        assert r[2] == today.strftime("%Y-%m-%d")
    conn.close()

    # 3. Test clean_existing_tracker does NOT resurrect archived jobs from DB back into CSV
    clean_existing_tracker(str(csv_file), db_path=str(db_file))
    with open(csv_file, mode="r", encoding="utf-8") as f:
        synced_rows = list(csv.DictReader(f))
    synced_ids = {r["Job ID"] for r in synced_rows}
    assert synced_ids == {"job2", "job4", "job5"}

    # 4. Test unarchive
    res_unarchive = handle_archive(unarchive="job1", db_path=str(db_file), tracker_csv=str(csv_file))
    assert res_unarchive == 0

    # Verify job1 is now restored to CSV and cleared in DB
    with open(csv_file, mode="r", encoding="utf-8") as f:
        unarchived_rows = list(csv.DictReader(f))
    unarchived_ids = {r["Job ID"] for r in unarchived_rows}
    assert "job1" in unarchived_ids

    conn = sqlite3.connect(str(db_file))
    c = conn.cursor()
    c.execute("SELECT archived, archive_date FROM jobs WHERE job_id = 'job1'")
    archived_val, archive_date_val = c.fetchone()
    assert archived_val in ("No", "", None)
    assert archive_date_val in ("", None)
    conn.close()


def test_archive_targeted(tmp_path):
    csv_file = tmp_path / "master_tracker.csv"
    db_file = tmp_path / "jobs.db"

    test_jobs = [
        {"job_id": "target1", "company": "Acme", "position": "Dev", "location": "Remote", "date_added": "2026-09-01", "tracker_status": "Applied", "source_pdf": "test.pdf", "notes": ""},
        {"job_id": "target2", "company": "Beta", "position": "Dev", "location": "Remote", "date_added": "2026-09-01", "tracker_status": "Applied", "source_pdf": "test.pdf", "notes": ""},
    ]
    save_to_sqlite(str(db_file), test_jobs)

    fieldnames = TRACKER_HEADERS
    with open(csv_file, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for j in test_jobs:
            writer.writerow({
                "Job ID": j["job_id"],
                "Date Added": j["date_added"],
                "Company": j["company"],
                "Position": j["position"],
                "Location": j["location"],
                "Tracker Status": j["tracker_status"],
                "Source PDF": j["source_pdf"],
                "Notes": j["notes"],
                "Archived": "No",
            })

    # Unarchive non-existent
    res = handle_archive(unarchive="nonexistent", db_path=str(db_file), tracker_csv=str(csv_file))
    assert res == 0

    # Unarchive without target
    res_err = handle_archive(unarchive=True, target=None, db_path=str(db_file), tracker_csv=str(csv_file))
    assert res_err == 1

