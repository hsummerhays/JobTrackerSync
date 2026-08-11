"""Shared helpers used across the job-tracker scripts (parse_jobs.py,
find_pdf.py, query_jobs.py). Centralized so a fix to shared logic (status
ranking, key normalization, delimiter handling, file URI conversion)
doesn't have to be re-applied by hand to every script that needs it.
"""
import re
from pathlib import Path, PureWindowsPath
from urllib.parse import quote

# '/' appears routinely inside Windows and POSIX file paths, so it can't
# safely delimit multi-valued fields (Provider, Source PDF) stored in the CSV.
FIELD_DELIMITER = "|"

UNREVIEWED_STATUSES = {"New", "Imported"}

VALID_STATUSES = ["New", "Applied", "Phone Screen", "Technical Interview", "Recruiter Submitted", "Waiting", "Rejected", "Cancelled", "Ghosted", "Expired", "Offer", "Accepted"]

# A human deliberately closed the loop on these -- once set, they must not be
# clobbered by a still-active status like "Applied" just because "Applied"
# outranks them numerically below.
TERMINAL_STATUSES = {"Rejected", "Ghosted", "Cancelled", "Expired", "Closed"}

STATUS_RANKS = {
    "Accepted": 100,
    "Offer": 95,
    "Interviewing": 90,
    "Interview": 90,
    "Technical Interview": 90,
    "Phone Screen": 85,
    "Recruiter Contact": 80,
    "Recruiter Submitted": 80,
    "Applied": 70,
    "Waiting": 65,
    "Rejected": 50,
    "Ghosted": 40,
    "Cancelled": 30,
    "Expired": 20,
    "New": 10,
    "Imported": 5,
}


def normalize_string(s):
    return re.sub(r'[^a-z0-9]', '', str(s).lower())


def get_status_rank(status):
    return STATUS_RANKS.get(status, 0)


def should_prefer_status(base_status, candidate_status):
    base_status = (base_status or "").strip()
    candidate_status = (candidate_status or "").strip()

    base_rank = get_status_rank(base_status)
    candidate_rank = get_status_rank(candidate_status)

    # Active human applications (Applied, Interviewing, Offer) and explicit
    # user Rejections must never be clobbered by weaker or automated statuses
    # (like Expired, Cancelled, or New).
    return candidate_rank > base_rank



def is_clean_location(loc):
    return '·' not in (loc or '')


def locations_compatible(loc_a, loc_b):
    """True if two rows' locations plausibly refer to the same posting --
    either they match after normalization, or one is a malformed
    'Company · Location' value (which fix_all_offset_locations.py-style
    cleanup targets) and can't be trusted to disagree with a clean one.
    Two distinct clean locations are never compatible, since that usually
    means two different postings, not one posting recorded twice."""
    if not is_clean_location(loc_a) or not is_clean_location(loc_b):
        return True
    return normalize_string(loc_a) == normalize_string(loc_b)


def split_multivalue_field(value: str) -> list[str]:
    """Split a field stored with FIELD_DELIMITER, tolerating the legacy
    ' / ' delimiter older rows may still contain."""
    chunks = []
    for pipe_part in (value or "").split("|"):
        chunks.extend(pipe_part.split(" / "))
    return [chunk.strip() for chunk in chunks if chunk.strip()]


def merge_delimited_field(base_value, other_value):
    """Merge a multi-valued field stored with FIELD_DELIMITER, skipping dupes."""
    items = []
    for v in split_multivalue_field(base_value) + split_multivalue_field(other_value):
        if v not in items:
            items.append(v)
    return f"{FIELD_DELIMITER}".join(items)


def canonical_key(company, position, date_added):
    """Group rows by company + position + date, not company + date alone --
    a company can legitimately post several different jobs on the same day."""
    return f"{normalize_string(company)}|{normalize_string(position)}|{date_added}"


def normalize_location(loc: str) -> str:
    """Return a clean, canonical location string.

    Rules applied in order:
    1. Strip LinkedIn/Indeed work-type suffixes: (On-site), (Hybrid), (Remote),
       (In person), (Contract), (Part-time) — they're redundant with other fields.
    2. Resolve "X Metropolitan Area [qualifier]" → "X, UT" (all known uses are SLC).
    3. Resolve "Jobs in X" artifacts from digest scraping → "X, UT".
    4. Map bare state codes, blanks, or explicit "Unknown" → "Unknown".
    5. Normalise known shorthand ("Remote" variations stay as-is).
    """
    if not loc:
        return "Unknown"
    loc = loc.strip()
    if not loc or loc.lower() == "unknown":
        return "Unknown"

    # Strip LinkedIn/Indeed trailing work-type qualifiers
    loc = re.sub(
        r'\s*\((On-site|On site|Onsite|Hybrid|Remote|In person|In-person|Contract|Part-time|Full-time)\)',
        '', loc, flags=re.IGNORECASE
    ).strip()

    # Resolve Metropolitan Area variants (all are SLC for this tracker)
    metro_match = re.match(
        r'^(.+?)\s+Metropolitan\s+Area\b', loc, re.IGNORECASE
    )
    if metro_match:
        city = metro_match.group(1).strip()
        # Map known cities; default to UT
        STATE_MAP = {
            "Salt Lake City": "UT", "Denver": "CO", "Phoenix": "AZ",
            "Dallas": "TX", "Austin": "TX", "Seattle": "WA",
        }
        state = STATE_MAP.get(city, "UT")
        return f"{city}, {state}"

    # Resolve "Jobs in X" digest artifacts (assume Utah)
    jobs_in = re.match(r'^Jobs\s+in\s+(.+)$', loc, re.IGNORECASE)
    if jobs_in:
        return f"{jobs_in.group(1).strip()}, UT"

    # Bare state code → Unknown
    if re.match(r'^[A-Z]{2}$', loc):
        return "Unknown"

    # Empty after stripping → Unknown
    if not loc:
        return "Unknown"

    return loc


def canonical_job_key(company, position, location):
    """Group parsed jobs by company + position + location (no date), used
    while scanning a single run to catch the same posting appearing on
    multiple pages/PDFs before it's ever written to the tracker."""
    return f"{normalize_string(company)}|{normalize_string(position)}|{normalize_string(normalize_location(location))}"



def build_occurrence_fingerprint(provider, source_pdf, date_added, source_index, title):
    """Occurrence fingerprint for aggregator/digest placeholders (e.g.
    "Ladders-DailyDigest"), whose "company" isn't a real employer and so
    can't use canonical_job_key. Identifies a specific posting by where it
    was found (provider + source PDF + date + position within the PDF) plus
    its title, so reprocessing the same PDF recognizes the row instead of
    minting a new one. Shared by the initial parse and by backfilling rows
    that predate the Fingerprint column, so the two never drift apart.
    source_index is unavailable when backfilling a legacy row (it was never
    persisted as its own column) -- callers pass "" in that case."""
    return "|".join([
        normalize_string(provider or ""),
        normalize_string(str(source_pdf or "")),
        str(date_added or ""),
        str(source_index or ""),
        normalize_string(title or ""),
    ])


def path_to_file_uri(value: str) -> "str | None":
    """Convert a filesystem path string (Windows or POSIX) to a file:// URI,
    or None if it can't be resolved."""
    value = value.strip()

    try:
        if re.match(r"^[A-Za-z]:[\\/]", value):
            path = PureWindowsPath(value)
            drive = path.drive.rstrip(":").upper()
            encoded_parts = "/".join(quote(part) for part in path.parts[1:])
            return f"file:///{drive}:/{encoded_parts}"

        return Path(value).resolve().as_uri()
    except (OSError, ValueError):
        return None


def title_similarity(a, b):
    """Cheap token-overlap similarity (Jaccard over normalized words) used to
    match a malformed row to the clean row it most likely corresponds to."""
    words_a = set(re.findall(r'[a-z0-9]+', str(a).lower()))
    words_b = set(re.findall(r'[a-z0-9]+', str(b).lower()))
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)
