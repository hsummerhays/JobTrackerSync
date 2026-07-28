"""Shared helpers for the master_tracker.csv cleanup/dedup scripts
(fix_duplicates.py, fix_duplicates_by_company.py). Centralized so a fix to
one script's merge logic (status ranking, key normalization, delimiter
handling) doesn't have to be re-applied by hand to the others.
"""
import re

# '/' appears routinely inside Windows and POSIX file paths, so it can't
# safely delimit multi-valued fields (Provider, Source PDF) stored in the CSV.
FIELD_DELIMITER = "|"

UNREVIEWED_STATUSES = {"New", "Imported"}

# A human deliberately closed the loop on these -- once set, they must not be
# clobbered by a still-active status like "Applied" just because "Applied"
# outranks them numerically below.
TERMINAL_STATUSES = {"Rejected", "Ghosted", "Cancelled", "Expired", "Closed"}

STATUS_RANKS = {
    "Offer": 100,
    "Interviewing": 90,
    "Technical Interview": 85,
    "Phone Screen": 80,
    "Recruiter Contact": 75,
    "Applied": 60,
    "Waiting": 55,
    "New": 50,
    "Imported": 45,
    "Rejected": 10,
    "Ghosted": 10,
    "Cancelled": 10,
    "Expired": 10,
    "Closed": 10,
}


def normalize_string(s):
    return re.sub(r'[^a-z0-9]', '', str(s).lower())


def get_status_rank(status):
    return STATUS_RANKS.get(status, 0)


def should_prefer_status(base_status, candidate_status):
    base_status = (base_status or "").strip()
    candidate_status = (candidate_status or "").strip()

    base_unreviewed = base_status in UNREVIEWED_STATUSES
    candidate_unreviewed = candidate_status in UNREVIEWED_STATUSES

    if base_unreviewed != candidate_unreviewed:
        return base_unreviewed and not candidate_unreviewed

    base_terminal = base_status in TERMINAL_STATUSES
    candidate_terminal = candidate_status in TERMINAL_STATUSES

    if base_terminal != candidate_terminal:
        # A terminal status is sticky: a still-active status never displaces
        # it, even though "Applied" outranks "Rejected" numerically.
        return candidate_terminal

    return get_status_rank(candidate_status) > get_status_rank(base_status)


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


def _split_legacy_values(value: str) -> list[str]:
    chunks = []
    for pipe_part in value.split("|"):
        chunks.extend(pipe_part.split(" / "))
    return [chunk.strip() for chunk in chunks if chunk.strip()]


def merge_delimited_field(base_value, other_value):
    """Merge a multi-valued field stored with FIELD_DELIMITER, skipping dupes."""
    items = []
    for v in _split_legacy_values(base_value or '') + _split_legacy_values(other_value or ''):
        if v not in items:
            items.append(v)
    return f"{FIELD_DELIMITER}".join(items)


def canonical_key(company, position, date_added):
    """Group rows by company + position + date, not company + date alone --
    a company can legitimately post several different jobs on the same day."""
    return f"{normalize_string(company)}|{normalize_string(position)}|{date_added}"


def title_similarity(a, b):
    """Cheap token-overlap similarity (Jaccard over normalized words) used to
    match a malformed row to the clean row it most likely corresponds to."""
    words_a = set(re.findall(r'[a-z0-9]+', str(a).lower()))
    words_b = set(re.findall(r'[a-z0-9]+', str(b).lower()))
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)
