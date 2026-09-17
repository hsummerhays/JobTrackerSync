"""Shared helpers and consolidated utility functions used across the job-tracker
scripts (parse_jobs.py, find_pdf.py, query_jobs.py, create_calendar_event.py,
generate_vcf.py).

Centralized so fixes to shared logic (status ranking, key normalization,
delimiter handling, file URI conversion, text normalization, hashing, file
backups, and classification) don't have to be re-applied by hand to every script.
"""
from __future__ import annotations

import csv
import glob
import hashlib
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import time
import urllib.parse
from datetime import datetime
from pathlib import Path, PureWindowsPath
from typing import Any, Iterable, List, Optional, Sequence, Tuple

# '/' appears routinely inside Windows and POSIX file paths, so it can't
# safely delimit multi-valued fields (Provider, Source PDF) stored in the CSV.
FIELD_DELIMITER = "|"

# Tracker CSV Standard Column Names
TRACKER_HEADERS = [
    "Job ID",
    "Review Status",
    "Job Type",
    "Company",
    "Position",
    "Location",
    "URL",
    "Provider",
    "Source PDF",
    "Source Index",
    "Confidence",
    "Fit Score",
    "Priority",
    "Company Type",
    "Recommendation",
    "Tracker Status",
    "Disposition",
    "Action",
    "Existing Company",
    "Age (days)",
    "Reason",
    "Matched Skills",
    "Missing Skills",
    "Date Added",
    "Last Seen",
    "Notes",
    "Recruiter",
    "Hiring Manager",
    "Fingerprint",
    "Previous Job ID",
]

# Canonical Status Lists & Sets
VALID_STATUSES = [
    "New",
    "Applied",
    "Phone Screen",
    "Manager Interview Pending",
    "Technical Interview",
    "Onsite Interview Pending",
    "Final Interview Scheduled",
    "Assessment Pending",
    "Reference Check",
    "Recruiter Submitted",
    "Waiting",
    "Rejected",
    "Cancelled",
    "Ghosted",
    "Expired",
    "Offer",
    "Accepted",
]

VALID_REVIEW_STATUSES = [
    "New",
    "Applied",
    "Imported",
    "Closed",
    "Recruiter Contact",
    "Reviewed",
]

VALID_ACTIONS = [
    "Apply",
    "Contact Recruiter",
    "Review",
    "Already Applied",
    "Ignore",
    "Send References",
]

UNREVIEWED_STATUSES = {"New", "Imported"}

TERMINAL_STATUSES = {"Rejected", "Ghosted", "Cancelled", "Expired", "Closed"}

CLOSED_TRACKER_STATUSES = {"Rejected", "Cancelled", "Ghosted", "Expired"}

INTERVIEW_STATUSES = {
    "Phone Screen",
    "Manager Interview Pending",
    "Technical Interview",
    "Assessment Pending",
    "Onsite Interview Pending",
    "Final Interview Scheduled",
    "Reference Check",
}

# Statuses that count as active / in-flight applications for review status and actions
APPLIED_APPLICATION_STATUSES = {
    "Applied",
    "Phone Screen",
    "Manager Interview Pending",
    "Technical Interview",
    "Onsite Interview Pending",
    "Final Interview Scheduled",
    "Assessment Pending",
    "Reference Check",
    "Recruiter Submitted",
    "Waiting",
    "Offer",
    "Accepted",
    "Interviewing",
    "Interview",
}

# Statuses representing active stages in the interview pipeline (excluding New/Applied/Terminal)
ACTIVE_PIPELINE_STATUSES = {
    "Phone Screen",
    "Manager Interview Pending",
    "Technical Interview",
    "Assessment Pending",
    "Onsite Interview Pending",
    "Final Interview Scheduled",
    "Reference Check",
    "Recruiter Submitted",
    "Waiting",
}

# Statuses that trigger the re-apply check on newly rediscovered job cards
REAPPLY_STATUSES = {
    "Applied",
    "Phone Screen",
    "Manager Interview Pending",
    "Technical Interview",
    "Onsite Interview Pending",
    "Final Interview Scheduled",
    "Assessment Pending",
    "Reference Check",
    "Recruiter Submitted",
    "Waiting",
}

DEFAULT_DISPOSITION_MAP = {
    "New": "Apply",
    "Applied": "Waiting",
    "Phone Screen": "Active",
    "Manager Interview Pending": "Active",
    "Technical Interview": "Active",
    "Onsite Interview Pending": "Active",
    "Final Interview Scheduled": "Active",
    "Assessment Pending": "Active",
    "Reference Check": "Active",
    "Recruiter Submitted": "Active",
    "Waiting": "Active",
    "Interviewing": "Active",
    "Interview": "Active",
    "Rejected": "Closed",
    "Cancelled": "Closed",
    "Ghosted": "Closed",
    "Expired": "Closed",
    "Offer": "Active",
    "Accepted": "Active",
}

STATUS_RANKS = {
    "Accepted": 100,
    "Offer": 95,
    "Reference Check": 94,
    "Final Interview Scheduled": 93,
    "Onsite Interview Pending": 92,
    "Assessment Pending": 91,
    "Interviewing": 90,
    "Interview": 90,
    "Technical Interview": 90,
    "Manager Interview Pending": 87,
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

# Known aggregator/job-board brands that sometimes appear as "company" inside
# other providers' digest emails (e.g. Ladders posts jobs on LinkedIn), or are
# deliberately used as a placeholder "company" for digest-style postings where
# no per-job employer can be extracted (see is_aggregator_placeholder below).
AGGREGATOR_PROVIDER_NAMES = {
    "ladders",
    "ladders-dailydigest",
    "theladders",
    "the ladders",
    "linkedin",
    "indeed",
    "glassdoor",
    "ziprecruiter",
    "jobs.utah.gov",
    "jobs.utah.gov-dailysummary",
    "actively recruiting",
}

MAX_OLD_BACKUPS_TO_KEEP = 3
_RUN_START_TIMESTAMP = datetime.now().strftime("%Y%m%d%H%M%S%f")

# ---------------------------------------------------------------------------
# String & Regex Normalization
# ---------------------------------------------------------------------------

_COMPANY_SUFFIX_RE = re.compile(
    r"\s*[,]?\s*\b(company|co|corporation|corp|incorporated|inc|limited|ltd|llc|llp|lp|group|holdings)\.?\s*$",
    re.IGNORECASE,
)


def normalize_string(s: Any) -> str:
    """Lowercase string and strip all non-alphanumeric characters."""
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def word_boundary_pattern(search_term: str) -> re.Pattern:
    """Build a case-insensitive regex that matches search_term when it isn't
    embedded inside a longer alphanumeric run (e.g. matches 'Franki' in 'Franki_hiring.pdf'
    or 'Python' in 'Python/Django'). Non-alphanumeric separators like '_' or '-'
    count as boundaries."""
    return re.compile(
        r"(?<![A-Za-z0-9])" + re.escape(search_term) + r"(?![A-Za-z0-9])",
        re.IGNORECASE,
    )


def normalize_company_for_matching(company: Any) -> str:
    """Strip trailing corporate-suffix words for identity matching, so
    'Wheeler Machinery Company' and 'Wheeler Machinery Co' resolve to the
    same canonical company. Repeats to handle chained suffixes (e.g. 'Foo
    Group Inc')."""
    s = str(company or "").strip()
    prev = None
    while prev != s:
        prev = s
        s = _COMPANY_SUFFIX_RE.sub("", s).strip()
    return s


def clean_company_name(comp: Any) -> str:
    """Remove common email subject/notification formatting artifacts from company names.
    Examples:
      'Jobs at Brady Corporation' -> 'Brady Corporation'
      '(Remote) at Globe Life' -> 'Globe Life'
      'Informativ is hiring for Sr. PHP Engineer' -> 'Informativ'
    """
    if not comp:
        return ""
    cleaned = re.sub(r"(?i)^\s*Jobs\s+at\s+", "", str(comp))
    cleaned = re.sub(r"(?i)^\s*\(Remote\)\s+at\s+", "", cleaned)
    cleaned = re.sub(r"(?i)^\s*at\s+", "", cleaned)
    cleaned = re.sub(r"(?i)\s+is\s+hiring\b.*", "", cleaned)
    cleaned = re.sub(r"(?i)\s+is\s+looking\s+for\b.*", "", cleaned)
    cleaned = re.sub(r"(?i)\bhas\s+an\s+open\s+position\b.*", "", cleaned)
    cleaned = re.sub(r"\s*\.\.\.\s*$", "", cleaned)
    return cleaned.strip()


def normalize_ocr_spacing(text: Any) -> str:
    """Normalize OCR kerning and spacing artifacts across extracted text."""
    if not text:
        return ""
    s = str(text)
    # Specific common corrections
    s = re.sub(r"(?i)\bfourey\s+es\b", "Foureyes", s)
    s = re.sub(r"(?i)\bof\s+fice\b", "office", s)
    s = re.sub(r"(?i)\bfirs\s+t\b", "first", s)
    s = re.sub(r"(?i)\blak\s+e\b", "lake", s)
    s = re.sub(r"(?i)\bseen\s+firs\s+t\b", "seen first", s)
    s = re.sub(r"(?i)\bpac\s+k\s+yak\b", "pack yak", s)
    s = re.sub(r"(?i)\binsurance\s+of\s+fice\b", "Insurance Office", s)
    s = re.sub(r"\bPorchSoftware\b", "Porch Software", s)

    # General heuristics:
    # 1. End of word separated by space: "firs t" -> "first"
    s = re.sub(
        r"\b([a-zA-Z]{2,})\s+([bcdfghjklmnpqrstvwxyzBCDFGHJKLMNPQRSTVWXYZ])\b(?![#+])",
        r"\1\2",
        s,
    )
    # 2. Start of word separated by space: "p hoto" -> "photo"
    s = re.sub(
        r"\b([bcdfghjklmnpqrstvwxyzBCDFGHJKLMNPQRSTVWXYZ])\s+([a-zA-Z]{2,})\b",
        r"\1\2",
        s,
    )
    s = re.sub(r"(?i)\bwestv\s+alley\b", "West Valley", s)
    s = re.sub(r"(?i)\btechnolog\s+ies\b", "Technologies", s)
    s = re.sub(r"(?i)\bcorp\s+oration\b", "Corporation", s)
    s = re.sub(r"(?i)\bsurg\s+e\b", "Surge", s)
    s = re.sub(r"(?i)\bdrap\s+er\b", "Draper", s)
    s = re.sub(r",(\s*)([A-Z])\s+([A-Z])\b", r",\1\2\3", s)
    s = re.sub(r"\b\d(?:\s+\d){4,8}\b", lambda m: m.group(0).replace(" ", ""), s)

    return s


def normalize_title(title: Any) -> str:
    """Normalize job title for deduplication keys, mapping standalone Roman numeral
    level indicators (I, II, III, IV, V) to Arabic digits (1, 2, 3, 4, 5)."""
    if not title:
        return ""
    ROMAN_MAP = {"i": "1", "ii": "2", "iii": "3", "iv": "4", "v": "5"}
    return re.sub(
        r"\b(i|ii|iii|iv|v)\b",
        lambda m: ROMAN_MAP.get(m.group(1).lower(), m.group(1)),
        str(title),
        flags=re.IGNORECASE,
    )


def is_clean_location(loc: Any) -> bool:
    """True if location string does not contain unseparated metadata delimiters."""
    return "·" not in (str(loc or ""))


def normalize_location(loc: Any) -> str:
    """Return a clean, canonical location string."""
    if not loc:
        return "Unknown"
    s = str(loc).strip()
    if not s or s.lower() == "unknown":
        return "Unknown"

    # Strip LinkedIn/Indeed trailing work-type qualifiers
    s = re.sub(
        r"\s*\((On-site|On site|Onsite|Hybrid|Remote|In person|In-person|Contract|Part-time|Full-time)\)",
        "",
        s,
        flags=re.IGNORECASE,
    ).strip()

    # Resolve Metropolitan Area variants (default to SLC/UT)
    metro_match = re.match(r"^(.+?)\s+Metropolitan\s+Area\b", s, re.IGNORECASE)
    if metro_match:
        city = metro_match.group(1).strip()
        STATE_MAP = {
            "Salt Lake City": "UT",
            "Denver": "CO",
            "Phoenix": "AZ",
            "Dallas": "TX",
            "Austin": "TX",
            "Seattle": "WA",
        }
        state = STATE_MAP.get(city, "UT")
        return f"{city}, {state}"

    # Resolve "Jobs in X" digest artifacts (assume Utah)
    jobs_in = re.match(r"^Jobs\s+in\s+(.+)$", s, re.IGNORECASE)
    if jobs_in:
        return f"{jobs_in.group(1).strip()}, UT"

    # Strip alert-age fragments
    s = re.sub(
        r"\s+(?:\d+\s*(?:d|h|w|mo|y)|Just posted)$", "", s, flags=re.IGNORECASE
    ).strip()

    # Strip trailing US ZIP code
    s = re.sub(r"\s+\d{5}(?:-\d{4})?$", "", s).strip()

    # Bare state code → Unknown
    if re.match(r"^[A-Z]{2}$", s):
        return "Unknown"

    if not s:
        return "Unknown"

    return s


def locations_compatible(loc_a: Any, loc_b: Any) -> bool:
    """True if two rows' locations plausibly refer to the same posting --
    either they match after normalization, or one is a malformed value."""
    if not is_clean_location(loc_a) or not is_clean_location(loc_b):
        return True
    return normalize_string(loc_a) == normalize_string(loc_b)


def title_similarity(a: Any, b: Any) -> float:
    """Cheap token-overlap similarity (Jaccard over normalized words)."""
    words_a = set(re.findall(r"[a-z0-9]+", str(a or "").lower()))
    words_b = set(re.findall(r"[a-z0-9]+", str(b or "").lower()))
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)


# ---------------------------------------------------------------------------
# Delimited Fields & Keys
# ---------------------------------------------------------------------------


def split_multivalue_field(value: str) -> list[str]:
    """Split a field stored with FIELD_DELIMITER, tolerating legacy ' / '."""
    chunks = []
    for pipe_part in (value or "").split("|"):
        chunks.extend(pipe_part.split(" / "))
    return [chunk.strip() for chunk in chunks if chunk.strip()]


def merge_delimited_field(base_value: Any, other_value: Any) -> str:
    """Merge a multi-valued field stored with FIELD_DELIMITER, skipping dupes."""
    items = []
    for v in split_multivalue_field(str(base_value or "")) + split_multivalue_field(
        str(other_value or "")
    ):
        if v not in items:
            items.append(v)
    return f"{FIELD_DELIMITER}".join(items)


def canonical_key(company: Any, position: Any, date_added: Any) -> str:
    """Group rows by company + position + date."""
    return f"{normalize_string(company)}|{normalize_string(normalize_title(position))}|{date_added}"


def canonical_job_key(company: Any, position: Any, location: Any) -> str:
    """Group parsed jobs by company + position + location (strict literal identity)."""
    return f"{normalize_string(company)}|{normalize_string(normalize_title(position))}|{normalize_string(normalize_location(location))}"


def is_aggregator_placeholder(company: Any) -> bool:
    """True if company is an aggregator/digest placeholder rather than a real employer."""
    comp_lower = str(company or "").strip().lower()
    if not comp_lower:
        return False
    return (
        comp_lower in AGGREGATOR_PROVIDER_NAMES
        or "dailysummary" in comp_lower
        or "dailydigest" in comp_lower
    )


def build_occurrence_fingerprint(
    provider: Any, source_pdf: Any, date_added: Any, source_index: Any, title: Any
) -> str:
    """Occurrence fingerprint for aggregator/digest placeholders."""
    return "|".join([
        normalize_string(provider or ""),
        normalize_string(str(source_pdf or "")),
        str(date_added or ""),
        str(source_index or ""),
        normalize_string(title or ""),
    ])


# ---------------------------------------------------------------------------
# Status & Workflow Logic
# ---------------------------------------------------------------------------


def get_status_rank(status: Any) -> int:
    return STATUS_RANKS.get(str(status or "").strip(), 0)


def should_prefer_status(base_status: Any, candidate_status: Any) -> bool:
    """True if candidate_status has higher rank than base_status."""
    base_rank = get_status_rank(base_status)
    candidate_rank = get_status_rank(candidate_status)
    return candidate_rank > base_rank


def compute_priority(
    recommendation: str, action: str, age_days: int = 0
) -> str:
    """Compute priority (P1–P4) based on recommendation, action, and age in days."""
    if recommendation in ["★☆☆☆☆ Skip", "★★☆☆☆ Low"]:
        return "P4 – Ignore"
    elif recommendation == "★★★☆☆ Maybe":
        return "P3 – Investigate"

    if action in ["Apply", "Already Applied"] and recommendation == "★★★★★ Apply Now":
        priority = "P1 – Apply today"
    elif action in ["Apply", "Already Applied", "Contact Recruiter"]:
        priority = "P2 – Apply this week"
    elif action == "Review":
        priority = "P3 – Investigate"
    else:
        priority = "P4 – Ignore"

    if action in ["Apply", "Contact Recruiter"] and age_days > 14:
        if priority == "P1 – Apply today":
            priority = "P2 – Apply this week"
        elif priority == "P2 – Apply this week":
            priority = "P3 – Investigate"

    return priority


def classify_workplace(
    location: Any = "", position: Any = "", raw_context: Any = ""
) -> str:
    """Classify workplace arrangement as 'Hybrid', 'Remote', 'Onsite', or 'Unknown'."""
    text = f"{location or ''} {position or ''} {raw_context or ''}".lower()
    if "hybrid" in text:
        return "Hybrid"
    elif "remote" in text or "work from home" in text or "telecommute" in text:
        return "Remote"
    elif (
        location
        and str(location).strip()
        and str(location).strip().lower() not in ("n/a", "unknown", "none")
    ):
        return "Onsite"
    else:
        return "Unknown"


def classify_job_type(title: Any, context: Any = "") -> str:
    """Determine if a job is a Software Engineer or Operations role."""
    title_lower = str(title or "").lower()
    context_lower = str(context or "").lower()

    ops_indicators = [
        "operations",
        "manufacturing",
        "inventory",
        "logistics",
        "repair",
        "production",
        "warehouse",
        "procurement",
        "manager",
        "supervisor",
        "coordinator",
        "billing",
        "reconciliation",
    ]
    swe_indicators = [
        "software",
        "developer",
        "engineer",
        "programmer",
        "architect",
        ".net",
        "java",
        "c#",
        "spring",
        "react",
    ]

    # Check title first
    has_ops_title = any(w in title_lower for w in ops_indicators)
    has_swe_title = any(w in title_lower for w in swe_indicators)

    specific_ops = [
        "manufacturing",
        "inventory",
        "logistics",
        "production",
        "warehouse",
        "procurement",
    ]
    if any(w in title_lower for w in specific_ops) and not any(
        w in title_lower for w in ["software", "developer", "backend"]
    ):
        return "Operations"

    if has_ops_title and not has_swe_title:
        return "Operations"
    if has_swe_title:
        return "Software Engineer"

    # Check context
    has_ops_context = any(w in context_lower for w in ops_indicators)
    has_swe_context = any(w in context_lower for w in swe_indicators)

    if has_ops_context and not has_swe_context:
        return "Operations"

    return "Software Engineer"


def detect_provider(text: Any, filename: Any = "") -> str:
    """Detect job board provider from PDF content or filename."""
    full_text = f"{text or ''} {filename or ''}".lower()
    if "jobs.utah.gov" in full_text or "utah's daily job summary" in full_text:
        return "jobs.utah.gov"
    elif "linkedin" in full_text:
        return "LinkedIn"
    elif "bhe career site" in full_text or "bhe career" in full_text:
        return "BHE"
    elif "ladders" in full_text or "your skills are in high demand" in full_text:
        return "Ladders"
    elif "indeed" in full_text:
        return "Indeed"
    elif "glassdoor" in full_text:
        return "Glassdoor"
    elif "ziprecruiter" in full_text:
        return "ZipRecruiter"
    elif "robert half" in full_text or "roberthalf.com" in full_text:
        return "Robert Half"
    elif "lensa" in full_text or "lensa.com" in full_text:
        return "Lensa"
    return "Unknown/Other"


# ---------------------------------------------------------------------------
# File Operations, Hashing, Backups & Atomic Writes
# ---------------------------------------------------------------------------


def path_to_file_uri(value: str) -> Optional[str]:
    """Convert a filesystem path string (Windows or POSIX) to a file:// URI,
    or None if it can't be resolved."""
    if not value:
        return None
    val = value.strip()
    try:
        if re.match(r"^[A-Za-z]:[\\/]", val):
            path = PureWindowsPath(val)
            drive = path.drive.rstrip(":").upper()
            encoded_parts = "/".join(urllib.parse.quote(part) for part in path.parts[1:])
            return f"file:///{drive}:/{encoded_parts}"

        return Path(val).resolve().as_uri()
    except (OSError, ValueError):
        return None


def hash_file(file_path: str, algorithm: str = "sha256") -> Optional[str]:
    """Generate content hash for a file, or None on OSError."""
    try:
        hasher = getattr(hashlib, algorithm)()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except OSError:
        return None


def hash_pdf_file(pdf_path: str) -> Optional[str]:
    """Return a stable content hash (MD5) for a PDF file, or None on error."""
    return hash_file(pdf_path, algorithm="md5")


def backup_timestamp(backup_path: str) -> str:
    """Extract the timestamp suffix from a .bak.<timestamp> filename."""
    return backup_path.rsplit(".bak.", 1)[-1]


_backup_timestamp = backup_timestamp


def backup_file_if_exists(
    path: str,
    max_backups: int = MAX_OLD_BACKUPS_TO_KEEP,
    run_start_timestamp: Optional[str] = None,
) -> Optional[str]:
    """Copy `path` to a timestamped `.bak.<timestamp>` sibling before a risky write.
    Prunes older backups from past runs down to max_backups."""
    if not os.path.exists(path):
        return None
    ts = run_start_timestamp or _RUN_START_TIMESTAMP
    backup_path = f"{path}.bak.{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    try:
        shutil.copy2(path, backup_path)
        directory = os.path.dirname(os.path.abspath(path)) or "."
        base_name = os.path.basename(path)
        pattern = os.path.join(directory, f"{base_name}.bak.*")
        existing_backups = sorted(glob.glob(pattern), reverse=True)
        older_run_backups = [
            b for b in existing_backups if backup_timestamp(b) < ts
        ]
        for old_backup in older_run_backups[max_backups:]:
            try:
                os.remove(old_backup)
            except OSError:
                pass
        return backup_path
    except OSError:
        return None


def write_csv_atomic(
    csv_path: str,
    fieldnames: Sequence[str],
    rows: Iterable[dict],
    extrasaction: str = "raise",
) -> None:
    """Write rows to csv_path via a temp file + atomic rename with retry on Windows."""
    target_dir = os.path.dirname(os.path.abspath(csv_path)) or "."
    fd, tmp_path = tempfile.mkstemp(
        dir=target_dir, prefix=".tmp_tracker_", suffix=".csv"
    )
    try:
        with os.fdopen(fd, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f, fieldnames=fieldnames, extrasaction=extrasaction
            )
            writer.writeheader()
            writer.writerows(rows)
        for attempt in range(5):
            try:
                os.replace(tmp_path, csv_path)
                break
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.05 * (attempt + 1))
    except BaseException:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


# Alias for backward compatibility
write_tracker_csv_atomic = write_csv_atomic


# ---------------------------------------------------------------------------
# Database Utilities
# ---------------------------------------------------------------------------


def ensure_db_columns(
    cursor: sqlite3.Cursor, table: str, columns: Iterable[Tuple[str, str]]
) -> None:
    """Idempotently add any of `columns` (list of (name, type)) missing from `table`."""
    for col, col_type in columns:
        try:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError:
            pass


# Alias for backward compatibility
_ensure_columns = ensure_db_columns


# ---------------------------------------------------------------------------
# Calendar & Contact Utilities
# ---------------------------------------------------------------------------


def generate_calendar_url(
    title: str, description: str = "", start: str = "", end: str = ""
) -> str:
    """Generate a pre-filled Google Calendar web link."""
    params: dict[str, str] = {
        "action": "TEMPLATE",
        "text": title,
    }
    if description:
        params["details"] = description
    if start and end:
        params["dates"] = f"{start}/{end}"
    elif start:
        params["dates"] = f"{start}/{start}"
    return f"https://calendar.google.com/calendar/r/eventedit?{urllib.parse.urlencode(params)}"


def create_vcard_entry(
    name: str,
    email: str = "",
    phone: str = "",
    org: str = "",
    title: str = "",
    notes: str = "",
) -> str:
    """Generate a standard vCard (v3.0) entry string."""
    lines = ["BEGIN:VCARD", "VERSION:3.0"]
    if name:
        parts = name.strip().split()
        if len(parts) > 1:
            last = parts[-1]
            first = " ".join(parts[:-1])
            lines.append(f"N:{last};{first};;;")
        else:
            lines.append(f"N:;{name.strip()};;;")
        lines.append(f"FN:{name.strip()}")

    if org:
        lines.append(f"ORG:{org.strip()}")
    if title:
        lines.append(f"TITLE:{title.strip()}")
    if email:
        lines.append(f"EMAIL;TYPE=INTERNET,HOME:{email.strip()}")
    if phone:
        lines.append(f"TEL;TYPE=CELL:{phone.strip()}")
    if notes:
        lines.append(f"NOTE:{notes.strip()}")

    lines.append("END:VCARD\n")
    return "\n".join(lines)
