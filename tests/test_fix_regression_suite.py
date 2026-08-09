import csv
import pytest
import sqlite3
from parse_jobs import (
    evaluate_job,
    compute_priority,
    _find_skills,
    parse_job_cards_from_text,
    handle_rescore,
)


def test_utah_detection():
    """Southlake, TX must not match Utah; Salt Lake City, UT must."""
    job_southlake = {
        "title": "Software Engineer",
        "company": "Test Company",
        "location": "Southlake, TX (Hybrid)",
        "raw_context": "Software Engineer Test Company Southlake, TX (Hybrid)",
    }
    job_slc = {
        "title": "Software Engineer",
        "company": "Test Company",
        "location": "Salt Lake City, UT (Hybrid)",
        "raw_context": "Software Engineer Test Company Salt Lake City, UT (Hybrid)",
    }

    _, _, notes_tx, _, _, _, _, reason_tx, _, _, _ = evaluate_job(job_southlake)
    _, _, notes_ut, _, _, _, _, reason_ut, _, _, _ = evaluate_job(job_slc)

    assert "Rule 6: Relocation required" in notes_tx
    assert "Rule 6: Relocation required" not in notes_ut


def test_aggregator_listings_capped_at_p3():
    """Jobs from Ladders, jobs.utah.gov, or DailySummary listings must never exceed ★★★☆☆ Maybe."""
    job_ladders = {
        "title": "Senior Software Engineer (.NET/Vue.js)",
        "company": "Amazing Tech",
        "location": "Remote",
        "provider": "Ladders",
        "raw_context": "Senior Software Engineer .NET Vue.js Remote Amazing Tech",
    }
    _, _, _, _, _, _, recommendation_ladders, _, _, _, _ = evaluate_job(job_ladders)
    assert recommendation_ladders == "★★★☆☆ Maybe"

    job_daily = {
        "title": "Senior Software Engineer (.NET/Vue.js)",
        "company": "Jobs.utah.gov-DailySummary",
        "location": "Salt Lake City, UT",
        "raw_context": "Senior Software Engineer .NET Vue.js Salt Lake City, UT Jobs.utah.gov-DailySummary",
    }
    _, _, _, _, _, _, recommendation_daily, _, _, _, _ = evaluate_job(job_daily)
    assert recommendation_daily == "★★★☆☆ Maybe"


def test_action_apply_cannot_elevate_low_skip_to_p2():
    """Skip/Low recommendations must always produce P4 regardless of Action = Apply."""
    assert compute_priority("★☆☆☆☆ Skip", "Apply") == "P4 – Ignore"
    assert compute_priority("★★☆☆☆ Low", "Apply") == "P4 – Ignore"
    assert compute_priority("★★★☆☆ Maybe", "Apply") == "P3 – Investigate"
    assert compute_priority("★★★★☆ Strong", "Apply") == "P2 – Apply this week"


def test_vue_aliases_normalize_correctly():
    """'Vue', 'vue.js', 'vuejs' must resolve to a vue-named skill; 'Nuxt' is detected separately
    as its own skill (the alias mapping from nuxt → Vue.js happens at scoring time, not in _find_skills)."""
    for text in [
        "We need someone with Vue experience",
        "We need someone with Vue.js experience",
        "We need someone with Vuejs experience",
    ]:
        skills_lower = [s.lower() for s in _find_skills(text)]
        assert any("vue" in s for s in skills_lower), f"Vue not found in skills for: {text!r}"

    # Nuxt is detected as its own skill entry; the alias to Vue.js applies at scoring time
    nuxt_skills = [s.lower() for s in _find_skills("We need someone with Nuxt experience")]
    assert "nuxt" in nuxt_skills or any("vue" in s for s in nuxt_skills), \
        "Nuxt (or its Vue.js alias) not found in skills"


def test_porch_software_metadata_parses_correctly():
    """Email metadata 'Years Exp Required' must not become the company name."""
    text = (
        "Porch Software\n"
        "Years Exp Required\n"
        "Mid/Senior Full Stack Developer (C#/Vuejs) - Minimum 5\n"
        "Salt Lake City, UT 84020 (Remote)"
    )
    jobs = parse_job_cards_from_text(text)
    assert len(jobs) == 1
    assert jobs[0]["company"] == "Porch Software"
    assert "Mid/Senior Full Stack Developer" in jobs[0]["title"]


def test_rescore_idempotency_and_preservation(tmp_path):
    """
    5. --rescore must be idempotent (running it twice produces identical rows).
    6. Rescoring must preserve manual statuses, notes, and recruiter information.
    8. Applied/interviewing jobs must not revert to 'New'.
    """
    db_path = tmp_path / "test_jobs.db"
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute(
        """CREATE TABLE jobs (
        job_id TEXT PRIMARY KEY, review_status TEXT, job_type TEXT, company TEXT,
        position TEXT, location TEXT, url TEXT, provider TEXT, source_pdf TEXT,
        confidence TEXT, fit_score INTEGER, priority TEXT, company_type TEXT,
        recommendation TEXT, tracker_status TEXT, disposition TEXT, action TEXT,
        existing_company TEXT, reason TEXT, matched_skills TEXT, missing_skills TEXT,
        date_added TEXT, notes TEXT, recruiter TEXT, hiring_manager TEXT,
        last_seen TEXT, fingerprint TEXT, previous_job_id TEXT, raw_context TEXT
    )"""
    )
    c.execute(
        """
        INSERT INTO jobs (
            job_id, company, position, location, raw_context,
            tracker_status, notes, recruiter, matched_skills, missing_skills, action
        ) VALUES (
            'job1', 'Test Corp', 'Developer', 'Remote', 'Developer Test Corp Remote Vue.js',
            'Interviewing', 'Had a great first round', 'John Doe', 'Vue.js', '', 'Apply'
        )
        """
    )
    conn.commit()
    conn.close()

    # Redirect sqlite3.connect so handle_rescore operates on the temp DB
    original_connect = sqlite3.connect

    def mock_connect(*args, **kwargs):
        return original_connect(db_path)

    csv_path = tmp_path / "test_tracker.csv"

    sqlite3.connect = mock_connect
    try:
        handle_rescore(csv_path=str(csv_path))
        conn = original_connect(db_path)
        conn.row_factory = sqlite3.Row
        row1 = dict(conn.cursor().execute("SELECT * FROM jobs").fetchone())
        conn.close()

        handle_rescore(csv_path=str(csv_path))
        conn = original_connect(db_path)
        conn.row_factory = sqlite3.Row
        row2 = dict(conn.cursor().execute("SELECT * FROM jobs").fetchone())
        conn.close()
    finally:
        sqlite3.connect = original_connect

    # Idempotency
    assert row1 == row2

    # Preservation of manual fields
    assert row2["tracker_status"] == "Interviewing"
    assert row2["notes"] == "Had a great first round"
    assert row2["recruiter"] == "John Doe"

    # Must not revert to 'New'
    assert row2["tracker_status"] != "New"


def test_rescore_propagates_to_csv(tmp_path):
    """
    --rescore must write its corrected scores into master_tracker.csv, not just
    jobs.db. A row that was originally (mis-)scored as Utah/P2/Strong before a
    location-matching fix landed must come out of the CSV re-scored to
    "Out of state"/P4/Skip -- exactly like the row already in jobs.db -- so a
    later normal sync (which treats the CSV as the source of "existing" state)
    doesn't read the stale CSV value back into the DB and silently revert the
    rescore.
    """
    db_path = tmp_path / "test_jobs.db"
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute(
        """CREATE TABLE jobs (
        job_id TEXT PRIMARY KEY, review_status TEXT, job_type TEXT, company TEXT,
        position TEXT, location TEXT, url TEXT, provider TEXT, source_pdf TEXT,
        confidence TEXT, fit_score INTEGER, priority TEXT, company_type TEXT,
        recommendation TEXT, tracker_status TEXT, disposition TEXT, action TEXT,
        existing_company TEXT, reason TEXT, matched_skills TEXT, missing_skills TEXT,
        date_added TEXT, notes TEXT, recruiter TEXT, hiring_manager TEXT,
        last_seen TEXT, fingerprint TEXT, previous_job_id TEXT, raw_context TEXT
    )"""
    )
    c.execute(
        """
        INSERT INTO jobs (
            job_id, company, position, location, raw_context,
            tracker_status, action, fit_score, priority, recommendation, reason,
            matched_skills, missing_skills, company_type
        ) VALUES (
            'schwab1', 'Charles Schwab', 'Senior Backend Engineer (.NET)', 'Southlake, TX (Hybrid)', '',
            'New', 'Apply', 90, 'P2 - Apply this week', '****Star Strong',
            'Utah + .NET + Small company', '.NET', '', 'Small / Medium'
        )
        """
    )
    conn.commit()
    conn.close()

    csv_path = tmp_path / "test_tracker.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "Job ID", "Review Status", "Job Type", "Company", "Position", "Location", "URL", "Provider",
            "Source PDF", "Source Index", "Confidence", "Fit Score", "Priority", "Company Type",
            "Recommendation", "Tracker Status", "Disposition", "Action", "Existing Company",
            "Age (days)", "Reason", "Matched Skills", "Missing Skills", "Date Added", "Last Seen",
            "Notes", "Recruiter", "Hiring Manager", "Fingerprint", "Previous Job ID",
        ])
        writer.writeheader()
        writer.writerow({
            "Job ID": "schwab1", "Company": "Charles Schwab", "Position": "Senior Backend Engineer (.NET)",
            "Location": "Southlake, TX (Hybrid)", "Fit Score": "90", "Priority": "P2 - Apply this week",
            "Recommendation": "****Star Strong", "Reason": "Utah + .NET + Small company",
            "Matched Skills": ".NET", "Missing Skills": "", "Company Type": "Small / Medium",
            "Tracker Status": "New", "Action": "Apply", "Date Added": "2026-08-01",
        })

    original_connect = sqlite3.connect

    def mock_connect(*args, **kwargs):
        return original_connect(db_path)

    sqlite3.connect = mock_connect
    try:
        handle_rescore(csv_path=str(csv_path))
    finally:
        sqlite3.connect = original_connect

    conn = original_connect(db_path)
    conn.row_factory = sqlite3.Row
    db_row = dict(conn.cursor().execute("SELECT * FROM jobs WHERE job_id = 'schwab1'").fetchone())
    conn.close()

    with open(csv_path, newline="", encoding="utf-8") as f:
        csv_row = next(iter(csv.DictReader(f)))

    # jobs.db must reflect the out-of-state rejection
    assert db_row["priority"] == "P4 – Ignore"
    assert db_row["recommendation"] == "★☆☆☆☆ Skip"

    # master_tracker.csv must match jobs.db, not the stale values it was seeded with
    assert csv_row["Fit Score"] == str(db_row["fit_score"])
    assert csv_row["Priority"] == db_row["priority"]
    assert csv_row["Recommendation"] == db_row["recommendation"]
    assert csv_row["Reason"] == db_row["reason"]
    assert "Utah" not in csv_row["Reason"]
