import csv
import os
import pytest
import sqlite3
from parse_jobs import (
    evaluate_job,
    compute_priority,
    _find_skills,
    _format_skill_lists,
    parse_job_cards_from_text,
    normalize_ocr_spacing,
    handle_rescore,
    handle_clear_score_override,
    clean_existing_tracker,
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


def test_vuejs_alias_matches_resume_skill_listed_as_vue_dot_js():
    """A resume_skills config that lists only 'vue.js' must still recognize a
    posting title that says 'Vuejs' as a matched skill, not a missing one --
    _find_skills returns whichever POTENTIAL_SKILLS alias literally appeared
    in the text ('vuejs'), which must be compared against resume_skills by
    canonical display name, not by the raw alias string."""
    matched, missing = _format_skill_lists(["vuejs", "c#"], ["vue.js", "c#"])
    assert "Vue.js" in matched
    assert "Vue.js" not in missing


def test_zip_code_digit_spacing_is_collapsed():
    """A ZIP code split apart by PDF kerning ("UT 8 4 0 2 0") must be
    rejoined, the same way normalize_ocr_spacing already rejoins
    letter-by-letter kerning splits."""
    assert normalize_ocr_spacing("Draper, UT 8 4 0 2 0 (Remote)") == "Draper, UT 84020 (Remote)"


def test_apply_now_requires_a_technical_signal():
    """Remote + senior + small-company alone must not produce Apply Now/P1 --
    those are generic preferences any senior-sounding remote posting
    satisfies. Without a matched resume skill, a tech_keywords hit, or a
    legacy-modernization hit, the posting is capped at whatever its
    fit_score alone earns (Strong/P2 or Maybe/P3), never Apply Now/P1 --
    even if fit_score and confidence would otherwise clear the P1 bar."""
    job_generic = {
        "title": "Senior Software Engineer",
        "company": "Headway",
        "location": "Remote",
        "raw_context": "Senior Software Engineer Headway Remote full stack backend distributed data",
    }
    _, _, _, fit_score, _, _, recommendation, _, matched_skills, _, _ = evaluate_job(job_generic)
    assert fit_score >= 80, "fixture should still score high enough to have hit the old P1 bar"
    assert matched_skills == ""
    assert recommendation != "★★★★★ Apply Now"
    assert compute_priority(recommendation, "Apply") != "P1 – Apply today"

    # A real matched skill must still be able to reach Apply Now/P1.
    job_matched = {
        "title": "Senior .NET Engineer",
        "company": "Acme",
        "location": "Remote",
        "raw_context": "Senior .NET Engineer Acme Remote full stack backend distributed data",
    }
    _, _, _, _, _, _, recommendation_matched, _, matched_skills_matched, _, _ = evaluate_job(job_matched)
    assert matched_skills_matched != ""
    assert recommendation_matched == "★★★★★ Apply Now"


def test_porch_software_metadata_parses_correctly():
    """Glassdoor 'Jobs you might like' card wraps the title across two lines,
    with the trailing fragment ('Required') landing alone on its own line.
    This is the real layout-mode PDF extraction from a "Wheeler Machinery
    Co: Apply Now" Glassdoor digest (2026-08-12) -- a synthetic fixture that
    put 'Years Exp Required' on one line and reordered Company/Title/Location
    passed even though it didn't reproduce the real bug, where the wrap
    fragment 'Required' alone became the company name instead of Porch
    Software."""
    text = (
        "                                  Wheeler Machinery Co      2.5 ★\n"
        "                           Senior Full Stack Software Engineer\n"
        "                           Salt Lake City    , UT\n"
        "                           $112K - $159K (Glassdoor est.)\n"
        "\n"
        "                                Easy Apply\n"
        "\n"
        "\n"
        "                        Jobs you might like\n"
        "\n"
        "\n"
        "\n"
        "\n"
        "                                  PorchSoftware     2.6 ★\n"
        "                           Mid/Senior Full Stack Developer (C#/Vuejs) - Minimum 5 Years Exp\n"
        "                           Required\n"
        "                           Draper, UT\n"
        "                           $110K - $130K (Employer est.)\n"
        "\n"
        "                                Easy Apply\n"
        "\n"
        "\n"
        "\n"
        "\n"
        "\n"
        "                                  3form   3.6 ★\n"
    )
    jobs = parse_job_cards_from_text(text)
    porch_jobs = [j for j in jobs if "Porch" in j["company"]]
    assert len(porch_jobs) == 1
    porch = porch_jobs[0]
    # The source layout renders the company name with no literal space
    # character between the two words ("PorchSoftware") -- normalize_ocr_spacing
    # corrects this specific known case back to "Porch Software".
    assert porch["company"] == "Porch Software"
    assert porch["title"] == "Mid/Senior Full Stack Developer (C#/Vuejs) - Minimum 5 Years Exp Required"
    assert porch["location"] == "Draper, UT"

    wheeler_jobs = [j for j in jobs if "Wheeler" in j["company"]]
    assert len(wheeler_jobs) == 1
    assert wheeler_jobs[0]["company"] == "Wheeler Machinery Co"
    assert wheeler_jobs[0]["location"] == "Salt Lake City, UT"


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


def test_manual_score_preservation_across_sync_and_rescore(tmp_path):
    """Verify manual score overrides (score_source = 'manual') are preserved by
    clean_existing_tracker and default handle_rescore, but can be reset via rescore_all."""
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
        last_seen TEXT, fingerprint TEXT, previous_job_id TEXT, raw_context TEXT, score_source TEXT
    )"""
    )
    c.execute(
        """
        INSERT INTO jobs (
            job_id, company, position, location, raw_context, provider, source_pdf,
            confidence, job_type, company_type, review_status, disposition, notes,
            existing_company, date_added, url,
            tracker_status, fit_score, priority, recommendation, action, reason, score_source
        ) VALUES (
            'manual1', 'Wheeler Machinery Company', 'Senior Full Stack Software Engineer', 'Salt Lake City, UT',
            'wheeler machinery company senior full stack software engineer', 'Manual', 'Manual',
            '', 'Software Engineer', 'Small / Medium', 'Applied', 'Waiting', '',
            'No', '2026-08-01', '',
            'Applied', 95, 'P1 – Apply today', '★★★★★ Apply Now', 'Already Applied', 'Manual score override', 'manual'
        )
        """
    )
    conn.commit()
    conn.close()

    original_connect = sqlite3.connect
    def mock_connect(*args, **kwargs):
        return original_connect(db_path)

    csv_path = tmp_path / "test_tracker.csv"
    csv_headers = [
        "Job ID", "Review Status", "Job Type", "Company", "Position", "Location", "URL", "Provider",
        "Source PDF", "Source Index", "Confidence", "Fit Score", "Priority", "Company Type",
        "Recommendation", "Tracker Status", "Disposition", "Action", "Existing Company",
        "Age (days)", "Reason", "Matched Skills", "Missing Skills", "Date Added", "Last Seen", "Notes",
        "Recruiter", "Hiring Manager", "Fingerprint", "Previous Job ID", "Score Source",
    ]
    with open(csv_path, mode='w', newline='', encoding='utf-8') as f:
        csv.DictWriter(f, fieldnames=csv_headers).writeheader()

    # clean_existing_tracker checks for a relative "jobs.db" to restore rows
    # missing from the CSV -- give it one in an isolated cwd, distinct from
    # any real jobs.db, since sqlite3.connect is mocked to redirect to db_path
    # regardless of the filename requested.
    original_cwd = os.getcwd()
    os.chdir(tmp_path)
    (tmp_path / "jobs.db").touch()

    sqlite3.connect = mock_connect
    try:
        # 1. clean_existing_tracker must preserve score_source = manual, the 95
        # fit score, and the manually-set priority/action (not re-derive them)
        clean_existing_tracker(str(csv_path))
        conn = original_connect(db_path)
        conn.row_factory = sqlite3.Row
        row = dict(conn.cursor().execute("SELECT * FROM jobs WHERE job_id = 'manual1'").fetchone())
        conn.close()
        assert row["fit_score"] == 95
        assert row["score_source"] == "manual"
        assert row["priority"] == "P1 – Apply today"
        assert row["action"] == "Already Applied"

        # Score Source column must round-trip into the CSV, not be silently dropped
        with open(csv_path, newline='', encoding='utf-8') as f:
            csv_row = next(csv.DictReader(f))
        assert csv_row["Score Source"] == "manual"

        # 2. handle_rescore(rescore_all=False) must preserve the manual score
        handle_rescore(csv_path=str(csv_path), rescore_all=False)
        conn = original_connect(db_path)
        conn.row_factory = sqlite3.Row
        row = dict(conn.cursor().execute("SELECT * FROM jobs WHERE job_id = 'manual1'").fetchone())
        conn.close()
        assert row["fit_score"] == 95
        assert row["score_source"] == "manual"

        # 3. handle_rescore(rescore_all=True) forces rescoring and resets score_source to parser
        handle_rescore(csv_path=str(csv_path), rescore_all=True)
        conn = original_connect(db_path)
        conn.row_factory = sqlite3.Row
        row = dict(conn.cursor().execute("SELECT * FROM jobs WHERE job_id = 'manual1'").fetchone())
        conn.close()
        assert row["score_source"] == "parser"
    finally:
        sqlite3.connect = original_connect
        os.chdir(original_cwd)


def test_clear_score_override_scopes_to_target(tmp_path):
    """--clear-score-override <target> must only reset the matched job(s) --
    it must not clear or rescore every other manually-scored job in the DB."""
    db_path = tmp_path / "jobs.db"
    csv_path = tmp_path / "master_tracker.csv"
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
        last_seen TEXT, fingerprint TEXT, previous_job_id TEXT, raw_context TEXT, score_source TEXT
    )"""
    )
    for job_id, company in [("jobA", "CompanyA"), ("jobB", "CompanyB")]:
        c.execute(
            """
            INSERT INTO jobs (
                job_id, company, position, location, raw_context,
                tracker_status, fit_score, recommendation, action, reason, score_source
            ) VALUES (?, ?, 'Engineer', 'Salt Lake City, UT', 'engineer',
                      'Applied', 90, '★★★★★ Apply Now', 'Already Applied', 'manual override', 'manual')
            """,
            (job_id, company),
        )
    conn.commit()
    conn.close()

    handle_clear_score_override(target="CompanyA", db_path=str(db_path), csv_path=str(csv_path))

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = {r["job_id"]: dict(r) for r in conn.execute("SELECT * FROM jobs").fetchall()}
    conn.close()

    assert rows["jobA"]["score_source"] == "parser"
    assert rows["jobB"]["score_source"] == "manual"
    assert rows["jobB"]["fit_score"] == 90

