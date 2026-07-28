import os
from parse_jobs import parse_job_cards_from_text

FIXTURE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "fixtures",
    "omada_health_linkedin_extract.txt",
)


def _parse_fixture():
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        text = f.read()
    return parse_job_cards_from_text(text, provider="LinkedIn", source_pdf="omada.pdf")


def test_omada_health_linkedin_parsing_exact_pairs():
    """Regression test for a LinkedIn 'Jobs similar to X' digest where each
    card is a bare 'Title' line followed by a 'Company · Location' line.
    A prior bug offset every company/location pair by one card, e.g.
    Franki's job showed Filevine's location. This checks exact
    (title, company, location) triples, not just that the wrong value
    is absent, so a re-introduced offset-by-one bug is caught directly."""
    jobs = _parse_fixture()
    by_company = {j["company"]: j for j in jobs}

    expected = {
        "Franki": ("Senior Backend Engineer", "United States (Remote)"),
        "Filevine": ("Senior Software Development Engineer (Back-end)", "United States (Remote)"),
        "Eight Sleep": ("Senior Backend Engineer", "United States (Remote)"),
        "Pear Commerce": ("Senior Software Engineer", "United States (Remote)"),
        "LemonEdge": ("Senior Software Engineer", "United States (Remote)"),
        "Tilt": ("Senior Software Engineer, Backend", "United States (Remote)"),
    }

    for company, (title, location) in expected.items():
        assert company in by_company, f"{company} job not found"
        job = by_company[company]
        assert job["title"] == title, f"{company} title mismatch: {job['title']!r}"
        assert job["location"] == location, f"{company} location mismatch: {job['location']!r}"
