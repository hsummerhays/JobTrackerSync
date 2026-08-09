import sys
import os
import re
import csv
import json
import sqlite3
import hashlib
import uuid
import argparse
import shutil
import time
import pathlib
import tempfile
from datetime import datetime, date, timezone, timedelta
import pypdf
from dedup_utils import (
    merge_delimited_field,
    canonical_job_key,
    VALID_STATUSES,
    build_occurrence_fingerprint,
    should_prefer_status,
    normalize_string,
    locations_compatible,
    title_similarity,
    TERMINAL_STATUSES,
    UNREVIEWED_STATUSES,
)
from rich.console import Console
from rich.table import Table

# Set console encoding to UTF-8 to prevent emoji errors on Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# Initialize Rich Console for beautiful outputs
console = Console()

# Rules and configuration constants
CONFIG_PATH = "config.json"

# Rule 8 Skip list (compiled regex patterns)
SKIP_KEYWORDS = [
    r"\bAI\s+Trainer\b",
    r"\bDataAnnotation\b",
    r"\bQA\b", r"\bTest\b", r"\bTesting\b",
    r"\bWordPress\b",
    r"\bJunior\b", r"\bJr\b",
    r"\bService\s+Desk\b",
    r"\bHelp\s+Desk\b",
    r"\bTechnical\s+Support\b",
    r"\bManufacturing\s+Engineer\b",
    r"\bFPGA\b",
    r"\bDevOps\b",
    r"\bServiceNow\b"
]

# Rule 9 Priority list
PRIORITY_KEYWORDS = [
    r"\bSenior\s+Software\s+Engineer\b",
    r"\bBackend\s+Engineer\b",
    r"\bFull\s+Stack\s+Engineer\b",
    r"\bLead\s+Engineer\b",
    r"\bPrincipal\s+Engineer\b",
    r"\bSoftware\s+Engineer\s+III\b",
    r"\bSoftware\s+Engineer\s+IV\b"
]

# Rule 10 Tech keywords
TECH_KEYWORDS = [
    "C#", ".NET", "Java", "Spring Boot", "SQL Server", "PostgreSQL",
    "REST APIs", "GraphQL", "React", "Next.js", "Node.js", "AWS", "Azure"
]

TITLE_KEYWORDS = [
    "engineer", "developer", "programmer", "architect", "analyst", "lead",
    "specialist", "manager", "support", "trainer", "coordinator", "mgr",
    "associate", "worker", "selector", "janitor", "tasker", "operator",
    "technician", "clerk", "driver", "consultant"
]

UI_LABEL_PATTERN = r'(?i)(View Details?|Learn More|Apply Now|Easy Apply|Save Job|Show More|See More|Read More|Click Here)'

POTENTIAL_SKILLS = [
    "java", "c#", ".net", "python", "spring boot", "spring", "asp.net core",
    "react", "next.js", "graphql", "rest", "microservices", "docker",
    "kubernetes", "aws", "azure", "postgresql", "sql server", "sql",
    "power bi", "cube.js", "kafka", "rabbitmq", "redis", "clean architecture",
    "git", "linux", "ssis", "etl", "wcf", "scala", "go", "golang",
    "typescript", "angular", "vue", "vue.js", "vuejs", "nuxt", "nuxt.js", "node", "nodejs", "gcp", "google cloud",
    "terraform", "ansible", "jenkins", "ci/cd", "spark", "hadoop", "c++",
    "ruby", "rails", "php", "zend", "laravel", "django", "flask", "fastapi",
    "dynamodb", "mongodb", "cassandra", "oracle", "mariadb", "mysql",
    "elasticsearch", "solr", "snowflake", "redshift", "bigquery", "dbt",
    "airflow", "selenium", "cypress", "jest", "mocha", "manufacturing",
    "inventory", "logistics", "supply chain", "repair", "reporting",
    "business automation", "documentation", "workflow automation", "rma",
    "inventory management", "reconciliation", "compliance", "coordination"
]

SKILL_DISPLAY_NAMES = {
    "java": "Java", "c#": "C#", ".net": ".NET", "python": "Python",
    "spring boot": "Spring Boot", "spring": "Spring", "asp.net core": "ASP.NET Core",
    "react": "React", "next.js": "Next.js", "graphql": "GraphQL", "rest": "REST",
    "microservices": "Microservices", "docker": "Docker", "kubernetes": "Kubernetes",
    "aws": "AWS", "azure": "Azure", "postgresql": "PostgreSQL",
    "sql server": "SQL Server", "sql": "SQL", "power bi": "Power BI",
    "cube.js": "Cube.js", "kafka": "Kafka", "rabbitmq": "RabbitMQ",
    "redis": "Redis", "clean architecture": "Clean Architecture", "git": "Git",
    "linux": "Linux", "ssis": "SSIS", "etl": "ETL", "wcf": "WCF",
    "scala": "Scala", "go": "Go", "golang": "Go", "typescript": "TypeScript",
    "angular": "Angular", "vue": "Vue.js", "vue.js": "Vue.js", "vuejs": "Vue.js", "nuxt": "Vue.js", "nuxt.js": "Vue.js", "node": "Node.js", "nodejs": "Node.js",
    "gcp": "GCP", "google cloud": "GCP", "terraform": "Terraform",
    "ansible": "Ansible", "jenkins": "Jenkins", "ci/cd": "CI/CD",
    "spark": "Spark", "hadoop": "Hadoop", "c++": "C++", "ruby": "Ruby",
    "rails": "Rails", "php": "PHP", "zend": "Zend", "laravel": "Laravel",
    "django": "Django", "flask": "Flask", "fastapi": "FastApi",
    "dynamodb": "DynamoDB", "mongodb": "MongoDB", "cassandra": "Cassandra",
    "oracle": "Oracle", "mariadb": "MariaDB", "mysql": "MySQL",
    "elasticsearch": "Elasticsearch", "solr": "Solr", "snowflake": "Snowflake",
    "redshift": "Redshift", "bigquery": "BigQuery", "dbt": "dbt",
    "airflow": "Airflow", "selenium": "Selenium", "cypress": "Cypress",
    "jest": "Jest", "mocha": "Mocha", "manufacturing": "Manufacturing",
    "inventory": "Inventory", "logistics": "Logistics", "supply chain": "Supply Chain",
    "repair": "Repair", "reporting": "Reporting",
    "business automation": "Business Automation", "documentation": "Documentation",
    "workflow automation": "Workflow Automation", "rma": "RMA",
    "inventory management": "Inventory Management", "reconciliation": "Reconciliation",
    "compliance": "Compliance", "coordination": "Coordination"
}

# Rule 11 Legacy keywords
LEGACY_KEYWORDS = [
    "FileMaker", "Perl", "Monolith", "Legacy Java", "Enterprise modernization"
]

# FAANG scale companies for Rule 12 comparison
FAANG_COMPANIES = ["Google", "Apple", "Meta", "Facebook", "Amazon", "Netflix", "Microsoft"]

# Incremental sync: bump this whenever a parser change should force re-processing of unchanged PDFs.
PARSER_VERSION = "1.3.1"


def hash_pdf_file(pdf_path):
    """Return a stable content hash (MD5) for a PDF file, or None on error."""
    try:
        hasher = hashlib.md5()
        with open(pdf_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except OSError:
        return None


def initialize_processed_files_table(conn):
    """Create the processed_files table if it does not yet exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS processed_files (
            file_hash       TEXT NOT NULL,
            parser_version  TEXT NOT NULL,
            file_path       TEXT,
            file_size       INTEGER,
            modified_time   REAL,
            processed_at    TEXT,
            status          TEXT,
            error_message   TEXT,
            PRIMARY KEY (file_hash, parser_version)
        )
    """)
    conn.commit()


def check_pdf_processed(conn, file_hash, parser_version):
    """Return True if this hash+version was previously processed successfully."""
    row = conn.execute(
        "SELECT status FROM processed_files WHERE file_hash = ? AND parser_version = ?",
        (file_hash, parser_version)
    ).fetchone()
    return row is not None and row[0] == "success"


def record_pdf_processed(conn, file_hash, parser_version, file_path, file_size, modified_time, status, error_message=None):
    """Upsert a processed_files record after a PDF has been handled."""
    conn.execute("""
        INSERT INTO processed_files (file_hash, parser_version, file_path, file_size, modified_time, processed_at, status, error_message)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(file_hash, parser_version) DO UPDATE SET
            file_path      = excluded.file_path,
            file_size      = excluded.file_size,
            modified_time  = excluded.modified_time,
            processed_at   = excluded.processed_at,
            status         = excluded.status,
            error_message  = excluded.error_message
    """, (
        file_hash, parser_version, file_path, file_size, modified_time,
        datetime.now(timezone.utc).isoformat(), status, error_message
    ))
    conn.commit()

def clean_company_name(comp):
    if not comp: return ""
    # Strip common email subject/notification formatting artifacts
    # "Jobs at Brady Corporation" -> "Brady Corporation"
    # "(Remote) at Globe Life" -> "Globe Life"
    # "at Globe Life" -> "Globe Life"
    cleaned = re.sub(r'(?i)^\s*Jobs\s+at\s+', '', comp)
    cleaned = re.sub(r'(?i)^\s*\(Remote\)\s+at\s+', '', cleaned)
    cleaned = re.sub(r'(?i)^\s*at\s+', '', cleaned)
    cleaned = re.sub(r'(?i)\s+is\s+hiring\b.*', '', cleaned)
    cleaned = re.sub(r'(?i)\s+is\s+looking\s+for\b.*', '', cleaned)
    cleaned = re.sub(r'(?i)\bhas\s+an\s+open\s+position\b.*', '', cleaned)
    cleaned = re.sub(r'\s*\.\.\.\s*$', '', cleaned)
    return cleaned.strip()

# Known aggregator/job-board brands that sometimes appear as "company" inside
# other providers' digest emails (e.g. Ladders posts jobs on LinkedIn), or are
# deliberately used as a placeholder "company" for digest-style postings where
# no per-job employer can be extracted (see is_aggregator_placeholder below).
AGGREGATOR_PROVIDER_NAMES = {
    "ladders", "ladders-dailydigest", "theladders", "the ladders",
    "linkedin", "indeed", "glassdoor", "ziprecruiter",
    "jobs.utah.gov", "jobs.utah.gov-dailysummary",
    "actively recruiting",
}


def is_aggregator_placeholder(company):
    """True if `company` is an aggregator/digest placeholder rather than a real
    employer name, e.g. "Jobs.utah.gov-DailySummary" or "Ladders-DailyDigest".
    These placeholders must never participate in canonical-key matching --
    two unrelated digest postings from the same aggregator would otherwise
    look like the same "employer" and get merged or reapply-cancelled."""
    comp_lower = (company or "").strip().lower()
    if not comp_lower:
        return False
    return comp_lower in AGGREGATOR_PROVIDER_NAMES or "dailysummary" in comp_lower or "dailydigest" in comp_lower


def is_valid_company(company, provider=None):
    if not company:
        return False
    # Normalize OCR spacing first
    comp = normalize_ocr_spacing(company)
    # Collapse multiple spaces to a single space
    comp = re.sub(r'\s+', ' ', comp.strip())
    if not comp:
        return False
    comp_lower = comp.lower()
    # Digest/summary placeholder rows (e.g. "Jobs.utah.gov-DailySummary",
    # "Ladders-DailyDigest") are valid tracker rows even though they aren't a
    # real employer -- is_aggregator_placeholder() is what keeps them out of
    # canonical-key matching, not rejection here. This must run before the
    # bare-provider-name rejection below, since those exact placeholder
    # strings are also listed in AGGREGATOR_PROVIDER_NAMES (to reject the
    # *unsuffixed* provider name, e.g. "jobs.utah.gov" on its own).
    if "dailysummary" in comp_lower or "dailydigest" in comp_lower:
        return True
    # Reject job board / provider names that should never appear as employer names.
    if comp_lower in AGGREGATOR_PROVIDER_NAMES:
        return False
    # Reject if contains slash or backslash (typically indicates a tech stack heading)
    if "/" in comp or "\\" in comp:
        return False
    # Reject if composed entirely of tech keywords
    tech_keywords = {"java", "typescript", "aws", "python", "c#", ".net", "azure", "react", "angular", "node", "sql", "javascript"}
    comp_words = [w.strip() for w in re.split(r"[\s,\-|]+", comp_lower) if w.strip()]
    if comp_words and all(w in tech_keywords for w in comp_words):
        return False

    # Reject placeholders
    if comp_lower in ["unknown", "unknown/other", "undisclosed", "undisclosed company"]:
        return False
    # Check if starts with lowercase letter or number
    if comp[0].islower() or comp[0].isdigit():
        return False
    # Check length
    if len(comp) > 100:
        return False
    # Reject Indeed recommendation banners / email digest artifacts
    recommendation_banners = [
        "based on your title",
        "based on your location",
        "recommended for you",
        "update your profile"
    ]
    if any(banner in comp_lower for banner in recommendation_banners):
        return False
    # Reject company names ending in digest artifacts or truncated text
    truncated_endings = ["...", "more ...", "view more", "see more", "more..."]
    if any(comp_lower.endswith(ending) for ending in truncated_endings):
        return False
    # Reject UI element strings captured instead of company names
    ui_elements = {"view details", "learn more", "apply now", "easy apply", "save job", "show more",
                   "see more", "read more", "click here", "get started", "sign in", "log in",
                   "easy", "be seen first", "do not share this email", "1-click apply",
                   "just posted", "systems"}
    if comp_lower in ui_elements:
        return False
    # Reject if a UI label was concatenated onto the end (PDF parser artifact)
    ui_label_endings = ["view details", "view detail", "learn more", "apply now", "easy apply",
                        "save job", "show more", "see more", "read more", "click here", "be seen first", "do not share this email", "1-click apply"]
    if any(comp_lower.endswith(suf) for suf in ui_label_endings):
        return False
    # Check for exclusion words
    exclude_words = ["application", "interest", "submit", "hiring", "apply", "gmail", "http", "resume", "position", "salary", "compensation", "message", "do not share this email", "be seen first", "1-click apply", "your job listings", "job listings", "job summary", "years exp required", "yrs exp required"]
    if any(w in comp_lower for w in exclude_words):
        return False
    # Reject if contains date/time timestamp pattern
    if re.search(r'\b\d{1,2}/\d{1,2}/\d{2,4}\b', comp) or re.search(r'\b\d{1,2}:\d{2}\s*(AM|PM|am|pm)?\b', comp):
        return False
    # Reject if it matches location-only terms
    location_names = {
        "salt lake city", "salt lake", "slc", "lehi", "provo", "ogden", "sandy", "draper", "murray", "west valley", 
        "west valley city", "eagle mountain", "richmond", "virginia", "utah", "california", "texas", "colorado", 
        "denver", "seattle", "washington", "new york", "boston", "remote", "hybrid", "on-site", "onsite", "coast",
        "east coast", "west coast", "coast)", "charlotte", "atlanta", "austin", "dallas", "houston", "phoenix"
    }
    if comp_lower in location_names:
        return False
    # Reject if ends with state/location suffix or abbreviation (e.g. , UT, , CA, or ending in UT/CA/VA/Coast)
    if re.search(r'\b(UT|CA|VA|TX|NY|FL|CO|WA|IL|MA|GA|MI|OH|PA|NJ|Utah|California|Virginia|Coast|Remote|Hybrid)\)?$', comp):
        return False
    # Check if it looks like a sentence (e.g., contains multiple words with lowercase verbs/pronouns or too many words)
    if len(comp.split()) > 7:
        return False
    # Check punctuation at the end or typical sentence markers
    # Allow trailing period only for short abbreviations like "Ltd.", "Inc.", "Corp."
    if '?' in comp or '!' in comp:
        return False
    if comp.endswith('.') and len(comp.split()[-1]) > 5:
        return False
    if re.match(r'^posted:\s*', comp_lower):
        return False
    return True


def compute_priority(recommendation, action, age_days=0):
    if recommendation in ["★☆☆☆☆ Skip", "★★☆☆☆ Low"]:
        return "P4 – Ignore"
    elif recommendation == "★★★☆☆ Maybe":
        return "P3 – Investigate"

    if action == "Apply" and recommendation == "★★★★★ Apply Now":
        priority = "P1 – Apply today"
    elif action in ["Apply", "Contact Recruiter"]:
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

MAX_OLD_BACKUPS_TO_KEEP = 3
# Snapshot taken once, at import time, so every backup_file_if_exists() call
# in this process can tell "made during this run" from "made by a past run".
_RUN_START_TIMESTAMP = datetime.now().strftime('%Y%m%d%H%M%S%f')

def _backup_timestamp(backup_path):
    return backup_path.rsplit(".bak.", 1)[-1]

def backup_file_if_exists(path):
    """Copy `path` to a timestamped `.bak.<timestamp>` sibling before a risky
    write, so there's a recoverable snapshot to restore from if the write is
    interrupted partway through. No-op if `path` doesn't exist yet.
    Prunes down to the most recent MAX_OLD_BACKUPS_TO_KEEP .bak files from
    past runs to save space, but never removes a backup made during this
    run -- a single run can call this multiple times (e.g. once before
    jobs.db and once before the tracker CSV, or an extra one-time backfill
    snapshot), and every one of those must survive until the run finishes,
    regardless of how many calls that turns out to be."""
    if not os.path.exists(path):
        return None
    backup_path = f"{path}.bak.{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    try:
        shutil.copy2(path, backup_path)

        import glob
        directory = os.path.dirname(os.path.abspath(path))
        base_name = os.path.basename(path)
        pattern = os.path.join(directory, f"{base_name}.bak.*")
        existing_backups = sorted(glob.glob(pattern), reverse=True)
        older_run_backups = [b for b in existing_backups if _backup_timestamp(b) < _RUN_START_TIMESTAMP]
        for old_backup in older_run_backups[MAX_OLD_BACKUPS_TO_KEEP:]:
            try:
                os.remove(old_backup)
            except OSError:
                pass

        return backup_path
    except OSError as e:
        console.print(f"[dim yellow]Could not back up {path} before writing: {e}[/dim yellow]")
        return None


def write_tracker_csv_atomic(tracker_path, fieldnames, rows, extrasaction='raise'):
    """Write rows to tracker_path via a temp file + atomic rename, so a crash
    or interruption mid-write can't leave master_tracker.csv truncated."""
    tracker_dir = os.path.dirname(os.path.abspath(tracker_path)) or "."
    fd, tmp_path = tempfile.mkstemp(dir=tracker_dir, prefix=".tmp_tracker_", suffix=".csv")
    try:
        with os.fdopen(fd, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction=extrasaction)
            writer.writeheader()
            writer.writerows(rows)
        os.replace(tmp_path, tracker_path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def initialize_tracker(tracker_path):
    """Ensure the tracker CSV exists and has the correct headers."""
    if not os.path.exists(tracker_path):
        with open(tracker_path, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["Job ID", "Review Status", "Job Type", "Company", "Position", "Location", "URL", "Provider", "Source PDF", "Source Index", "Confidence", "Fit Score", "Priority", "Company Type", "Recommendation", "Tracker Status", "Disposition", "Action", "Existing Company", "Age (days)", "Reason", "Matched Skills", "Missing Skills", "Date Added", "Last Seen", "Notes", "Recruiter", "Hiring Manager", "Fingerprint", "Previous Job ID"])
        console.print(f"[green]Initialized new tracker at {tracker_path}[/green]")

def clean_existing_tracker(tracker_path):
    """Clean up any existing rows in the tracker that fail the company name rules and migrate schema if needed."""
    if not os.path.exists(tracker_path):
        return
    
    rows_to_keep = []
    cleaned_any = False
    migrated_schema = False
    
    expected_headers = [
        "Job ID", "Review Status", "Job Type", "Company", "Position", "Location", "URL", "Provider",
        "Source PDF", "Source Index", "Confidence", "Fit Score", "Priority", "Company Type",
        "Recommendation", "Tracker Status", "Disposition", "Action", "Existing Company",
        "Age (days)", "Reason", "Matched Skills", "Missing Skills", "Date Added", "Last Seen", "Notes", "Recruiter", "Hiring Manager",
        "Fingerprint", "Previous Job ID"
    ]

    try:
        with open(tracker_path, mode='r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            if not fieldnames:
                return
            rows = list(reader)
            
        # Check if any expected header is missing
        if any(h not in fieldnames for h in expected_headers):
            migrated_schema = True
            
        company_counts = {}
        for row in rows:
            c = row.get("Company", "").strip().lower()
            if c:
                company_counts[c] = company_counts.get(c, 0) + 1
                
        ui_label_strip = re.compile(
            r'(?i)(View Details?|Learn More|Apply Now|Easy Apply|Save Job|Show More|See More|Read More|Click Here)$'
        )
        for row in rows:
            company = row.get("Company", "")
            position = row.get("Position", "")
            location = row.get("Location", "")
            # Strip trailing UI labels that were concatenated by the parser (e.g. "Acme Corp.View Details")
            cleaned_company = ui_label_strip.sub('', company).strip()
            cleaned_company = clean_company_name(cleaned_company)
            # Collapse multiple spaces to a single space
            cleaned_company = re.sub(r'\s+', ' ', cleaned_company).strip()
            if cleaned_company != company:
                company = cleaned_company
                row["Company"] = company
                cleaned_any = True
            if not company or not is_valid_company(company, row.get("Provider")):
                cleaned_any = True
                continue
            comp_lower = company.strip().lower()
            generic_roles = {
                "software developer", "software engineer", "java developer", 
                "backend developer", "backend engineer", "developer", "engineer",
                "full stack developer", "full stack engineer", "java software developer",
                "java software engineer", "j2ee developer", "j2ee software developer",
                "software developer", "c developer", "react js developer", ".net developer"
            }
            conversational_phrases = [
                "could be", "with your", "your background", "your experience", 
                "is hiring", "apply now", "feel free", "hiring for", "interested in", 
                "you're interested", "you would be", "contribute to", "opportunities you", 
                "great fit", "little different", "looking for", "would be a", 
                "could contribute", "background as a", "expertise with", "offers remote",
                "flexibility of", "competitive pay"
            ]
            pos_lower = position.lower()
            loc_lower = location.lower()
            is_conversational = any(phrase in comp_lower or phrase in pos_lower or phrase in loc_lower for phrase in conversational_phrases)
            
            # Check for invalid company names starting with punctuation or containing generic terms
            bad_company = (
                re.match(r'^[\W_]', comp_lower) or  # starts with punctuation/symbol
                any(phrase in comp_lower for phrase in ["based compensation", "no salary", "remote", "hybrid", "salary", "compensation", "apply now", "hourly", "contract"])
            )
            
            if (comp_lower.startswith("hugh summerhays") or
                "gmail" in comp_lower or
                comp_lower.startswith("1 message") or
                comp_lower.startswith("looking for") or
                comp_lower.startswith("https://") or
                comp_lower == "(remote)" or
                comp_lower in generic_roles or
                "create" in comp_lower or
                "create" in position.lower() or
                is_conversational or
                bad_company):
                cleaned_any = True
                continue
            
            migrated_row = {}
            migrated_row["Company"] = company
            migrated_row["Position"] = position
            migrated_row["Location"] = location
            migrated_row["URL"] = row.get("URL", row.get("Link", ""))
            migrated_row["Provider"] = row.get("Provider", "Unknown")
            migrated_row["Source PDF"] = row.get("Source PDF", "Unknown")
            migrated_row["Confidence"] = row.get("Confidence", "🟡 Medium")
            status = row.get("Tracker Status", row.get("Status", "New"))
            if status not in ["New", "Applied", "Phone Screen", "Technical Interview", "Recruiter Submitted", "Waiting", "Rejected", "Cancelled", "Ghosted", "Expired", "Offer", "Accepted"]:
                if status == "Recruiter":
                    status = "Recruiter Submitted"
                elif status == "Interview":
                    status = "Phone Screen"
                elif status == "Technical":
                    status = "Technical Interview"
                elif status in ["Skip", "Duplicate"]:
                    status = "Cancelled"
                else:
                    status = "New"
            migrated_row["Tracker Status"] = status
            
            review_status = row.get("Review Status")
            if not review_status:
                if status in ["Applied", "Phone Screen", "Technical Interview", "Recruiter Submitted", "Waiting", "Offer", "Accepted"]:
                    review_status = "Applied"
                elif status in ["Rejected", "Cancelled", "Ghosted", "Expired"]:
                    review_status = "Closed"
                else:
                    review_status = "Imported"
            migrated_row["Review Status"] = review_status
            
            disposition_map = {
                "New": "Apply",
                "Applied": "Waiting",
                "Phone Screen": "Active",
                "Technical Interview": "Active",
                "Recruiter Submitted": "Active",
                "Waiting": "Active",
                "Rejected": "Closed",
                "Cancelled": "Closed",
                "Ghosted": "Closed",
                "Expired": "Closed",
                "Offer": "Active",
                "Accepted": "Closed"
            }
            disposition = row.get("Disposition", disposition_map.get(status, "Apply"))
            migrated_row["Disposition"] = disposition
            migrated_row["Date Added"] = row.get("Date Added", datetime.now().strftime("%Y-%m-%d"))
            migrated_row["Last Seen"] = row.get("Last Seen", migrated_row["Date Added"])
            
            notes = row.get("Notes", "")
            migrated_row["Notes"] = notes
            
            # Job ID
            job_id = row.get("Job ID")
            if not job_id:
                job_id = hashlib.md5(f"{company.strip().lower()}|{position.strip().lower()}|{location.strip().lower()}".encode('utf-8')).hexdigest()
            migrated_row["Job ID"] = job_id
            
            # Score this row through evaluate_job() -- the same rules engine
            # used for freshly-parsed postings -- instead of a second, drifted
            # copy of the scoring math. That duplicate never enforced Rule 6
            # (reject postings outside Utah/Remote) or the incomplete-listing
            # recommendation cap, so out-of-state and digest-only postings
            # could silently regain Strong/Apply Now every time the tracker
            # was cleaned -- and this runs on every sync, not just --rescore,
            # which is why those scores kept coming back. The CSV has no
            # persisted posting text, so context is approximated from fields
            # already on the row, the same fallback --rescore uses for DB
            # rows that predate raw_context.
            approx_context = f"{position} {company} {row.get('Matched Skills', '')} {row.get('Missing Skills', '')} {row.get('Reason', '')} {notes}"
            eval_job = {
                "title": position,
                "company": company,
                "location": location,
                "raw_context": approx_context,
                "provider": row.get("Provider"),
                "source_index": row.get("Source Index"),
                "url": row.get("URL", row.get("Link")),
            }
            (
                _, confidence, eval_notes, fit_score, _temp_priority, comp_type,
                rec, reason, matched_skills, missing_skills, job_type,
            ) = evaluate_job(eval_job)

            migrated_row["Job Type"] = job_type
            migrated_row["Company Type"] = comp_type
            migrated_row["Fit Score"] = int(fit_score)
            migrated_row["Confidence"] = confidence
            migrated_row["Reason"] = reason
            migrated_row["Matched Skills"] = matched_skills
            migrated_row["Missing Skills"] = missing_skills

            if "Local/Onsite restriction detected" in eval_notes and "Local/Onsite restriction detected" not in notes:
                notes = notes + "; Local/Onsite restriction detected" if notes else "Local/Onsite restriction detected"
                migrated_row["Notes"] = notes

            # Apply Digest-Based Priority Decay (Half-Life) for "New" (un-actioned) jobs
            company_lower = company.lower()
            provider_lower = migrated_row.get("Provider", "").lower()
            is_digest = ("dailysummary" in company_lower or 
                         "dailydigest" in company_lower or 
                         "ladders" in provider_lower or 
                         "jobs.utah.gov" in provider_lower)
            if is_digest and status == "New":
                date_added_str = migrated_row.get("Date Added", "")
                if date_added_str:
                    try:
                        added = date.fromisoformat(date_added_str)
                        age_days = (date.today() - added).days
                        if 3 <= age_days <= 7:
                            if rec in ["★★★★★ Apply Now", "★★★★☆ Strong"]:
                                rec = "★★★☆☆ Maybe"
                        elif age_days >= 8:
                            if rec in ["★★★★★ Apply Now", "★★★★☆ Strong", "★★★☆☆ Maybe"]:
                                rec = "★★☆☆☆ Low"
                    except (ValueError, TypeError):
                        pass
            migrated_row["Recommendation"] = rec
            
            # Action calculation
            if status != "New":
                if status in ["Applied", "Waiting", "Phone Screen", "Technical Interview", "Recruiter Submitted", "Offer", "Accepted"]:
                    action = "Already Applied"
                elif status in ["Rejected", "Cancelled", "Ghosted", "Expired"]:
                    action = "Ignore"
                else:
                    action = "Ignore"
            else:
                if comp_type == "Recruiting Firm" and rec in ["★★★★★ Apply Now", "★★★★☆ Strong"]:
                    action = "Contact Recruiter"
                elif rec in ["★★★★★ Apply Now", "★★★★☆ Strong"]:
                    action = "Apply"
                elif rec == "★★★☆☆ Maybe":
                    action = "Review"
                else:
                    action = "Ignore"
                    
            if status == "New":
                act = action
            else:
                act = row.get("Action", action)
                if act not in ["Apply", "Contact Recruiter", "Review", "Ignore", "Already Applied", "Waiting", "Interview", "Rejected", "Cancelled", "Expired", "Offer", "Accepted"]:
                    if "apply" in act.lower():
                        act = "Apply"
                    elif "recruiter" in act.lower():
                        act = "Contact Recruiter"
                    elif "review" in act.lower():
                        act = "Review"
                    else:
                        act = "Ignore"
                # Correct stale Contact Recruiter for non-recruiting-firm companies
                if act == "Contact Recruiter" and comp_type != "Recruiting Firm":
                    act = "Apply" if rec in ["★★★★★ Apply Now", "★★★★☆ Strong"] else "Review"
            migrated_row["Action"] = act
            
            # Priority calculation (always recalculated to standardize formatting)
            age_val = migrated_row.get("Age (days)")
            age_days = int(age_val) if age_val and str(age_val).isdigit() else 0
            migrated_row["Priority"] = compute_priority(rec, act, age_days)
            
            # Existing Company (same employer already tracked)
            known_tracker_companies = {"lvt", "decerto", "explorer software group", "infinity software development", "clearwaters.it", "new walton services", "american auto auction group", "co-diagnostics", "sunwest bank", "weave", "medallion bank"}
            comp_cleaned = company.strip().lower()
            current_val = row.get("Existing Company", row.get("Already in Tracker"))
            if comp_cleaned in known_tracker_companies:
                migrated_row["Existing Company"] = "Yes"
            elif company_counts.get(comp_cleaned, 0) <= 1:
                migrated_row["Existing Company"] = "No"
            else:
                migrated_row["Existing Company"] = current_val if current_val in ["Yes", "No"] else "No"
            
            # Preserve Recruiter & Hiring Manager
            migrated_row["Recruiter"] = row.get("Recruiter", "")
            migrated_row["Hiring Manager"] = row.get("Hiring Manager", "")
            
            source_index = row.get("Source Index", "")
            if not source_index and notes:
                match = re.search(r"Source Index:\s*([^\n,]+)", notes)
                if match:
                    source_index = match.group(1).strip()
            migrated_row["Source Index"] = source_index

            # Preserve audit fields; backfill Fingerprint for rows that predate
            # the column so every row has a stable identity key. Aggregator
            # placeholders use the occurrence-key formula (see
            # build_occurrence_fingerprint) instead of canonical_job_key, same
            # as the initial parse, so backfill and import never diverge.
            if is_aggregator_placeholder(company) and source_index:
                # Always recompute aggregator fingerprint in case previous version was invalid
                migrated_row["Fingerprint"] = build_occurrence_fingerprint(
                    row.get("Provider", ""), row.get("Source PDF", ""), row.get("Date Added", ""), source_index, position
                )
            elif row.get("Fingerprint"):
                migrated_row["Fingerprint"] = row["Fingerprint"]
            else:
                migrated_row["Fingerprint"] = canonical_job_key(company, position, location)
            migrated_row["Previous Job ID"] = row.get("Previous Job ID", "")

            rows_to_keep.append(migrated_row)
                
        # Always sync with SQLite database 'jobs.db' on launch. Snapshot both
        # files first -- these are two separate writes, not one transaction.
        backup_file_if_exists("jobs.db")
        backup_file_if_exists(tracker_path)
        success = save_to_sqlite("jobs.db", rows_to_keep)

        # Always save CSV back to disk to preserve updated skills/scores calculations
        if success:
            write_tracker_csv_atomic(tracker_path, expected_headers, rows_to_keep, extrasaction='ignore')
            console.print(f"[green]Synchronized and recalculated all tracking rows in {tracker_path}[/green]")
        else:
            console.print("[red]Database save failed, aborting CSV update in clean_existing_tracker.[/red]")
    except Exception as e:
        console.print(f"[yellow]Failed to clean/migrate existing tracker: {e}[/yellow]")

def _ensure_columns(cursor, table, columns):
    """Idempotently add any of `columns` (list of (name, type)) missing from
    `table`, used both for self-healing older DBs and for schema-drift
    recovery -- additive only, never drops or recreates the table."""
    for col, col_type in columns:
        try:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError:
            pass


def save_to_sqlite(db_path, jobs_list):
    """Save or upsert a list of jobs to the SQLite database."""
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Create table if not exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                review_status TEXT,
                job_type TEXT,
                company TEXT,
                position TEXT,
                location TEXT,
                url TEXT,
                provider TEXT,
                source_pdf TEXT,
                confidence TEXT,
                fit_score INTEGER,
                priority TEXT,
                company_type TEXT,
                recommendation TEXT,
                tracker_status TEXT,
                disposition TEXT,
                action TEXT,
                existing_company TEXT,
                reason TEXT,
                matched_skills TEXT,
                missing_skills TEXT,
                date_added TEXT,
                last_seen TEXT,
                notes TEXT,
                recruiter TEXT,
                hiring_manager TEXT,
                fingerprint TEXT,
                previous_job_id TEXT,
                raw_context TEXT
            )
        """)

        # Drop old statuses table if it exists
        cursor.execute("DROP TABLE IF EXISTS statuses")

        # Create job_workflow table to store persistent user workflow state
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS job_workflow (
                job_id TEXT PRIMARY KEY,
                tracker_status TEXT,
                review_status TEXT,
                action TEXT,
                disposition TEXT,
                updated_at TEXT,
                updated_by TEXT,
                notes TEXT,
                follow_up_date TEXT,
                last_contact_date TEXT,
                status_source TEXT
            )
        """)

        # Create processed_files table for incremental sync
        initialize_processed_files_table(conn)

        # Migrate data from old job_status table if it exists
        try:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='job_status'")
            if cursor.fetchone():
                cursor.execute("""
                    INSERT OR IGNORE INTO job_workflow (job_id, tracker_status, updated_at, updated_by, notes, follow_up_date, last_contact_date, status_source)
                    SELECT job_id, tracker_status, updated_at, updated_by, notes, follow_up_date, last_contact_date, 'migration' FROM job_status
                """)
                cursor.execute("DROP TABLE IF EXISTS job_status")
        except sqlite3.OperationalError:
            pass

        # Add columns dynamically to jobs and job_workflow in case the tables already existed without them
        _ensure_columns(cursor, "jobs", [
            ("recruiter", "TEXT"),
            ("hiring_manager", "TEXT"),
            ("fingerprint", "TEXT"),
            ("previous_job_id", "TEXT"),
            ("raw_context", "TEXT"),
        ])
        _ensure_columns(cursor, "job_workflow", [
            ("review_status", "TEXT"),
            ("action", "TEXT"),
            ("disposition", "TEXT"),
            ("updated_at", "TEXT"),
            ("updated_by", "TEXT"),
            ("notes", "TEXT"),
            ("follow_up_date", "TEXT"),
            ("last_contact_date", "TEXT"),
            ("status_source", "TEXT"),
        ])

        # One-time backfill: pre-existing rows created before the fingerprint
        # column existed won't have one yet. Back up the DB file before writing,
        # since this touches every existing row.
        cursor.execute("SELECT COUNT(*) FROM jobs WHERE fingerprint IS NULL OR fingerprint = ''")
        if cursor.fetchone()[0] > 0:
            conn.commit()
            backup_file_if_exists(db_path)
            cursor.execute("SELECT job_id, company, position, location FROM jobs WHERE fingerprint IS NULL OR fingerprint = ''")
            rows_to_backfill = cursor.fetchall()
            cursor.executemany(
                "UPDATE jobs SET fingerprint = ? WHERE job_id = ?",
                [
                    (canonical_job_key(company or "", position or "", location or ""), job_id)
                    for job_id, company, position, location in rows_to_backfill
                ]
            )
            conn.commit()

        # Populate job_workflow table with existing status data from jobs table if available
        try:
            cursor.execute("""
                INSERT OR IGNORE INTO job_workflow (job_id, tracker_status, review_status, action, disposition)
                SELECT job_id, tracker_status, review_status, action, disposition FROM jobs WHERE job_id IS NOT NULL
            """)
        except sqlite3.OperationalError:
            pass

        # Note: neither expired nor previously-applied jobs rediscovered on a
        # later run are deleted here. A rediscovered Applied/Interviewing/etc.
        # posting is merged into its existing record by the dedup pass in
        # main(); a rediscovered Expired posting instead becomes a new row
        # linked back to the old one via Previous Job ID. Either way the old
        # row (and its job_workflow history) is kept, never orphaned or
        # force-deleted.

        # Retrieve persisted workflow values
        cursor.execute("SELECT job_id, tracker_status, review_status, action, disposition, status_source FROM job_workflow")
        persisted_workflows = {row[0]: {
            "tracker_status": row[1],
            "review_status": row[2],
            "action": row[3],
            "disposition": row[4],
            "status_source": row[5],
        } for row in cursor.fetchall()}

        # Check for recent applications for "New" jobs. Must match company AND
        # position (and a compatible location) -- a company-only match would
        # auto-cancel an unrelated role just because some other role at the same
        # company was recently applied to. Aggregator/digest placeholder
        # "companies" are skipped entirely since they don't identify a real
        # employer and would otherwise cancel unrelated postings against
        # each other.
        try:
            today = datetime.now()
            sixty_days_ago = (today - timedelta(days=60)).strftime('%Y-%m-%d')
            applied_statuses = ("Applied", "Interviewing", "Technical Interview", "Phone Screen", "Recruiter Contact", "Offer", "Waiting")
            placeholders = ','.join(['?'] * len(applied_statuses))

            for job in jobs_list:
                current_status = job.get("Tracker Status", job.get("tracker_status", job.get("Status", job.get("status"))))
                if current_status != "New" and current_status:
                    continue
                company = job.get("Company", job.get("company"))
                position = job.get("Position", job.get("position"))
                location = job.get("Location", job.get("location"))
                if not company or not position or is_aggregator_placeholder(company):
                    continue

                query = f"""
                    SELECT date_added, position, location
                    FROM jobs
                    WHERE company = ?
                    AND tracker_status IN ({placeholders})
                    AND date_added >= ?
                    ORDER BY date_added DESC
                """
                cursor.execute(query, (company, *applied_statuses, sixty_days_ago))
                match_date = None
                for cand_date, cand_position, cand_location in cursor.fetchall():
                    if normalize_string(cand_position or "") == normalize_string(position) and locations_compatible(cand_location or "", location or ""):
                        match_date = cand_date
                        break

                if match_date:
                    recent_date = datetime.strptime(match_date[:10], '%Y-%m-%d')
                    days_since = (today - recent_date).days
                    reason_text = f"Already Applied within {days_since} days"

                    for k in ["Tracker Status", "tracker_status", "Status", "status"]:
                        if k in job:
                            job[k] = "Cancelled"

                    job["Review Status"] = "Closed"
                    job["review_status"] = "Closed"
                    job["Action"] = "Ignore"
                    job["action"] = "Ignore"
                    job["Disposition"] = "Closed"
                    job["disposition"] = "Closed"
                    job["Reason"] = reason_text
                    job["reason"] = reason_text
        except Exception as e:
            console.print(f"[dim yellow]Could not check for recent applications to auto-cancel duplicates: {e}[/dim yellow]")

        # Update jobs in-memory with their persisted workflow state. The persisted
        # (DB) status wins unless the incoming status is a genuine improvement per
        # should_prefer_status (dedup_utils) -- e.g. a still-"New" incoming status
        # never displaces a persisted "Applied". On top of that, an active
        # application status (Applied, Interviewing, ...) can never be
        # automatically downgraded into a terminal status (Cancelled, Rejected,
        # ...) by this parser-driven pass, even in the rare case
        # should_prefer_status would otherwise allow a terminal status to win.
        # This protection does NOT depend on status_source == "user" -- rows
        # migrated from an older schema, or written before status_source
        # existed, have a blank status_source and need the same protection as
        # a status a human set by hand.
        for job in jobs_list:
            jid = job.get("Job ID", job.get("job_id"))
            if jid and jid in persisted_workflows:
                pw = persisted_workflows[jid]
                persisted_status = pw.get("tracker_status")
                current_status = job.get("Tracker Status", job.get("tracker_status", job.get("Status", job.get("status"))))

                persisted_is_active_application = (
                    persisted_status not in TERMINAL_STATUSES
                    and persisted_status not in UNREVIEWED_STATUSES
                )
                parser_terminal_downgrade = (
                    persisted_is_active_application
                    and current_status in TERMINAL_STATUSES
                )
                keep_persisted = parser_terminal_downgrade or not should_prefer_status(persisted_status, current_status)

                if keep_persisted:
                    for target_key, source_key in [
                        ("Tracker Status", "tracker_status"),
                        ("Review Status", "review_status"),
                        ("Action", "action"),
                        ("Disposition", "disposition")
                    ]:
                        val = pw[source_key]
                        if val:
                            job[target_key] = val
                            lower_key = target_key.lower().replace(" ", "_")
                            if lower_key in job:
                                job[lower_key] = val
        
        def _upsert_all_jobs():
            # Upsert jobs and job_workflow
            for job in jobs_list:
                jid = job.get("Job ID", job.get("job_id"))
                tracker_status = job.get("Tracker Status", job.get("tracker_status", job.get("Status", job.get("status"))))
                review_status = job.get("Review Status", job.get("review_status"))
                action = job.get("Action", job.get("action"))
                disposition = job.get("Disposition", job.get("disposition"))
                status_source = job.get("_status_source", "parser")

                if jid:
                    cursor.execute("""
                        INSERT INTO job_workflow (job_id, tracker_status, review_status, action, disposition, updated_at, updated_by, status_source)
                        VALUES (?, ?, ?, ?, ?, datetime('now'), 'system', ?)
                        ON CONFLICT(job_id) DO UPDATE SET
                            updated_at = CASE
                                WHEN coalesce(tracker_status, '') != coalesce(excluded.tracker_status, '')
                                     OR coalesce(review_status, '') != coalesce(excluded.review_status, '')
                                     OR coalesce(action, '') != coalesce(excluded.action, '')
                                     OR coalesce(disposition, '') != coalesce(excluded.disposition, '')
                                THEN excluded.updated_at
                                ELSE updated_at
                            END,
                            updated_by = CASE
                                WHEN coalesce(tracker_status, '') != coalesce(excluded.tracker_status, '')
                                     OR coalesce(review_status, '') != coalesce(excluded.review_status, '')
                                     OR coalesce(action, '') != coalesce(excluded.action, '')
                                     OR coalesce(disposition, '') != coalesce(excluded.disposition, '')
                                THEN excluded.updated_by
                                ELSE updated_by
                            END,
                            status_source = CASE
                                WHEN coalesce(tracker_status, '') != coalesce(excluded.tracker_status, '')
                                     OR coalesce(review_status, '') != coalesce(excluded.review_status, '')
                                     OR coalesce(action, '') != coalesce(excluded.action, '')
                                     OR coalesce(disposition, '') != coalesce(excluded.disposition, '')
                                THEN excluded.status_source
                                ELSE status_source
                            END,
                            tracker_status = excluded.tracker_status,
                            review_status = excluded.review_status,
                            action = excluded.action,
                            disposition = excluded.disposition
                    """, (jid, tracker_status, review_status, action, disposition, status_source))

                company = job.get("Company", job.get("company")) or ""
                position = job.get("Position", job.get("position")) or ""
                location = job.get("Location", job.get("location")) or ""
                fingerprint = job.get("Fingerprint", job.get("fingerprint")) or canonical_job_key(company, position, location)

                cursor.execute("""
                    INSERT INTO jobs (
                        job_id, review_status, job_type, company, position, location, url, provider,
                        source_pdf, confidence, fit_score, priority, company_type,
                        recommendation, tracker_status, disposition, action, existing_company,
                        reason, matched_skills, missing_skills, date_added, last_seen, notes, recruiter, hiring_manager,
                        fingerprint, previous_job_id, raw_context
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(job_id) DO UPDATE SET
                        review_status=excluded.review_status,
                        job_type=excluded.job_type,
                        company=excluded.company,
                        position=excluded.position,
                        location=excluded.location,
                        url=excluded.url,
                        provider=excluded.provider,
                        source_pdf=excluded.source_pdf,
                        confidence=excluded.confidence,
                        fit_score=excluded.fit_score,
                        priority=excluded.priority,
                        company_type=excluded.company_type,
                        recommendation=excluded.recommendation,
                        tracker_status=excluded.tracker_status,
                        disposition=excluded.disposition,
                        action=excluded.action,
                        existing_company=excluded.existing_company,
                        reason=excluded.reason,
                        matched_skills=excluded.matched_skills,
                        missing_skills=excluded.missing_skills,
                        date_added=excluded.date_added,
                        last_seen=excluded.last_seen,
                        notes=excluded.notes,
                        recruiter=excluded.recruiter,
                        hiring_manager=excluded.hiring_manager,
                        fingerprint=excluded.fingerprint,
                        previous_job_id=COALESCE(excluded.previous_job_id, previous_job_id),
                        raw_context=COALESCE(NULLIF(excluded.raw_context, ''), raw_context)
                """, (
                    jid,
                    job.get("Review Status", job.get("review_status")),
                    job.get("Job Type", job.get("job_type")),
                    company,
                    position,
                    location,
                    job.get("URL", job.get("url")),
                    job.get("Provider", job.get("provider")),
                    job.get("Source PDF", job.get("source_pdf")),
                    job.get("Confidence", job.get("confidence")),
                    job.get("Fit Score", job.get("fit_score")),
                    job.get("Priority", job.get("priority")),
                    job.get("Company Type", job.get("company_type")),
                    job.get("Recommendation", job.get("recommendation")),
                    tracker_status,
                    job.get("Disposition", job.get("disposition")),
                    job.get("Action", job.get("action")),
                    job.get("Existing Company", job.get("Already in Tracker", job.get("already_in_tracker"))),
                    job.get("Reason", job.get("reason")),
                    job.get("Matched Skills", job.get("matched_skills")),
                    job.get("Missing Skills", job.get("missing_skills")),
                    job.get("Date Added", job.get("date_added")),
                    job.get("Last Seen", job.get("last_seen", job.get("Date Added", job.get("date_added")))),
                    job.get("Notes", job.get("notes")),
                    job.get("Recruiter", job.get("recruiter")),
                    job.get("Hiring Manager", job.get("hiring_manager")),
                    fingerprint,
                    job.get("Previous Job ID", job.get("previous_job_id")),
                    job.get("Raw Context", job.get("raw_context")),
                ))

        try:
            _upsert_all_jobs()
            conn.commit()
            return True
        except sqlite3.OperationalError:
            # Schema drift (e.g. an older jobs.db missing a column the current
            # code writes) -- patch the schema additively and retry once, instead
            # of dropping the jobs table and losing every row not present in this
            # run's jobs_list.
            conn.rollback()
            _ensure_columns(cursor, "jobs", [
                ("review_status", "TEXT"),
                ("job_type", "TEXT"),
                ("company", "TEXT"),
                ("position", "TEXT"),
                ("location", "TEXT"),
                ("url", "TEXT"),
                ("provider", "TEXT"),
                ("source_pdf", "TEXT"),
                ("confidence", "TEXT"),
                ("fit_score", "INTEGER"),
                ("priority", "TEXT"),
                ("company_type", "TEXT"),
                ("recommendation", "TEXT"),
                ("tracker_status", "TEXT"),
                ("disposition", "TEXT"),
                ("action", "TEXT"),
                ("existing_company", "TEXT"),
                ("reason", "TEXT"),
                ("matched_skills", "TEXT"),
                ("missing_skills", "TEXT"),
                ("date_added", "TEXT"),
                ("last_seen", "TEXT"),
                ("notes", "TEXT"),
                ("recruiter", "TEXT"),
                ("hiring_manager", "TEXT"),
                ("fingerprint", "TEXT"),
                ("previous_job_id", "TEXT"),
            ])
            _ensure_columns(cursor, "job_workflow", [
                ("review_status", "TEXT"),
                ("action", "TEXT"),
                ("disposition", "TEXT"),
                ("updated_at", "TEXT"),
                ("updated_by", "TEXT"),
                ("notes", "TEXT"),
                ("follow_up_date", "TEXT"),
                ("last_contact_date", "TEXT"),
                ("status_source", "TEXT"),
            ])
            conn.commit()
            _upsert_all_jobs()
            conn.commit()
            return True
    except Exception as e:
        if conn:
            conn.rollback()
        console.print(f"[red]Failed to save to SQLite database: {e}[/red]")
        return False
    finally:
        if conn:
            conn.close()

def load_tracker(tracker_path):
    """Load existing jobs from tracker to prevent duplicates."""
    existing_jobs = {}
    if os.path.exists(tracker_path):
        with open(tracker_path, mode='r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                job_id = row.get("Job ID")
                if not job_id:
                    comp = row.get("Company", "").strip().lower()
                    pos = row.get("Position", "").strip().lower()
                    loc = row.get("Location", "").strip().lower()
                    job_id = hashlib.md5(f"{comp}|{pos}|{loc}".encode('utf-8')).hexdigest()
                existing_jobs[(job_id, row.get("Date Added", ""))] = row
    return existing_jobs


def load_config():
    """Load config file to retrieve last used folder and job type criteria."""
    config = {}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except Exception as e:
            console.print(f"[yellow]Failed to read {CONFIG_PATH}, falling back to defaults: {e}[/yellow]")
            
    # Default job type criteria if not present
    if "job_type_criteria" not in config:
        config["job_type_criteria"] = {
            "Software Engineer": {
                "tech_keywords": [".net", "c#", "java", "spring", "react", "graphql", "docker", "kubernetes", "aws", "azure", "postgresql", "sql server", "cube.js", "kafka", "rabbitmq", "redis", "ssis", "etl", "wcf"],
                "legacy_keywords": ["modernization", "legacy", "migration", "porting", "upgrade", "conversion", "evolution"],
                "skip_keywords": ["\\bAI\\s+Trainer\\b", "\\bAI\\s+Tutor\\b", "\\bData\\s+Quality\\s+Specialist\\b", "\\bAnnotation\\b", "\\bSearch\\s+Evaluator\\b", "\\bAI\\s+Content\\b", "\\bAI\\s+Writer\\b", "\\bAI\\s+Editor\\b", "\\bAI\\s+Quality\\b", "\\bprompt\\b", "\\bhuman\\s+in\\s+the\\s+loop\\b", "\\bAI\\s+Trainer\\b", "\\bAI\\s+Tutor\\b", "\\bAI\\s+Data\\b", "\\bAI\\s+Feedback\\b", "\\bAI\\s+Reviewer\\b", "\\bAI\\s+Evaluator\\b"],
                "priority_keywords": ["\\.net", "c#", "java", "spring", "react", "graphql"],
                "resume_skills": ["java", "c#", ".net", "python", "spring boot", "spring", "asp.net core", "react", "next.js", "graphql", "rest", "microservices", "docker", "kubernetes", "aws", "azure", "postgresql", "sql server", "sql", "power bi", "cube.js", "kafka", "rabbitmq", "redis", "clean architecture", "git", "linux", "ssis", "etl", "wcf"]
            },
            "Operations": {
                "tech_keywords": ["operations", "manufacturing", "inventory", "logistics", "supply chain", "repair", "quality assurance", "production", "warehouse", "procurement", "maintenance", "billing", "reconciliation", "compliance", "coordination", "safety"],
                "legacy_keywords": ["modernization", "improvement", "optimization", "standards", "efficiency", "streamlining"],
                "skip_keywords": ["\\bAI\\s+Trainer\\b", "\\bAI\\s+Tutor\\b", "\\bData\\s+Quality\\s+Specialist\\b", "\\bAnnotation\\b", "\\bSearch\\s+Evaluator\\b", "\\bAI\\s+Content\\b", "\\bAI\\s+Writer\\b", "\\bAI\\s+Editor\\b", "\\bAI\\s+Quality\\b", "\\bprompt\\b", "\\bhuman\\s+in\\s+the\\s+loop\\b", "\\bAI\\s+Trainer\\b", "\\bAI\\s+Tutor\\b", "\\bAI\\s+Data\\b", "\\bAI\\s+Feedback\\b", "\\bAI\\s+Reviewer\\b", "\\bAI\\s+Evaluator\\b"],
                "priority_keywords": ["operations", "manager", "supervisor", "director", "coordinator", "lead"],
                "resume_skills": ["manufacturing", "inventory", "logistics", "repair", "reporting", "business automation", "documentation", "workflow automation", "rma", "inventory management", "reconciliation", "compliance", "coordination"]
            }
        }
        # Save config back to disk
        try:
            with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4)
        except Exception as e:
            console.print(f"[yellow]Failed to write default config to {CONFIG_PATH}: {e}[/yellow]")

    # Apply skill aliases
    if "skill_aliases" in config:
        global POTENTIAL_SKILLS, SKILL_DISPLAY_NAMES
        for canon_skill, aliases in config["skill_aliases"].items():
            canon_display = SKILL_DISPLAY_NAMES.get(canon_skill, canon_skill.title())
            if canon_skill not in POTENTIAL_SKILLS:
                POTENTIAL_SKILLS.append(canon_skill)
            SKILL_DISPLAY_NAMES[canon_skill] = canon_display
            for alias in aliases:
                if alias not in POTENTIAL_SKILLS:
                    POTENTIAL_SKILLS.append(alias)
                SKILL_DISPLAY_NAMES[alias] = canon_display

    return config

def save_config(pdf_dir):
    """Save the selected folder to the config file."""
    try:
        config = load_config()
        config["last_pdf_dir"] = pdf_dir
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        console.print(f"[yellow]Failed to save config: {e}[/yellow]")

def select_pdf_directory():
    """Prompt the user for a PDF folder via GUI dialog or console input."""
    config = load_config()
    default_dir = config.get("last_pdf_dir", "")
    
    # Try GUI directory selection
    selected_dir = ""
    tkinter_success = False
    try:
        import tkinter as tk
        from tkinter import filedialog
        
        root = tk.Tk()
        root.withdraw()  # Hide main window
        root.attributes("-topmost", True)  # Bring dialog to front
        root.update()
        
        initial = default_dir if default_dir and os.path.exists(default_dir) else os.getcwd()
        console.print("[cyan]Opening folder selection dialog...[/cyan]")
        selected_dir = filedialog.askdirectory(title="Select Folder containing PDFs", initialdir=initial)
        root.destroy()
        tkinter_success = True
    except (Exception, KeyboardInterrupt):
        # Tkinter might fail, hang, or be interrupted
        pass
        
    if tkinter_success and not selected_dir:
        console.print("[yellow]Folder selection cancelled. Exiting.[/yellow]")
        sys.exit(0)
        
    # Fallback/validation console prompt
    if not selected_dir:
        if default_dir:
            selected_dir = default_dir
        else:
            selected_dir = input("Enter PDF directory path: ").strip()
            
    if selected_dir:
        selected_dir = os.path.abspath(selected_dir)
        save_config(selected_dir)
        
    return selected_dir

def extract_job_urls_from_page(page):
    """Extract all job-related URI links from page annotations, sorted from top to bottom."""
    urls_with_y = []
    if page.annotations:
        for annot in page.annotations:
            try:
                obj = annot.get_object()
                if not obj:
                    continue
                rect = obj.get('/Rect')
                if not rect:
                    continue
                
                uri = ""
                if '/A' in obj:
                    action = obj['/A'].get_object()
                    if '/URI' in action:
                        uri = action['/URI']
                
                if uri:
                    uri_lower = uri.lower()
                    # Filter out non-job links
                    ignore_patterns = [
                        "privacy", "terms", "unsubscribe", "help", "google.com/maps", 
                        "facebook.com", "twitter.com", "instagram.com", "linkedin.com/company",
                        "support", "cookie", "preferences", "optout", "feedback", "about"
                    ]
                    if any(pat in uri_lower for pat in ignore_patterns):
                        continue
                    
                    y_coord = rect[1]  # y_bottom coordinate of annotation bounding box
                    urls_with_y.append((uri, y_coord))
            except Exception:
                # Malformed/unsupported annotation objects are common and not
                # actionable; skip just this one rather than failing extraction
                # for the whole page. Intentionally silent -- logging here would
                # spam once per malformed annotation across every PDF processed.
                continue
                
    # Sort by Y-coordinate in descending order (top of page to bottom)
    urls_with_y.sort(key=lambda x: x[1], reverse=True)
    
    # Deduplicate consecutive identical URLs
    deduped_urls = []
    for uri, y in urls_with_y:
        if not deduped_urls or deduped_urls[-1] != uri:
            deduped_urls.append(uri)
            
    return deduped_urls

def detect_provider(text, filename=""):
    """Detect job board provider from PDF content or filename."""
    full_text = (text + " " + filename).lower()
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
    return "Unknown/Other"

def extract_pdf_text(pdf_path):
    """Extract embedded text from PDF. Fallback to OCR if empty."""
    text = ""
    try:
        reader = pypdf.PdfReader(pdf_path)
        for page in reader.pages:
            t = page.extract_text(extraction_mode='layout')
            if t:
                text += t + "\n"
    except Exception as e:
        console.print(f"[yellow]Failed to read PDF text normally: {e}[/yellow]")
    
    # Rule fallback to OCR if no selectable text
    if not text.strip():
        console.print(f"[yellow]No selectable text in {os.path.basename(pdf_path)}. Falling back to OCR...[/yellow]")
        text = perform_ocr(pdf_path)
        
    return text

def perform_ocr(pdf_path):
    """OCR fallback using easyocr if available."""
    try:
        import easyocr
        console.print("[yellow]OCR is requested, but scanning multi-page PDF images requires converting them. Returning empty for now.[/yellow]")
        return ""
    except ImportError:
        console.print("[red]easyocr is not fully configured or missing dependencies for OCR.[/red]")
        return ""

def _looks_like_title(line):
    line_lower = line.strip().lower()
    # Skip email subject-like lines, search alerts, or meta-text
    if line_lower.endswith(" jobs") or line_lower.endswith(" job"):
        return False
    if "similar to" in line_lower or "jobs similar" in line_lower:
        return False
    if "jobs at" in line_lower or "jobs in" in line_lower:
        return False
    return any(kw in line_lower for kw in TITLE_KEYWORDS)

def _skill_boundary_pattern(skill):
    """Build a word-boundary regex for `skill`, requiring a non-alnum
    boundary only on sides where the skill itself starts/ends with an alnum
    character. Skills like ".net" start with punctuation, which is already
    a natural boundary -- requiring the char before that punctuation to
    also be non-alnum would reject legitimate matches like "ASP.NET" or
    "VB.NET"."""
    if not skill:
        return r'(?!)'  # never matches
    lookbehind = r'(?<![a-z0-9])' if skill[0].isalnum() else ''
    lookahead = r'(?![a-z0-9])' if skill[-1].isalnum() else ''
    return lookbehind + re.escape(skill) + lookahead

def _find_skills(text):
    text_lower = text.lower()
    return [skill for skill in POTENTIAL_SKILLS if re.search(_skill_boundary_pattern(skill), text_lower)]

def _title_preferred_skills(title, context):
    title_skills = _find_skills(title)
    if title_skills:
        return title_skills
    return _find_skills(context)

def _format_skill_lists(found_skills, resume_skills):
    matched_list = [s for s in found_skills if s in resume_skills]
    missing_list = [s for s in found_skills if s not in resume_skills]
    matched_skills = ", ".join([SKILL_DISPLAY_NAMES[s] for s in matched_list])
    missing_skills = ", ".join([SKILL_DISPLAY_NAMES[s] for s in missing_list])
    return matched_skills, missing_skills

def normalize_ocr_spacing(text):
    if not text:
        return ""
    # Specific common corrections
    text = re.sub(r'(?i)\bfourey\s+es\b', 'Foureyes', text)
    text = re.sub(r'(?i)\bof\s+fice\b', 'office', text)
    text = re.sub(r'(?i)\bfirs\s+t\b', 'first', text)
    text = re.sub(r'(?i)\blak\s+e\b', 'lake', text)
    text = re.sub(r'(?i)\bseen\s+firs\s+t\b', 'seen first', text)
    text = re.sub(r'(?i)\bpac\s+k\s+yak\b', 'pack yak', text)
    text = re.sub(r'(?i)\binsurance\s+of\s+fice\b', 'Insurance Office', text)
    
    # General heuristics:
    # 1. End of word separated by space: "firs t" -> "first" (length >=2 followed by consonant, excluding C# and C++)
    text = re.sub(r'\b([a-zA-Z]{2,})\s+([bcdfghjklmnpqrstvwxyzBCDFGHJKLMNPQRSTVWXYZ])\b(?![#+])', r'\1\2', text)
    # 2. Start of word separated by space: "p hoto" -> "photo" (consonant followed by length >=2)
    text = re.sub(r'\b([bcdfghjklmnpqrstvwxyzBCDFGHJKLMNPQRSTVWXYZ])\s+([a-zA-Z]{2,})\b', r'\1\2', text)
    
    return text

def _clean_location(location):
    location = re.sub(r'[,\sâ€¢•]+$', '', location).strip()
    location = re.sub(r'\s+', ' ', location).strip()
    location = re.sub(r'\s*,\s*', ', ', location).strip()
    location = location.strip(', ')

    location = re.split(UI_LABEL_PATTERN, location, maxsplit=1)[0].strip()
    location = re.split(r'(?i)1-Click Apply|Quick Apply|Apply Now', location, maxsplit=1)[0].strip()
    if _looks_like_title(location):
        return ""
    return location.strip(', ')

def parse_job_cards_from_text(text, provider="Unknown/Other", source_pdf="Unknown"):
    """
    Parse potential job cards from extracted text.
    Keying off patterns like:
    [Title]
    [Company]
    [Location]
    """
    # Preprocess text to normalize OCR spacing artifacts (Extract -> Normalize)
    text = normalize_ocr_spacing(text)
    
    if provider == "jobs.utah.gov":
        jobs = []
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        for line in lines:
            match = re.search(r'^(.+)\s+\{([^}]+)\}\s*$', line)
            if match:
                title = match.group(1).strip()
                location_raw = match.group(2).strip()
                location = re.sub(r'\s+', ' ', location_raw)
                location = re.sub(r'(?i)sal\s*t\s*lake\s*city', 'Salt Lake City', location)
                location = re.sub(r'(?i)south\s*jordan', 'South Jordan', location)
                location = re.sub(r'(?i)west\s*valley\s*city', 'West Valley City', location)
                location = re.sub(r'(?i)salt\s*lake(?!\s*city)', 'Salt Lake City', location)
                title = re.sub(r'\s+', ' ', title)
                jobs.append({
                    "title": title,
                    "company": "Jobs.utah.gov-DailySummary",
                    "location": location,
                    "provider": "jobs.utah.gov",
                    "source_pdf": source_pdf,
                    "url": "https://jobs.utah.gov",
                    "raw_context": line
                })
        return jobs

    if provider == "BHE":
        jobs = []
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        start_collecting = False
        for line in lines:
            if "we have new jobs that might interest you" in line.lower():
                start_collecting = True
                continue
            if "you can also view all the jobs available" in line.lower() or "you can also view all the jobs" in line.lower():
                start_collecting = False
                break
            if start_collecting:
                title = re.sub(r'\s+', ' ', line).strip()
                if title:
                    jobs.append({
                        "title": title,
                        "company": "BHE",
                        "location": "Unknown",
                        "provider": "BHE",
                        "source_pdf": source_pdf,
                        "url": "N/A",
                        "raw_context": line
                    })
        return jobs

    if provider == "Ladders":
        jobs = []
        
        # Try Format C: Remote Jobs for You (pipe-delimited single-line format)
        if "remote jobs for" in text.lower():
            c_text = re.sub(r'[ \t]+', ' ', text)
            c_text = re.sub(r'(\$\d+K\s*-)\n\s*(\$?\d+K.*)', r'\1 \2', c_text)
            c_text = re.sub(r'\|\n\s*(\$?\d+K.*)', r'| \1', c_text)
            c_lines = [line.strip() for line in c_text.split('\n') if line.strip()]
            
            start_collecting = False
            for line in c_lines:
                if "remote jobs for you:" in line.lower():
                    start_collecting = True
                    continue
                if "do these jobs match what you're looking for" in line.lower() or "find more jobs" in line.lower():
                    start_collecting = False
                    break
                if start_collecting and "|" in line:
                    parts = [p.strip() for p in line.split("|") if p.strip()]
                    if len(parts) >= 2:
                        salary_raw = ""
                        if re.search(r'\$\d+K', parts[-1]):
                            salary_raw = parts[-1]
                            parts = parts[:-1]
                            
                        if len(parts) == 1:
                            title = parts[0]
                            company = "Unknown"
                            location = "Remote"
                        elif len(parts) == 2:
                            title = parts[0]
                            company = parts[1]
                            location = "Remote"
                        else:
                            title = parts[0]
                            company = parts[-1]
                            location = re.sub(r'\s+', ' ', " ".join(parts[1:-1])).strip()
                            location = re.sub(r'(?i)v\s*i\s*r\s*t\s*u\s*a\s*l\s*/\s*travel', 'Remote', location)
                            location = re.sub(r'(?i)v\s*irtual\s*/\s*travel', 'Remote', location)
                            if not location:
                                location = "Remote"
                                
                        title = re.sub(r'\s+', ' ', title)
                        company = re.sub(r'\s+', ' ', company)
                        
                        jobs.append({
                            "title": title,
                            "company": company,
                            "location": location,
                            "provider": "Ladders",
                            "source_pdf": source_pdf,
                            "url": "https://www.theladders.com",
                            "raw_context": f"{line} | Company: {company} | Location: {location} | Estimated Salary: {salary_raw}"
                        })
            if jobs:
                return jobs
                
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        # Try multiline layout formats first
        i = 0
        while i < len(lines):
            line = lines[i]
            
            # Format A: Title and Salary on one line, Company | Location on next line
            # e.g., "Applied Scientist             $165K - $206K*"
            match_a1 = re.search(r'^(.+?)\s{2,}(\$\d+K\s*-\s*\$\d+K.*)$', line)
            if match_a1:
                title = match_a1.group(1).strip()
                salary_raw = match_a1.group(2).strip()
                if i + 1 < len(lines):
                    next_line = lines[i+1]
                    match_a2 = re.search(r'^(.+?)\s*\|\s*(.+)$', next_line)
                    if match_a2:
                        company = match_a2.group(1).strip()
                        location_raw = match_a2.group(2).strip()
                        
                        location = re.sub(r'\s+', ' ', location_raw)
                        location = re.sub(r'(?i)v\s*i\s*r\s*t\s*u\s*a\s*l\s*/\s*travel', 'Remote', location)
                        location = re.sub(r'(?i)v\s*irtual\s*/\s*travel', 'Remote', location)
                        location = re.sub(r'(?i)salt\s*lake\s*city\s*,\s*ut', 'Salt Lake City, UT', location)
                        location = re.sub(r'(?i)draper\s*,\s*ut', 'Draper, UT', location)
                        location = re.sub(r'\s*,\s*$', '', location)
                        
                        title = re.sub(r'\s+', ' ', title)
                        company = re.sub(r'\s+', ' ', company)
                        
                        jobs.append({
                            "title": title,
                            "company": company,
                            "location": location,
                            "provider": "Ladders",
                            "source_pdf": source_pdf,
                            "url": "https://www.theladders.com",
                            "raw_context": f"{line} | Company: {company} | Location: {location} | Estimated Salary: {salary_raw}"
                        })
                        i += 2
                        continue
                        
            # Format B: Salary | Company | Location on one line, Title on preceding lines
            # e.g., "$180K - $210K* | Teladoc | Remote"
            match_b = re.search(r'^(\$\d+K\s*-\s*\$\d+K.*)\s*\|\s*(.+?)\s*\|\s*(.+)$', line)
            if match_b:
                salary_raw = match_b.group(1).strip()
                company = match_b.group(2).strip()
                loc_start = match_b.group(3).strip()
                
                # Find location continuation by looking forward until "Apply Now"
                loc_parts = [loc_start]
                k = i + 1
                while k < len(lines):
                    next_line = lines[k]
                    if "apply now" in next_line.lower():
                        break
                    if "|" in next_line or "jobs posted" in next_line.lower():
                        break
                    loc_parts.append(next_line)
                    k += 1
                location = " ".join(loc_parts).strip()
                location = re.sub(r'\s+', ' ', location)
                location = re.sub(r'(?i)v\s*i\s*r\s*t\s*u\s*a\s*l\s*/\s*travel', 'Remote', location)
                location = re.sub(r'(?i)v\s*irtual\s*/\s*travel', 'Remote', location)
                location = re.sub(r'(?i)salt\s*lake\s*city\s*,\s*ut', 'Salt Lake City, UT', location)
                location = re.sub(r'(?i)draper\s*,\s*ut', 'Draper, UT', location)
                location = re.sub(r'\s*,\s*$', '', location)
                
                # Find title by looking backward
                title_parts = []
                j = i - 1
                while j >= 0:
                    prev_line = lines[j]
                    if "apply now" in prev_line.lower() or "jobs posted" in prev_line.lower() or "hot remote" in prev_line.lower() or "hot companies" in prev_line.lower() or "|" in prev_line:
                        break
                    if "http" in prev_line or "gmail -" in prev_line.lower() or "1 message" in prev_line or re.search(r'\b\d+/\d+\b', prev_line):
                        j -= 1
                        continue
                    title_parts.insert(0, prev_line)
                    j -= 1
                title = " ".join(title_parts).strip()
                title = re.sub(r'\s+', ' ', title)
                company = re.sub(r'\s+', ' ', company)
                
                if title:
                    jobs.append({
                        "title": title,
                        "company": company,
                        "location": location,
                        "provider": "Ladders",
                        "source_pdf": source_pdf,
                        "url": "https://www.theladders.com",
                        "raw_context": f"{line} | Company: {company} | Location: {location} | Estimated Salary: {salary_raw}"
                    })
                    # We consumed the location lines, so fast-forward i to k
                    i = k
                    continue
                    
            i += 1
            
        # If no jobs found with layout parser, fallback to single-line format
        if not jobs:
            for line in lines:
                match = re.search(r'^(.+?)\s*/\s*(.+?)\s*/\s*(\$\d+K.*)$', line)
                if match:
                    title = match.group(1).strip()
                    location_raw = match.group(2).strip()
                    salary_raw = match.group(3).strip()
                    location = re.sub(r'\s+', ' ', location_raw)
                    location = re.sub(r'(?i)v\s*i\s*r\s*t\s*u\s*a\s*l\s*/\s*travel', 'Remote', location)
                    location = re.sub(r'(?i)salt\s*lake\s*city\s*,\s*ut', 'Salt Lake City, UT', location)
                    location = re.sub(r'(?i)draper\s*,\s*ut', 'Draper, UT', location)
                    location = re.sub(r'\s*,\s*$', '', location)
                    title = re.sub(r'\s+', ' ', title)
                    jobs.append({
                        "title": title,
                        "company": "Ladders-DailyDigest",
                        "location": location,
                        "provider": "Ladders",
                        "source_pdf": source_pdf,
                        "url": "https://www.theladders.com",
                        "raw_context": f"{line} | Estimated Salary: {salary_raw}"
                    })
        return jobs

    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    # Rule 2: Ignore specific heading blocks
    ignore_headings = [
        "jobs based on your preferences",
        "recommended jobs",
        "new jobs",
        "similar jobs",
        "featured jobs",
        "search results",
        "job alert"
    ]
    
    filtered_lines = []
    for line in lines:
        if any(heading in line.lower() for heading in ignore_headings):
            continue
        filtered_lines.append(line)
        
    jobs = []
    state_city_pattern = re.compile(r'\b(UT|Utah|Remote|United States|US|Hybrid|On-site|Salt Lake City)\b', re.IGNORECASE)
    
    i = 0
    while i < len(filtered_lines):
        line = filtered_lines[i]
        
        # Look for a line that looks like a Job Title
        is_title = _looks_like_title(line)
        
        if is_title:
            title = line
            company = "Unknown/Other"
            location = ""
            url = ""
            found_location = False
            
            # Check the next line to see if it's the company or actually a location/another job listing
            has_next = i + 1 < len(filtered_lines)
            if has_next:
                next_line = filtered_lines[i+1]
                # Is the next line actually another title?
                next_is_title = _looks_like_title(next_line)
                next_has_salary = bool(re.search(r'\$\d+K', next_line)) or "/ virtual" in next_line.lower() or "/ travel" in next_line.lower()
                
                # Check if the next line looks like a location instead of a company
                is_next_location = not next_is_title and (bool(state_city_pattern.search(next_line)) or "remote" in next_line.lower() or bool(re.search(r'\b(UT|CA|VA|TX|NY|FL|CO|WA|IL|MA|GA|MI|OH|PA|NJ|Utah|California|Virginia|Coast)\b', next_line)))
                
                # Check if the line after next (i+2) contains '·' and matches location/remote,
                # which indicates that next_line (i+1) is actually a continuation of the title,
                # and next_line+1 (i+2) is the Company · Location line.
                is_line_after_next_company_location = False
                if i + 2 < len(filtered_lines) and not next_is_title:
                    line_after_next = filtered_lines[i+2]
                    if "·" in line_after_next and (bool(state_city_pattern.search(line_after_next)) or "remote" in line_after_next.lower()):
                        is_line_after_next_company_location = True
                
                is_next_company_location = False
                if "·" in next_line and (bool(state_city_pattern.search(next_line)) or "remote" in next_line.lower()):
                    is_next_company_location = True

                if is_line_after_next_company_location:
                    title = f"{title} {next_line}"
                    line_after_next = filtered_lines[i+2]
                    parts = [p.strip() for p in line_after_next.split("·", 1)]
                    company = parts[0]
                    if len(parts) > 1:
                        location = _clean_location(parts[1])
                        found_location = True
                    next_idx = i + 3
                elif is_next_company_location:
                    parts = [p.strip() for p in next_line.split("·", 1)]
                    company = parts[0]
                    if len(parts) > 1:
                        location = _clean_location(parts[1])
                        found_location = True
                    next_idx = i + 2
                elif next_is_title or next_has_salary:
                    # The next line is another job title! Don't consume it as company.
                    company = "Unknown/Other"
                    next_idx = i + 1
                elif is_next_location:
                    # The next line is actually the location, so the company is likely the line before the title!
                    location = _clean_location(next_line)
                    found_location = True
                    if i > 0:
                        potential_company = filtered_lines[i-1]
                        potential_company = re.split(r'\s+·\s+|\s+\d\.\d', potential_company)[0].strip()
                        potential_company = re.sub(r'[,\s•]+$', '', potential_company).strip()
                        
                        # Fix for email metadata leaking into company name
                        if "years exp required" in potential_company.lower() and i > 1:
                            potential_company = filtered_lines[i-2]
                            potential_company = re.split(r'\s+·\s+|\s+\d\.\d', potential_company)[0].strip()
                            potential_company = re.sub(r'[,\s•]+$', '', potential_company).strip()
                            
                        if is_valid_company(potential_company):
                            company = potential_company
                        else:
                            company = "Unknown/Other"
                    else:
                        company = "Unknown/Other"
                    next_idx = i + 2
                else:
                    # It's a company name!
                    company = next_line
                    next_idx = i + 2
            else:
                next_idx = i + 1
                
            # Look ahead for location and URL
            while next_idx < min(i + 6, len(filtered_lines)):
                next_line = filtered_lines[next_idx]
                # If we hit another title, stop looking ahead
                is_next_title = _looks_like_title(next_line)
                next_has_salary = bool(re.search(r'\$\d+K', next_line)) or "/ virtual" in next_line.lower() or "/ travel" in next_line.lower()
                if is_next_title or next_has_salary:
                    break
                if state_city_pattern.search(next_line) or "remote" in next_line.lower():
                    if not found_location:
                        location = _clean_location(next_line)
                        found_location = True
                    elif "on-site" in next_line.lower() or "remote" in next_line.lower() or "hybrid" in next_line.lower():
                        location = f"{location} {next_line.strip()}"
                if "http" in next_line or "www." in next_line or next_line.startswith("linkedin.com"):
                    url = next_line
                next_idx += 1
            
            # Clean up company name ending characters
            company = re.split(r'\s+·\s+|\s+\d\.\d', company)[0].strip()
            
            if not found_location and i + 2 < next_idx and i + 2 < len(filtered_lines):
                # Only fallback if i+2 was not already processed/skipped
                potential_loc = filtered_lines[i+2]
                if not _looks_like_title(potential_loc):
                    location = _clean_location(potential_loc)
                
            # Smart split for Company • Location separated by bullet
            if "•" in company:
                parts = company.split("•")
                company = parts[0].strip()
                loc_prefix = parts[1].strip()
                
                # Combine loc_prefix with parsed location
                if location:
                    if loc_prefix.lower() in location.lower():
                        pass
                    elif location.lower() in loc_prefix.lower():
                        location = loc_prefix
                    else:
                        sep = " "
                        location = f"{loc_prefix}{sep}{location}"
                else:
                    location = loc_prefix
            
            # Clean up trailing punctuation / bullets
            company = re.sub(r'[,\s•]+$', '', company).strip()
            # Strip UI labels that may have been concatenated onto the company name
            ui_label_pattern = rf'{UI_LABEL_PATTERN}$'
            company = re.sub(ui_label_pattern, '', company).strip()
            # Collapse multiple spaces to a single space
            company = re.sub(r'\s+', ' ', company).strip()
            location = _clean_location(location)
            
            # Clean up title anomalies (e.g., ZipRecruiter's trailing 'New' badge, or unmatched parens from wrapping)
            title = re.sub(r'\s+New$', '', title, flags=re.IGNORECASE).strip()
            if title.endswith(')') and '(' not in title:
                title = title[:-1].strip()
                
            jobs.append({
                "title": title,
                "company": clean_company_name(company),
                "location": location,
                "url": url,
                "provider": provider,
                "source_pdf": source_pdf,
                "raw_context": "\n".join(filtered_lines[max(0, i-2):min(len(filtered_lines), i+8)])
            })
            i = next_idx - 1
        i += 1
        
    return jobs

def classify_job_type(title, context):
    """Determine if a job is a Software Engineer or Operations role."""
    title_lower = title.lower()
    context_lower = context.lower()
    
    ops_indicators = ["operations", "manufacturing", "inventory", "logistics", "repair", "production", "warehouse", "procurement", "manager", "supervisor", "coordinator", "billing", "reconciliation"]
    swe_indicators = ["software", "developer", "engineer", "programmer", "architect", ".net", "java", "c#", "spring", "react"]
    
    # Check title first
    has_ops_title = any(w in title_lower for w in ops_indicators)
    has_swe_title = any(w in title_lower for w in swe_indicators)

    # Domain-specific ops keywords override the generic "engineer" keyword
    # e.g. "Manufacturing Engineer" or "Logistics Coordinator" → Operations
    specific_ops = ["manufacturing", "inventory", "logistics", "production", "warehouse", "procurement"]
    if any(w in title_lower for w in specific_ops) and not any(w in title_lower for w in ["software", "developer", "backend"]):
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

def evaluate_job(job):
    """
    Apply Job Review Rules v1.0 to decide if the job should be recommended.
    Returns: (should_recommend: bool, confidence: str, notes: str, fit_score: int, company_type: str, recommendation: str, reason: str, matched_skills: str, missing_skills: str, job_type: str)
    """
    title = job["title"]
    company = job["company"]
    location = job["location"]
    context = job["raw_context"].lower()
    
    # Classify Job Type first
    job_type = classify_job_type(title, context)
    
    # Load config and criteria dynamically based on job type
    config = load_config()
    criteria_map = config.get("job_type_criteria", {})
    criteria = criteria_map.get(job_type, criteria_map.get("Software Engineer", {}))
    
    tech_keywords = criteria.get("tech_keywords", [])
    legacy_keywords = criteria.get("legacy_keywords", [])
    skip_keywords = criteria.get("skip_keywords", [])
    priority_keywords = criteria.get("priority_keywords", [])
    resume_skills = criteria.get("resume_skills", [])
    
    # Reject the entire card if either company or title contains obvious email metadata/UI fragments
    for field_val in [title, company]:
        val_lower = field_val.lower()
        if "gmail -" in val_lower or "apply now" in val_lower or "more jobs" in val_lower or "be seen first" in val_lower or "do not share this email" in val_lower:
            return False, "🔴 Low", "Contains email metadata or UI instructions", 0, "P4", "Small / Medium", "★☆☆☆☆ Skip", "Metadata/UI leak", "", "", job_type
        if re.search(r'\b\d{1,2}:\d{2}\s*(AM|PM|am|pm)?\b', field_val):
            return False, "🔴 Low", "Contains timestamp (likely email metadata)", 0, "P4", "Small / Medium", "★☆☆☆☆ Skip", "Metadata/UI leak", "", "", job_type

    # Rule 3 & 4: Must have company and title
    if not title or not company:
        return False, "🔴 Low", "Rule 4: Missing company or title", 0, "P4", "Small / Medium", "★☆☆☆☆ Skip", "Missing details", "", "", job_type
        
    if not is_valid_company(company, job.get("provider")):
        return False, "🔴 Low", "Failed company name validation rules", 0, "P4", "Small / Medium", "★☆☆☆☆ Skip", "Failed criteria", "", "", job_type
        
    comp_lower = company.strip().lower()
        
    # Reject conversational text fragments from email templates
    conversational_phrases = [
        "could be", "with your", "your background", "your experience", 
        "is hiring", "apply now", "feel free", "hiring for", "interested in", 
        "you're interested", "you would be", "contribute to", "opportunities you", 
        "great fit", "little different", "looking for", "would be a", 
        "could contribute", "background as a", "expertise with", "offers remote",
        "flexibility of", "competitive pay"
    ]
    title_lower = title.lower()
    loc_lower = location.lower()
    if any(phrase in comp_lower or phrase in title_lower or phrase in loc_lower for phrase in conversational_phrases):
        return False, "🔴 Low", "Excluding conversational email text fragment", 0, "P4", "Small / Medium", "★☆☆☆☆ Skip", "Text fragment", "", "", job_type
        
    # Rule 6: Relocation check (Utah or Remote only)
    is_utah = any(re.search(r"\b" + kw + r"\b", location.lower()) for kw in ["ut", "utah", "salt lake", "slc", "lehi", "provo", "ogden"])
    is_remote = "remote" in location.lower() or "remote" in title.lower()
    if not (is_utah or is_remote):
        return False, "🔴 Low", f"Rule 6: Relocation required (Location: {location})", 0, "P4", "Small / Medium", "★☆☆☆☆ Skip", "Out of state", "", "", job_type
        
    # Rule 7: Hard bachelor's degree requirement
    degree_required = re.search(r"bachelor'?s?\s+degree\s+required", context) or re.search(r"\bbs\b.*\brequired\b", context)
    degree_preferred = re.search(r"bachelor'?s?\s+degree\s+preferred", context) or re.search(r"\bbs\b.*\bpreferred\b", context)
    if degree_required and not degree_preferred:
        return False, "🔴 Low", "Rule 7: Hard bachelor's degree requirement detected", 0, "P4", "Small / Medium", "★☆☆☆☆ Skip", "Degree requirement", "", "", job_type
        
    # Rule 8: Skip list unless compelling reason
    compelling_reason = any(tech.lower() in context for tech in tech_keywords)
    for pattern in skip_keywords:
        if re.search(pattern, title, re.IGNORECASE):
            if not compelling_reason:
                return False, "🔴 Low", f"Rule 8: Excluded role type ({pattern})", 0, "P4", "Small / Medium", "★☆☆☆☆ Skip", "Excluded role", "", "", job_type
                
    # Check technology fits (Rule 10). If the title declares a specific stack,
    # prefer it over nearby posting text that may belong to another card.
    title_skill_names = _find_skills(title)
    tech_search = title.lower() if title_skill_names else f"{title} {context}".lower()
    matched_techs = [tech for tech in tech_keywords if re.search(_skill_boundary_pattern(tech.lower()), tech_search)]
    notes = []
    if job.get("source_index"):
        notes.append(f"Source Index: {job.get('source_index')}")
        
    if matched_techs:
        notes.append(f"Tech matches: {', '.join(matched_techs)}")
        
    # Check legacy modernization fits (Rule 11)
    matched_legacy = [legacy for legacy in legacy_keywords if legacy.lower() in context]
    if matched_legacy:
        notes.append(f"Legacy modernization: {', '.join(matched_legacy)}")
        
    # Rule 12: Smaller-to-mid-sized preference
    is_faang = any(faang.lower() in company.lower() for faang in FAANG_COMPANIES)
    if is_faang:
        notes.append("FAANG scale (lower preference)")
    else:
        notes.append("Small-to-mid-sized (preferred)")
        
    # Determine confidence level
    is_priority = any(re.search(pat, title, re.IGNORECASE) for pat in priority_keywords)
    has_valid_url = job.get("url") and job.get("url") != "N/A" and job.get("url").startswith("http")
    
    if job.get("provider") in ["jobs.utah.gov", "Ladders"]:
        confidence = "40%"
    else:
        # Check if PDF text fallback or empty (OCR)
        if not context.strip() or len(context) < 50:
            confidence = "20%"
        elif company and company != "Unknown" and not ("dailysummary" in company.lower() or "dailydigest" in company.lower()) and has_valid_url:
            confidence = "100%"
        elif company and company != "Unknown" and not ("dailysummary" in company.lower() or "dailydigest" in company.lower()):
            confidence = "90%"
        else:
            confidence = "70%"
            
    # Check for local candidate/onsite restrictions
    restriction_phrases = ["local candidate", "onsite only", "on-site only", "must relocate", "no remote"]
    has_restriction = any(p in title.lower() or p in context for p in restriction_phrases)
    if has_restriction:
        notes.append("Local/Onsite restriction detected")
        
    if job.get("provider") in ["jobs.utah.gov", "Ladders"]:
        notes.append("Employer not included in daily summary PDF")
        
    notes_str = "; ".join(notes)
    
    # Company type classification
    company_type = "Small / Medium"
    comp_lower = company.lower()
    c_search = f"{company} {context}".lower()
    if any(k in comp_lower for k in ["recruiting", "staffing", "placement", "navigators", "personnel", "robert half", "binit", "headhunters", "recruiter", "search partners"]):
        company_type = "Recruiting Firm"
    elif any(k in c_search for k in ["consulting", "solutions", "services", "cgi", "pwc"]):
        company_type = "Consulting"
    elif any(k in c_search for k in ["defense", "leidos", "harris", "lockheed", "raytheon", "boeing", "northrop", "military"]):
        company_type = "Defense"
    elif any(k in c_search for k in ["health", "medical", "hosp", "care", "pharm", "optum", "clinical", "dental"]):
        company_type = "Healthcare"
    elif any(k in c_search for k in ["finance", "wealth", "bank", "capital", "valuations", "investment", "insurance", "insurtech", "credit", "fidelity"]):
        company_type = "Financial"
    elif any(faang.lower() in company.lower() for faang in FAANG_COMPANIES):
        company_type = "Enterprise"

    # Normalized Fit Score calculation
    score_remote_utah = 20 if (is_utah or is_remote) else 0

    title_lower = title.lower()
    experienced_terms = [
        "senior", "lead", "principal", "staff", "architect", "engineering manager", "sme",
        "mid", " ii", " iii", " 2", " 3", "level ii", "level iii"
    ]
    role_terms = [
        "software engineer", "backend engineer", "full stack", "developer", "sde", "swe"
    ]

    score_experience = 15 if any(w in title_lower for w in experienced_terms) else 0
    score_role = 10 if any(w in title_lower for w in role_terms) else 0
    
    # Role-specific backend/fullstack indicator
    if job_type == "Software Engineer":
        score_backend_fs = 15 if any(w in title.lower() or w in context for w in ["backend", "full stack", "fullstack", "full-stack", "distributed", "data"]) else 0
        explicit_title_stack = bool(title_skill_names)
        stack_search = title.lower() if explicit_title_stack else f"{title} {context}".lower()
        has_dotnet = any(w in stack_search for w in [".net", "c#"])
        has_java = any(w in stack_search for w in ["java", "spring"])
        if has_dotnet:
            score_dotnet_java = 20
        elif has_java:
            score_dotnet_java = 10  # Priority adjustment: 10 points for Java-only Software Engineer roles
        else:
            score_dotnet_java = 0
    else:
        # For Operations: points for supervisor/director/manager leadership or automation experience
        score_backend_fs = 15 if any(w in title.lower() or w in context for w in ["director", "supervisor", "manager", "lead"]) else 0
        score_dotnet_java = 20 if any(w in title.lower() or w in context for w in ["manufacturing", "logistics", "inventory", "supply chain"]) else 0
        
    score_no_degree = 10 if not degree_required else 0
    score_small_med = 10 if company_type == "Small / Medium" else 0
    score_legacy = 10 if bool(matched_legacy) else 0
    
    fit_score = score_remote_utah + score_experience + score_role + score_backend_fs + score_dotnet_java + score_no_degree + score_small_med + score_legacy
    if has_restriction:
        fit_score = max(0, fit_score - 30)
    
    # Operations type penalty: deduct 15 pts when primary focus is Software Engineering
    # This prevents Operations Manager roles from ranking alongside senior engineering roles
    if job_type == "Operations":
        fit_score = max(0, fit_score - 15)
        
    # Incomplete listing penalty
    is_incomplete_listing = job.get("provider") in ["jobs.utah.gov", "Ladders"] or "dailysummary" in company.lower() or "dailydigest" in company.lower()
    if is_incomplete_listing:
        fit_score = max(0, fit_score - 30)
        
    # Recommendation calculation (normalized)
    try:
        conf_num = int(str(confidence).replace("%", "").strip())
    except ValueError:
        conf_num = 0

    if conf_num <= 20:
        recommendation = "★☆☆☆☆ Skip"
    else:
        if fit_score >= 80 and conf_num >= 90:
            recommendation = "★★★★★ Apply Now"
        elif fit_score >= 60:
            recommendation = "★★★★☆ Strong"
        elif fit_score >= 40:
            recommendation = "★★★☆☆ Maybe"
        elif fit_score >= 20:
            recommendation = "★★☆☆☆ Low"
        else:
            recommendation = "★☆☆☆☆ Skip"
            
    # Cap incomplete listings at P3 (Maybe)
    if is_incomplete_listing and recommendation in ["★★★★★ Apply Now", "★★★★☆ Strong"]:
        recommendation = "★★★☆☆ Maybe"
            
    # Reason calculation
    reasons = []
    if job_type == "Operations":
        reasons.append("Operations role (-15 pts)")
    if is_remote:
        reasons.append("Remote")
    elif is_utah:
        reasons.append("Utah")
        
    if has_restriction:
        reasons.append("Onsite/Local Restriction")

        
    matched_skills_list = []
    search_str = tech_search
    if job_type == "Software Engineer":
        if any(w in search_str for w in [".net", "c#"]): matched_skills_list.append(".NET")
        if "java" in search_str: matched_skills_list.append("Java")
        if "spring" in search_str: matched_skills_list.append("Spring")
    else:
        if "manufacturing" in search_str: matched_skills_list.append("Manufacturing")
        if "logistics" in search_str: matched_skills_list.append("Logistics")
        if "inventory" in search_str: matched_skills_list.append("Inventory")
        
    if matched_skills_list:
        reasons.append(" + ".join(matched_skills_list))
        
    if company_type == "Small / Medium":
        reasons.append("Small company")
    elif company_type == "Recruiting Firm":
        reasons.append("Recruiter")
    else:
        reasons.append(company_type)
        
    if degree_required:
        reasons.append("Degree requirement detected")
    elif is_faang:
        reasons.append("Enterprise scale")
        
    reason = " + ".join(reasons)
    
    found_skills = _title_preferred_skills(title, context)
    if job_type == "Operations":
        found_skills = [s for s in found_skills if s in resume_skills or s in tech_keywords]
    matched_skills, missing_skills = _format_skill_lists(found_skills, resume_skills)
            
    # Rule 16: Low confidence jobs are never recommended
    should_recommend = conf_num >= 40
    
    # Map temporary action for priority calculation
    if company_type == "Recruiting Firm" and recommendation in ["★★★★★ Apply Now", "★★★★☆ Strong"]:
        temp_action = "Contact Recruiter"
    elif recommendation in ["★★★★★ Apply Now", "★★★★☆ Strong"]:
        temp_action = "Apply"
    elif recommendation == "★★★☆☆ Maybe":
        temp_action = "Review"
    else:
        temp_action = "Ignore"
    priority = compute_priority(recommendation, temp_action)
    
    return should_recommend, confidence, notes_str, fit_score, priority, company_type, recommendation, reason, matched_skills, missing_skills, job_type

def _print_dashboard(tracker_path="master_tracker.csv"):
    """Print a daily action dashboard from the master tracker CSV."""
    if not os.path.exists(tracker_path):
        console.print(f"[red]Tracker not found: {tracker_path}[/red]")
        return
    
    with open(tracker_path, encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    
    today = date.today()

    def fmt_row(r):
        age = r.get("Age (days)", "")
        age_str = f"  [dim](+{age}d)[/dim]" if str(age).isdigit() and int(age) > 0 else ""
        return f"  • [bold]{r['Company']}[/bold] — {r.get('Position','')[:55]}{age_str}"

    p1 = [r for r in rows if r.get("Tracker Status") == "New" and r.get("Priority","").startswith("P1")]
    p2 = [r for r in rows if r.get("Tracker Status") == "New" and r.get("Priority","").startswith("P2")]
    active = [r for r in rows if r.get("Tracker Status") in ["Phone Screen", "Technical Interview", "Recruiter Submitted", "Waiting"]]
    follow_up = [r for r in rows if r.get("Tracker Status") == "Waiting"]
    recent_rejected = [r for r in rows if r.get("Tracker Status") in ["Rejected", "Ghosted"]]

    date_str = today.strftime('%A, %B %d, %Y').replace(' 0', ' ')
    console.print(f"\n[bold green]=========================================[/bold green]")
    console.print(f"[bold green]   TODAY'S WORK — {date_str}[/bold green]")
    console.print(f"[bold green]=========================================[/bold green]\n")

    console.print(f"[bold cyan]Apply Today ({len(p1)})[/bold cyan]")
    if p1:
        for r in p1: console.print(fmt_row(r))
    else:
        console.print("  [dim]None[/dim]")

    console.print(f"\n[bold cyan]Apply This Week ({len(p2)})[/bold cyan]")
    if p2:
        for r in p2[:10]: console.print(fmt_row(r))
        if len(p2) > 10:
            console.print(f"  [dim]... and {len(p2)-10} more[/dim]")
    else:
        console.print("  [dim]None[/dim]")

    console.print(f"\n[bold green]Active Pipeline ({len(active)})[/bold green]")
    if active:
        for r in active:
            console.print(f"  • [bold]{r['Company']}[/bold] — {r.get('Tracker Status','')} [{r.get('Position','')[:40]}]")
    else:
        console.print("  [dim]None[/dim]")

    if follow_up:
        console.print(f"\n[bold yellow]Follow Up ({len(follow_up)})[/bold yellow]")
        for r in follow_up:
            console.print(fmt_row(r))

    if recent_rejected:
        console.print(f"\n[bold red]Recently Rejected / Ghosted ({len(recent_rejected)})[/bold red]")
        for r in recent_rejected[:5]:
            console.print(fmt_row(r))

    console.print(f"\n[bold green]=========================================[/bold green]\n")


def print_today_queue(tracker_path="master_tracker.csv"):
    if not os.path.exists(tracker_path):
        console.print(f"[red]Tracker not found: {tracker_path}[/red]")
        return
    with open(tracker_path, encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    
    # Queue is P1 + P2 jobs with Tracker Status == "New"
    queue = [r for r in rows if r.get("Tracker Status") == "New" and (r.get("Priority","").startswith("P1") or r.get("Priority","").startswith("P2"))]
    
    console.print("\n[bold green]=========================================[/bold green]")
    console.print("[bold green]            TODAY'S QUEUE                [/bold green]")
    console.print("[bold green]=========================================[/bold green]\n")
    
    if queue:
        for r in queue:
            console.print(f"  □ [bold]{r['Company']}[/bold] — {r.get('Position','')[:50]}")
        console.print(f"\n[bold yellow]{len(queue)} jobs remaining[/bold yellow]")
    else:
        console.print("  🎉 No jobs remaining in today's queue!")
    console.print("\n[bold green]=========================================[/bold green]\n")


def print_analytics(tracker_path="master_tracker.csv", db_path="jobs.db"):
    """Print an analytics dashboard with pipeline conversion funnel, source comparison, weekly metrics, and score correlation."""
    if not os.path.exists(db_path):
        console.print(f"[red]Database not found: {db_path}. Please run sync first to build the database.[/red]")
        return
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'")
        if not cursor.fetchone():
            console.print("[red]Jobs table not found in database. Please run sync first.[/red]")
            return
            
        cursor.execute("""
            SELECT j.*, w.updated_at, w.notes as w_notes 
            FROM jobs j 
            LEFT JOIN job_workflow w ON j.job_id = w.job_id
        """)
        rows = [dict(r) for r in cursor.fetchall()]
    except Exception as e:
        console.print(f"[red]Error reading database: {e}[/red]")
        return
    finally:
        conn.close()
        
    if not rows:
        console.print("[yellow]No jobs found to analyze.[/yellow]")
        return

    # Helper function to check if a job was applied to
    def is_applied(r):
        return r.get("tracker_status") in [
            "Applied", "Phone Screen", "Technical Interview", "Recruiter Submitted", 
            "Waiting", "Rejected", "Ghosted", "Offer", "Accepted"
        ]

    # Helper function to check if a job was interviewed
    def is_interviewed(r):
        status = r.get("tracker_status")
        notes = (r.get("notes") or "").lower() + " " + (r.get("w_notes") or "").lower()
        if status in ["Phone Screen", "Technical Interview", "Offer", "Accepted"]:
            return True
        return any(kw in notes for kw in ["screen", "phone screen", "interview", "technical screen", "technical interview"])

    # Helper function to check if a job was offered
    def is_offered(r):
        status = r.get("tracker_status")
        notes = (r.get("notes") or "").lower() + " " + (r.get("w_notes") or "").lower()
        if status in ["Offer", "Accepted"]:
            return True
        return "offer" in notes

    # Helper function to parse dates
    def parse_date(date_str):
        if not date_str:
            return None
        date_str = date_str.strip()
        if len(date_str) >= 10:
            try:
                return date.fromisoformat(date_str[:10])
            except ValueError:
                pass
        return None

    # Helper to draw a horizontal progress bar
    def make_bar(percentage, width=15):
        filled = int(round(percentage / 100 * width))
        return "█" * filled + "░" * (width - filled)

    # Helper to get calendar week
    def get_iso_week_str(d):
        if not d:
            return None
        iso = d.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"

    # Output Title
    console.print("\n[bold magenta]=========================================[/bold magenta]")
    console.print("[bold magenta]          JOB PIPELINE ANALYTICS         [/bold magenta]")
    console.print("[bold magenta]=========================================[/bold magenta]\n")

    # --- SECTION 1: CRM PIPELINE FUNNEL ---
    tracked_cnt = len(rows)
    eligible_cnt = sum(1 for r in rows if (r.get("fit_score") or 0) >= 40)
    applied_cnt = sum(1 for r in rows if is_applied(r))
    screen_cnt = sum(1 for r in rows if is_interviewed(r))
    tech_cnt = sum(1 for r in rows if r.get("tracker_status") in ["Technical Interview", "Offer", "Accepted"] or any(kw in ((r.get("notes") or "") + " " + (r.get("w_notes") or "")).lower() for kw in ["technical", "coding", "hackerrank", "assessment"]))
    offer_cnt = sum(1 for r in rows if is_offered(r))
    accepted_cnt = sum(1 for r in rows if r.get("tracker_status") == "Accepted")

    funnel_data = [
        ("Tracked (Total)", tracked_cnt),
        ("Eligible (Score >= 40)", eligible_cnt),
        ("Applied", applied_cnt),
        ("Screening (Phone/Recruiter)", screen_cnt),
        ("Technical Interview", tech_cnt),
        ("Offer Received", offer_cnt),
        ("Offer Accepted", accepted_cnt)
    ]

    funnel_table = Table(title="1. CRM Conversion Funnel", title_style="bold cyan", show_header=True)
    funnel_table.add_column("Pipeline Stage", style="bold cyan")
    funnel_table.add_column("Count", justify="right", style="green")
    funnel_table.add_column("Conv. (Tracked)", justify="right", style="yellow")
    funnel_table.add_column("Conv. (Prev)", justify="right", style="yellow")
    funnel_table.add_column("Visual Funnel", style="magenta")

    prev_count = tracked_cnt
    for stage_name, count in funnel_data:
        conv_tracked = (count / tracked_cnt * 100) if tracked_cnt > 0 else 0.0
        conv_prev = (count / prev_count * 100) if prev_count > 0 else 0.0
        bar = make_bar(conv_tracked)
        funnel_table.add_row(
            stage_name,
            str(count),
            f"{conv_tracked:.1f}%",
            f"{conv_prev:.1f}%" if stage_name != "Tracked (Total)" else "-",
            bar
        )
        prev_count = count

    console.print(funnel_table)
    eligible_app_rate = (applied_cnt / eligible_cnt * 100) if eligible_cnt > 0 else 0.0
    console.print(f"Eligible Application Rate (Applied / Eligible): [bold green]{eligible_app_rate:.1f}%[/bold green]")
    console.print()

    # --- SECTION 2: BEST SOURCES BY CONVERSION ---
    providers = {}
    for r in rows:
        prov = r.get("provider") or "Unknown"
        prov_lower = prov.lower()
        if "indeed" in prov_lower:
            prov = "Indeed"
        elif "linkedin" in prov_lower:
            prov = "LinkedIn"
        elif "glassdoor" in prov_lower:
            prov = "Glassdoor"
        elif "ziprecruiter" in prov_lower:
            prov = "ZipRecruiter"
        elif "utah" in prov_lower:
            prov = "Jobs.utah.gov"
        elif "ladders" in prov_lower:
            prov = "Ladders"
        else:
            prov = prov.strip() or "Unknown"
        
        if prov not in providers:
            providers[prov] = []
        providers[prov].append(r)

    source_table = Table(title="2. Performance by Job Source / Provider", title_style="bold cyan")
    source_table.add_column("Source Board", style="bold cyan")
    source_table.add_column("Tracked", justify="right", style="white")
    source_table.add_column("Applied (%)", justify="right", style="green")
    source_table.add_column("Interview (%)", justify="right", style="yellow")
    source_table.add_column("Offers", justify="right", style="bold green")

    # Sort sources by tracked count descending
    sorted_sources = sorted(providers.items(), key=lambda x: len(x[1]), reverse=True)
    for source, s_rows in sorted_sources:
        s_tracked = len(s_rows)
        s_applied = sum(1 for r in s_rows if is_applied(r))
        s_interviewed = sum(1 for r in s_rows if is_interviewed(r))
        s_offered = sum(1 for r in s_rows if is_offered(r))
        
        app_pct = (s_applied / s_tracked * 100) if s_tracked > 0 else 0.0
        int_pct = (s_interviewed / s_applied * 100) if s_applied > 0 else 0.0
        
        source_table.add_row(
            source,
            str(s_tracked),
            f"{s_applied} ({app_pct:.1f}%)",
            f"{s_interviewed} ({int_pct:.1f}%)" if s_applied > 0 else "0 (0.0%)",
            str(s_offered)
        )

    console.print(source_table)
    console.print()

    # --- SECTION 3: APPLICATIONS BY WEEK ---
    weekly_stats = {}
    for r in rows:
        disc_date = parse_date(r.get("date_added"))
        app_date = parse_date(r.get("updated_at")) if is_applied(r) else None
        
        disc_week = get_iso_week_str(disc_date)
        app_week = get_iso_week_str(app_date)
        
        if disc_week:
            if disc_week not in weekly_stats:
                weekly_stats[disc_week] = {"discovered": 0, "applied": 0}
            weekly_stats[disc_week]["discovered"] += 1
            
        if app_week:
            if app_week not in weekly_stats:
                weekly_stats[app_week] = {"discovered": 0, "applied": 0}
            weekly_stats[app_week]["applied"] += 1

    weekly_table = Table(title="3. Weekly Volume & Consistency", title_style="bold cyan")
    weekly_table.add_column("Calendar Week (ISO)", style="bold cyan")
    weekly_table.add_column("Jobs Discovered", justify="right", style="white")
    weekly_table.add_column("Applications Sent", justify="right", style="green")

    # Sort weeks chronologically and show up to last 12 weeks
    sorted_weeks = sorted(weekly_stats.keys())[-12:]
    for wk in sorted_weeks:
        w_data = weekly_stats[wk]
        weekly_table.add_row(
            wk,
            str(w_data["discovered"]),
            str(w_data["applied"])
        )

    console.print(weekly_table)
    console.print()

    # --- SECTION 4: LATENCY AND AVERAGE DURATION ---
    latencies = []
    for r in rows:
        if is_applied(r):
            disc_date = parse_date(r.get("date_added"))
            app_date = parse_date(r.get("updated_at"))
            if disc_date and app_date:
                days = (app_date - disc_date).days
                latencies.append(max(0, days))

    from rich.panel import Panel
    if latencies:
        avg_lat = sum(latencies) / len(latencies)
        sorted_lat = sorted(latencies)
        median_lat = sorted_lat[len(sorted_lat) // 2]
        min_lat = sorted_lat[0]
        max_lat = sorted_lat[-1]
        
        latency_content = (
            f"Average latency from discovery to application:  [bold green]{avg_lat:.1f} days[/bold green]\n"
            f"Median latency:                                  [bold green]{median_lat} days[/bold green]\n"
            f"Minimum latency:                                 [bold green]{min_lat} days[/bold green] (same-day action)\n"
            f"Maximum latency:                                 [bold green]{max_lat} days[/bold green]"
        )
    else:
        latency_content = "[yellow]No status change date history found to calculate application latency.[/yellow]"
        
    console.print(Panel(latency_content, title="4. Discovery-to-Application Latency", title_align="left", border_style="cyan"))
    console.print()

    # --- SECTION 5: SCORE CORRELATION ---
    score_bins = [
        ("Excellent (90-100)", lambda s: 90 <= s <= 100),
        ("High (70-89)", lambda s: 70 <= s <= 89),
        ("Medium (50-69)", lambda s: 50 <= s <= 69),
        ("Low (30-49)", lambda s: 30 <= s <= 49),
        ("Ignore (< 30)", lambda s: s < 30)
    ]

    score_table = Table(title="5. Fit Score Correlation with Funnel Progression", title_style="bold cyan")
    score_table.add_column("Fit Score Range", style="bold cyan")
    score_table.add_column("Tracked", justify="right", style="white")
    score_table.add_column("Applied (%)", justify="right", style="green")
    score_table.add_column("Interview (%)", justify="right", style="yellow")
    score_table.add_column("Offers", justify="right", style="bold green")

    for range_name, bin_fn in score_bins:
        bin_rows = [r for r in rows if bin_fn(r.get("fit_score") or 0)]
        b_tracked = len(bin_rows)
        b_applied = sum(1 for r in bin_rows if is_applied(r))
        b_interviewed = sum(1 for r in bin_rows if is_interviewed(r))
        b_offered = sum(1 for r in bin_rows if is_offered(r))
        
        app_pct = (b_applied / b_tracked * 100) if b_tracked > 0 else 0.0
        int_pct = (b_interviewed / b_applied * 100) if b_applied > 0 else 0.0
        
        score_table.add_row(
            range_name,
            str(b_tracked),
            f"{b_applied} ({app_pct:.1f}%)" if b_tracked > 0 else "0 (0.0%)",
            f"{b_interviewed} ({int_pct:.1f}%)" if b_applied > 0 else "0 (0.0%)",
            str(b_offered)
        )

    console.print(score_table)
    console.print("\n[bold magenta]=========================================[/bold magenta]\n")


def handle_interactive_update():
    db_path = "jobs.db"
    if not os.path.exists(db_path):
        console.print("[red]jobs.db not found. Cannot perform database update.[/red]")
        return False
        
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()

        # Query database for jobs that are 'New' and have priority P1/P2, or are active in pipeline
        cursor.execute("""
            SELECT job_id, company, position, tracker_status, priority
            FROM jobs
            WHERE tracker_status IN ('New', 'Phone Screen', 'Technical Interview', 'Recruiter Submitted', 'Waiting')
            ORDER BY
                CASE tracker_status
                    WHEN 'Phone Screen' THEN 1
                    WHEN 'Technical Interview' THEN 2
                    WHEN 'Recruiter Submitted' THEN 3
                    WHEN 'Waiting' THEN 4
                    ELSE 5
                END,
                priority ASC,
                company ASC
        """)
        jobs = cursor.fetchall()
    finally:
        conn.close()
    
    if not jobs:
        console.print("[yellow]No active queue or pipeline jobs found to update.[/yellow]")
        return False
        
    console.print("\n[bold cyan]Today's Active Jobs[/bold cyan]\n")
    for idx, job in enumerate(jobs, 1):
        jid, company, position, status, priority = job
        status_info = f"[{status}]" if status != "New" else f"[{priority.split('–')[0].strip()}]"
        console.print(f"  {idx}) [bold]{company}[/bold] — {position[:50]} {status_info}")
        
    try:
        choice = input("\nSelect job (number) or Ctrl+C to cancel: ").strip()
        if not choice:
            return False
        choice_idx = int(choice) - 1
        if choice_idx < 0 or choice_idx >= len(jobs):
            console.print("[red]Invalid selection.[/red]")
            return False
    except (ValueError, KeyboardInterrupt):
        console.print("\n[yellow]Operation cancelled.[/yellow]")
        return False
        
    selected_job = jobs[choice_idx]
    job_id = selected_job[0]
    company = selected_job[1]
    position = selected_job[2]
    
    # New status selection
    valid_statuses = VALID_STATUSES
    console.print(f"\nSelected: [bold]{company}[/bold] — {position}")
    console.print(f"Current Status: [yellow]{selected_job[3]}[/yellow]")
    console.print("\n[bold cyan]New Status:[/bold cyan]")
    for idx, stat in enumerate(valid_statuses, 1):
        console.print(f"  {idx}) {stat}")
        
    try:
        status_choice = input("\nSelect new status (number) or Ctrl+C to cancel: ").strip()
        if not status_choice:
            return False
        status_idx = int(status_choice) - 1
        if status_idx < 0 or status_idx >= len(valid_statuses):
            console.print("[red]Invalid selection.[/red]")
            return False
    except (ValueError, KeyboardInterrupt):
        console.print("\n[yellow]Operation cancelled.[/yellow]")
        return False
        
    status = valid_statuses[status_idx]
    
    try:
        notes = input("\nAdd optional note/disposition (or press Enter to skip): ").strip()
        if not notes:
            notes = None
    except KeyboardInterrupt:
        console.print("\n[yellow]Operation cancelled.[/yellow]")
        return False
        
    return handle_status_update(job_id, status, notes)


def handle_status_update(query, status, notes=None):
    # Validates status
    valid_statuses = VALID_STATUSES
    if status not in valid_statuses:
        console.print(f"[red]Invalid status '{status}'. Valid statuses: {', '.join(valid_statuses)}[/red]")
        return False
        
    db_path = "jobs.db"
    tracker_path = "master_tracker.csv"
    
    if not os.path.exists(db_path):
        console.print("[red]jobs.db not found. Cannot perform database update.[/red]")
        return False
        
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    # A human is issuing this update -- make sure status_source exists before
    # the writes below stamp it, in case this DB predates that column.
    _ensure_columns(cursor, "job_workflow", [("status_source", "TEXT")])

    # Query database for matches
    cursor.execute("""
        SELECT job_id, company, position, location, tracker_status
        FROM jobs
        WHERE job_id = ? OR company LIKE ? OR position LIKE ?
    """, (query, f"%{query}%", f"%{query}%"))
    matches = cursor.fetchall()
    
    if not matches:
        console.print(f"[red]No jobs found matching '{query}'.[/red]")
        conn.close()
        return False
        
    if len(matches) > 1:
        console.print(f"[yellow]Multiple matches found for '{query}':[/yellow]")
        for m in matches:
            console.print(f"  • [bold]{m[0]}[/bold]: {m[1]} - {m[2]} ({m[3]}) [Current Status: {m[4]}]")
        console.print("[yellow]Please specify a more precise company name or the exact Job ID.[/yellow]")
        conn.close()
        return False
        
    # Single match found
    job_id, company, position, location, current_status = matches[0]
    
    # Determine derived fields
    review_status = "Imported"
    if status in ["Applied", "Phone Screen", "Technical Interview", "Recruiter Submitted", "Waiting", "Offer", "Accepted"]:
        review_status = "Applied"
    elif status in ["Rejected", "Cancelled", "Ghosted", "Expired"]:
        review_status = "Closed"
        
    action = "Apply"
    if status in ["Applied", "Waiting", "Phone Screen", "Technical Interview", "Recruiter Submitted", "Offer", "Accepted"]:
        action = "Already Applied"
    elif status in ["Rejected", "Cancelled", "Ghosted", "Expired"]:
        action = "Ignore"
        
    disposition_map = {
        "New": "Apply",
        "Applied": "Waiting",
        "Phone Screen": "Active",
        "Technical Interview": "Active",
        "Recruiter Submitted": "Active",
        "Waiting": "Active",
        "Rejected": "Closed",
        "Cancelled": "Closed",
        "Ghosted": "Closed",
        "Expired": "Closed",
        "Offer": "Active",
        "Accepted": "Closed"
    }
    disposition = disposition_map.get(status, "Apply")
    
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Update SQLite database
    cursor.execute("""
        UPDATE jobs 
        SET tracker_status = ?, review_status = ?, action = ?, disposition = ? 
        WHERE job_id = ?
    """, (status, review_status, action, disposition, job_id))
    
    cursor.execute("SELECT 1 FROM job_workflow WHERE job_id = ?", (job_id,))
    if cursor.fetchone():
        cursor.execute("""
            UPDATE job_workflow
            SET tracker_status = ?, review_status = ?, action = ?, disposition = ?,
                notes = COALESCE(?, notes), updated_at = ?, updated_by = 'system', status_source = 'user'
            WHERE job_id = ?
        """, (status, review_status, action, disposition, notes, now_str, job_id))
    else:
        cursor.execute("""
            INSERT INTO job_workflow (job_id, tracker_status, review_status, action, disposition, notes, updated_at, updated_by, status_source)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'system', 'user')
        """, (job_id, status, review_status, action, disposition, notes, now_str))
        
    # Retrieve updated row for CSV synchronization
    cursor.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,))
    db_row = cursor.fetchone()
    
    # Map DB row keys to CSV headers
    db_to_csv_mapping = {
        "job_id": "Job ID",
        "review_status": "Review Status",
        "job_type": "Job Type",
        "company": "Company",
        "position": "Position",
        "location": "Location",
        "url": "URL",
        "provider": "Provider",
        "source_pdf": "Source PDF",
        "confidence": "Confidence",
        "fit_score": "Fit Score",
        "priority": "Priority",
        "company_type": "Company Type",
        "recommendation": "Recommendation",
        "tracker_status": "Tracker Status",
        "disposition": "Disposition",
        "action": "Action",
        "existing_company": "Existing Company",
        "reason": "Reason",
        "matched_skills": "Matched Skills",
        "missing_skills": "Missing Skills",
        "date_added": "Date Added",
        "notes": "Notes",
        "recruiter": "Recruiter",
        "hiring_manager": "Hiring Manager"
    }
    
    csv_row = {}
    if db_row:
        # Get column names from cursor description
        columns = [col[0] for col in cursor.description]
        db_dict = dict(zip(columns, db_row))
        for db_k, csv_k in db_to_csv_mapping.items():
            csv_row[csv_k] = db_dict.get(db_k, "")
            
        # Compute Age (days)
        today = date.today()
        date_added_str = csv_row.get("Date Added", "")
        try:
            added = date.fromisoformat(date_added_str)
            csv_row["Age (days)"] = (today - added).days
        except (ValueError, TypeError):
            csv_row["Age (days)"] = ""
            
    conn.commit()
    conn.close()
    
    # Update master_tracker.csv
    if os.path.exists(tracker_path) and csv_row:
        rows = []
        updated = False
        with open(tracker_path, mode='r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            for row in reader:
                if row["Job ID"] == job_id:
                    row["Tracker Status"] = status
                    row["Review Status"] = review_status
                    row["Action"] = action
                    row["Disposition"] = disposition
                    if notes:
                        row["Notes"] = notes
                    updated = True
                rows.append(row)
                
        if not updated:
            rows.append(csv_row)
            
        # Sort rows: Fit Score desc, Recommendation desc, Company asc
        rows.sort(key=lambda x: (
            -int(x.get("Fit Score", 0) if x.get("Fit Score") else 0),
            x.get("Recommendation", ""),
            x.get("Company", "").lower()
        ))
        
        write_tracker_csv_atomic(tracker_path, fieldnames, rows, extrasaction='ignore')

    console.print("\n[bold green]✓ Updated[/bold green]\n")
    console.print(f"  [bold]Company:[/bold]       {company}")
    console.print(f"  [bold]Position:[/bold]      {position}")
    console.print("")
    console.print(f"  [bold]Tracker Status:[/bold] [cyan]{status}[/cyan]")
    console.print(f"  [bold]Review Status:[/bold]  {review_status}")
    console.print(f"  [bold]Action:[/bold]         {action}")
    console.print(f"  [bold]Disposition:[/bold]    {disposition}")
    if notes:
        console.print(f"  [bold]Notes/Disp:[/bold]     {notes}")
    console.print("")
    return True


def handle_manual_add(company=None, position=None, location=None, job_type=None, provider=None, recruiter=None, hiring_manager=None, url=None, fit_score=None, recommendation=None, status=None, notes=None, interactive=None):
    if interactive is None:
        interactive = not (company and position)

    console.print("\n[bold green]=== Add Manual Opportunity ===[/bold green]\n")
    
    # Prompt for fields
    if not company:
        if interactive:
            while not company:
                company = input("Company: ").strip()
                if not company:
                    console.print("[red]Company name is required.[/red]")
        else:
            console.print("[red]Company name is required in non-interactive mode.[/red]")
            return False
    else:
        company = company.strip()
            
    if not position:
        if interactive:
            while not position:
                position = input("Position: ").strip()
                if not position:
                    console.print("[red]Position is required.[/red]")
        else:
            console.print("[red]Position is required in non-interactive mode.[/red]")
            return False
    else:
        position = position.strip()
            
    if location is None:
        if interactive:
            location = input("Location [default: Remote]: ").strip()
        else:
            location = "Remote"
    if not location:
        location = "Remote"
    else:
        location = location.strip()
        
    if job_type is None:
        if interactive:
            job_type = input("Job Type (1: Software Engineer, 2: Operations) [default: 1]: ").strip()
        else:
            job_type = "Software Engineer"
    if job_type == "2" or str(job_type).lower() == "operations":
        job_type = "Operations"
    else:
        job_type = "Software Engineer"
        
    if provider is None:
        if interactive:
            provider = input("Source Type / Provider (e.g. PDF Import, Recruiter, Company Website, Referral, Manual) [default: Manual]: ").strip()
        else:
            provider = "Manual"
    if not provider:
        provider = "Manual"
    else:
        provider = provider.strip()
        
    if recruiter is None:
        if interactive:
            recruiter = input("Recruiter [optional]: ").strip()
        else:
            recruiter = ""
    else:
        recruiter = recruiter.strip()
        
    if hiring_manager is None:
        if interactive:
            hiring_manager = input("Hiring Manager [optional]: ").strip()
        else:
            hiring_manager = ""
    else:
        hiring_manager = hiring_manager.strip()
        
    if url is None:
        if interactive:
            url = input("URL [optional]: ").strip()
        else:
            url = ""
    else:
        url = url.strip()
    
    if fit_score is None:
        if interactive:
            fit_score_str = input("Fit Score (1-100) [default: 70]: ").strip()
            try:
                fit_score = int(fit_score_str)
            except ValueError:
                fit_score = 70
        else:
            fit_score = 70
    else:
        try:
            fit_score = int(fit_score)
        except ValueError:
            fit_score = 70
        
    if recommendation is None:
        if interactive:
            recommendation = input("Recommendation (e.g. ★★★★★ Apply Now, ★★★★☆ Strong, ★★★☆☆ Maybe) [default: ★★★★☆ Strong]: ").strip()
        else:
            recommendation = "★★★★☆ Strong"
    if not recommendation:
        recommendation = "★★★★☆ Strong"
    else:
        recommendation = recommendation.strip()
        
    if status is None:
        if interactive:
            applied_input = input("Applied? (y/n) [default: y]: ").strip().lower()
            if applied_input == "n":
                status = "New"
            else:
                # Prompt for status in the active statuses list
                valid_statuses = VALID_STATUSES
                console.print(f"Select status: {', '.join(valid_statuses)}")
                status_input = input(f"Status [default: Applied]: ").strip()
                if status_input in valid_statuses:
                    status = status_input
                else:
                    status = "Applied"
        else:
            status = "Applied"
    else:
        status = status.strip()
            
    if notes is None:
        if interactive:
            notes = input("Notes: ").strip()
        else:
            notes = ""
    else:
        notes = notes.strip()
    
    # Derived values
    review_status = "Imported"
    if status in ["Applied", "Phone Screen", "Technical Interview", "Recruiter Submitted", "Waiting", "Offer", "Accepted"]:
        review_status = "Applied"
    elif status in ["Rejected", "Cancelled", "Ghosted", "Expired"]:
        review_status = "Closed"
        
    action = "Apply"
    if status in ["Applied", "Waiting", "Phone Screen", "Technical Interview", "Recruiter Submitted", "Offer", "Accepted"]:
        action = "Already Applied"
    elif status in ["Rejected", "Cancelled", "Ghosted", "Expired"]:
        action = "Ignore"
        
    disposition_map = {
        "New": "Apply",
        "Applied": "Waiting",
        "Phone Screen": "Active",
        "Technical Interview": "Active",
        "Recruiter Submitted": "Active",
        "Waiting": "Active",
        "Rejected": "Closed",
        "Cancelled": "Closed",
        "Ghosted": "Closed",
        "Expired": "Closed",
        "Offer": "Active",
        "Accepted": "Closed"
    }
    disposition = disposition_map.get(status, "Apply")
    
    # Existing company check
    tracker_path = "master_tracker.csv"
    existing_companies = set()
    if os.path.exists(tracker_path):
        try:
            with open(tracker_path, mode='r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                existing_companies = {row.get("Company", "").strip().lower() for row in reader if row.get("Company")}
        except Exception as e:
            console.print(f"[dim yellow]Could not read {tracker_path} for existing-company check: {e}[/dim yellow]")
            
    known_tracker_companies = {"lvt", "decerto", "explorer software group", "infinity software development", "clearwaters.it", "new walton services", "american auto auction group", "co-diagnostics", "sunwest bank", "weave", "medallion bank"}
    comp_cleaned = company.strip().lower()
    if comp_cleaned in known_tracker_companies or comp_cleaned in existing_companies:
        already_in = "Yes"
    else:
        already_in = "No"
        
    # Generate job ID. If an existing tracker row already matches this
    # company/position/location, reuse its Job ID so re-running --add for the
    # same opportunity updates that row instead of creating a duplicate --
    # otherwise mint a fresh, permanent UUID, same as the PDF-import path.
    date_added = datetime.now().strftime("%Y-%m-%d")
    job_id = None
    target_fingerprint = canonical_job_key(company, position, location)
    if os.path.exists(tracker_path):
        try:
            with open(tracker_path, mode='r', newline='', encoding='utf-8') as f:
                for row in csv.DictReader(f):
                    row_fingerprint = canonical_job_key(row.get("Company", ""), row.get("Position", ""), row.get("Location", ""))
                    if row_fingerprint == target_fingerprint and row.get("Job ID"):
                        job_id = row["Job ID"]
                        break
        except Exception:
            pass
    if not job_id:
        job_id = uuid.uuid4().hex

    # Priority
    priority = compute_priority(recommendation, action)
    
    # Create the job dictionary
    job = {
        "Job ID": job_id,
        "Review Status": review_status,
        "Job Type": job_type,
        "Company": company,
        "Position": position,
        "Location": location,
        "URL": url if url else "N/A",
        "Provider": provider,
        "Source PDF": "Manual",
        "Confidence": "🟢 High",
        "Fit Score": fit_score,
        "Priority": priority,
        "Company Type": "Small / Medium",
        "Recommendation": recommendation,
        "Tracker Status": status,
        "Disposition": disposition,
        "Action": action,
        "Existing Company": already_in,
        "Age (days)": 0,
        "Reason": "Manual Opportunity",
        "Matched Skills": "",
        "Missing Skills": "",
        "Date Added": date_added,
        "Last Seen": date_added,
        "Notes": notes,
        "Recruiter": recruiter,
        "Hiring Manager": hiring_manager,
        "Fingerprint": canonical_job_key(company, position, location),
        "Previous Job ID": "",
        "Source Index": "",
        "_status_source": "user"
    }
    
    # Save/upsert to jobs.db
    success = save_to_sqlite("jobs.db", [job])
    if not success:
        console.print("[red]Database save failed, aborting CSV update to prevent data divergence.[/red]")
        return False
        
    # Append/update master_tracker.csv
    if os.path.exists(tracker_path):
        rows = []
        updated = False
        with open(tracker_path, mode='r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            for row in reader:
                if row["Job ID"] == job_id:
                    # Update row fields
                    row["Tracker Status"] = status
                    row["Review Status"] = review_status
                    row["Action"] = action
                    row["Disposition"] = disposition
                    row["Notes"] = notes
                    row["Recruiter"] = recruiter
                    row["Hiring Manager"] = hiring_manager
                    updated = True
                rows.append(row)
                
        if not updated:
            rows.append(job)
            
        # Sort rows: Fit Score desc, Recommendation desc, Company asc
        rows.sort(key=lambda x: (
            -int(x.get("Fit Score", 0) if x.get("Fit Score") else 0),
            x.get("Recommendation", ""),
            x.get("Company", "").lower()
        ))
        
        write_tracker_csv_atomic(tracker_path, fieldnames, rows, extrasaction='ignore')

    console.print(f"\n[bold green]✓ Manually added job '{position}' at '{company}' (ID: {job_id})[/bold green]\n")


def print_todays_highlights(new_jobs, combined_jobs, db_path="jobs.db"):
    """
    Print a 'Current Opportunity Highlights' briefing — top un-actioned opportunities from
    the full tracker, with new-this-run jobs called out separately.
    Always appears as the terminal's final section.
    """
    from rich.panel import Panel
    from rich.text import Text

    new_job_ids = {j.get("Job ID", "") for j in new_jobs}

    # Top un-actioned ★★★★☆+ jobs from the FULL tracker (not just this run)
    # Pattern ★★★★★ always surfaces here as long as it hasn't been acted on
    unactioned = [
        j for j in combined_jobs
        if j.get("Tracker Status") == "New"
        and ("★★★★★" in j.get("Recommendation", "") or "★★★★☆" in j.get("Recommendation", ""))
    ]
    unactioned.sort(key=lambda x: (-int(x.get("Fit Score", 0) or 0), x.get("Recommendation", "")))
    top_jobs = unactioned[:8]

    # --- Build insight data ---

    # Companies previously interviewed at
    prior_interview_companies = set()
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        rows = conn.execute("""
            SELECT LOWER(j.company)
            FROM jobs j
            JOIN job_workflow w ON j.job_id = w.job_id
            WHERE w.tracker_status IN ('Phone Screen', 'Technical Interview')
        """).fetchall()
        prior_interview_companies = {r[0] for r in rows}
    except Exception as e:
        console.print(f"[dim yellow]Could not load prior-interview companies from {db_path}: {e}[/dim yellow]")
    finally:
        if conn:
            conn.close()

    # Brand-new companies: in top_jobs AND new this run AND not in pre-run tracker
    existing_before_run = {
        r.get("Company", "").strip().lower()
        for r in combined_jobs
        if r.get("Job ID", "") not in new_job_ids
    }
    new_companies = [
        j for j in top_jobs
        if j.get("Job ID", "") in new_job_ids
        and j.get("Company", "").strip().lower() not in existing_before_run
    ]

    # Key skill matches among new-this-run jobs only
    HIGHLIGHT_SKILLS = [".net", "c#", "spring boot", "java", "react", "aws", "azure"]
    skill_hits = {}
    for j in new_jobs:
        matched = j.get("Matched Skills", "").lower()
        notes   = j.get("Notes", "").lower()
        company = j.get("Company", "")
        for skill in HIGHLIGHT_SKILLS:
            if skill in matched or skill in notes:
                skill_hits.setdefault(skill, []).append(company)

    # Previously-interviewed companies in new-this-run recs
    reunion_jobs = [
        j for j in new_jobs
        if j.get("Company", "").strip().lower() in prior_interview_companies
    ]

    # --- Render ---
    content = Text()

    if top_jobs:
        for idx, j in enumerate(top_jobs):
            if idx > 0:
                content.append("\n")
            is_new   = j.get("Job ID", "") in new_job_ids
            stars    = "★★★★★" if "★★★★★" in j.get("Recommendation", "") else "★★★★☆"
            company  = j.get("Company", "Unknown")
            position = j.get("Position", "")
            score    = j.get("Fit Score", "")
            location = j.get("Location", "")
            color    = "bold green" if "★★★★★" in stars else "green"
            tag      = " NEW" if is_new else ""
            
            line1 = Text()
            line1.append(stars, style=color)
            if is_new:
                line1.append(" NEW", style="bold cyan")
            line1.append(f"  {company}", style="bold")
            line1.append(f" — {position}\n")
            
            line2 = Text(f"         {location}  •  Fit: {score}", style="dim")
            
            content.append(line1)
            content.append(line2)
    else:
        content.append(Text("No ★★★★☆+ unactioned jobs in your queue", style="dim"))

    # Divider line
    content.append("\n" + "─" * 60 + "\n")

    insights = []
    total_new = len(new_jobs)
    insights.append(
        f"[cyan]{total_new}[/cyan] new job{'s' if total_new != 1 else ''} imported this run"
        if total_new else "[dim]No new jobs this run[/dim]"
    )
    if new_companies:
        names = ", ".join(j.get("Company", "") for j in new_companies[:3])
        extra = f" (+{len(new_companies)-3} more)" if len(new_companies) > 3 else ""
        insights.append(f"[cyan]{len(new_companies)}[/cyan] brand-new {'companies' if len(new_companies) != 1 else 'company'}: {names}{extra}")
    for skill, companies in skill_hits.items():
        display = skill.upper() if skill in (".net", "c#", "aws", "azure") else skill.title()
        insights.append(f"[cyan]{len(companies)}[/cyan] job{'s' if len(companies) != 1 else ''} matching {display}")
    if reunion_jobs:
        names = ", ".join(j.get("Company", "") for j in reunion_jobs[:2])
        insights.append(f"[cyan]{len(reunion_jobs)}[/cyan] from a company you've previously interviewed at: {names}")

    for idx, line in enumerate(insights):
        content.append(Text.from_markup(line))
        if idx < len(insights) - 1:
            content.append("\n")

    panel = Panel(
        content,
        title="[bold yellow]CURRENT OPPORTUNITY HIGHLIGHTS[/bold yellow]",
        border_style="bold yellow",
        expand=False,
        padding=(1, 2)
    )
    console.print()
    console.print(panel)



def handle_dedup_physical():
    """Find and combine physical duplicate rows in the tracker."""
    db_path = 'jobs.db'
    csv_path = 'master_tracker.csv'
    csv_out = 'master_tracker_temp.csv'
    
    if not os.path.exists(csv_path):
        console.print("[red]master_tracker.csv not found.[/red]")
        return
        
    with open(csv_path, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames

    groups = {}
    for i, row in enumerate(rows):
        key = (
            normalize_string(row.get('Company', '')),
            normalize_string(row.get('Position', '')),
            row.get('Date Added', ''),
            row.get('Source PDF', ''),
            row.get('Tracker Status', '')
        )
        if key not in groups:
            groups[key] = []
        groups[key].append(i)

    duplicates_found = 0
    to_delete_ids = []
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    for key, indices in groups.items():
        if len(indices) > 1:
            base_idx = indices[0]
            base_row = rows[base_idx]
            base_id = base_row['Job ID']
            
            for dup_idx in indices[1:]:
                dup_row = rows[dup_idx]
                dup_id = dup_row['Job ID']
                duplicates_found += 1
                to_delete_ids.append(dup_id)
                
                base_row['Source Index'] = merge_delimited_field(base_row.get('Source Index', ''), dup_row.get('Source Index', ''))
                
                notes1 = base_row.get('Notes', '').strip()
                notes2 = dup_row.get('Notes', '').strip()
                new_notes = notes1
                if notes2 and notes2 not in notes1:
                    new_notes = notes1 + "; " + notes2 if notes1 else notes2
                base_row['Notes'] = new_notes

            cursor.execute(
                "UPDATE jobs SET notes = ? WHERE job_id = ?",
                (base_row['Notes'], base_id)
            )

    if duplicates_found == 0:
        console.print("[green]No physical duplicates found.[/green]")
        conn.close()
        return

    for dup_id in to_delete_ids:
        cursor.execute("DELETE FROM job_workflow WHERE job_id = ?", (dup_id,))
        cursor.execute("DELETE FROM jobs WHERE job_id = ?", (dup_id,))
    
    conn.commit()
    conn.close()

    with open(csv_out, mode='w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        to_delete_set = set(to_delete_ids)
        for i, row in enumerate(rows):
            if row['Job ID'] not in to_delete_set:
                writer.writerow(row)
    
    shutil.move(csv_out, csv_path)
    console.print(f"[green]Deleted {duplicates_found} duplicate jobs. Kept and merged into base rows.[/green]")



def handle_rescore(db_path="jobs.db", csv_path="master_tracker.csv"):
    console.print("[cyan]Rescoring active jobs...[/cyan]")
    resolved_db = os.path.abspath(db_path)
    resolved_csv = os.path.abspath(csv_path)
    resolved_config = os.path.abspath(CONFIG_PATH)
    console.print(f"[dim]Database:  {resolved_db}[/dim]")
    console.print(f"[dim]Tracker:   {resolved_csv}[/dim]")
    console.print(f"[dim]Config:    {resolved_config}[/dim]")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    placeholders = ",".join(["?"] * len(TERMINAL_STATUSES))
    cursor.execute(f"SELECT * FROM jobs WHERE tracker_status NOT IN ({placeholders})", tuple(TERMINAL_STATUSES))
    jobs = cursor.fetchall()

    legacy_rows_approximated = 0
    rows_changed = 0
    # Field-level updates keyed by job_id, reused below to patch master_tracker.csv
    # in place -- without this, the CSV keeps stale pre-rescore values and a later
    # normal sync (which treats the CSV as the "existing" state) silently reverts
    # jobs.db back to those stale values on its next upsert.
    updated_fields_by_id = {}
    for row in jobs:
        job_dict = dict(row)
        job_dict['title'] = job_dict.get('position', '')
        if not job_dict.get('raw_context'):
            # Rows saved before raw_context was persisted have no original
            # posting text to re-evaluate against. Fall back to a synthesized
            # approximation from previously extracted fields, but this loses
            # signals that never made it into those fields (e.g. relocation
            # restrictions, degree requirements) and can under- or over-score
            # the job relative to its original evaluation.
            job_dict['raw_context'] = f"{job_dict.get('position', '')} {job_dict.get('company', '')} {job_dict.get('matched_skills', '')} {job_dict.get('missing_skills', '')} {job_dict.get('reason', '')} {job_dict.get('notes', '')}"
            legacy_rows_approximated += 1

        should_recommend, confidence, notes, fit_score, temp_priority, company_type, recommendation, reason, matched_skills, missing_skills, job_type = evaluate_job(job_dict)

        priority = compute_priority(recommendation, job_dict.get('action', ''), 0)

        if (fit_score, priority, company_type, recommendation, reason, matched_skills, missing_skills) != (
            job_dict.get('fit_score'), job_dict.get('priority'), job_dict.get('company_type'),
            job_dict.get('recommendation'), job_dict.get('reason'), job_dict.get('matched_skills'),
            job_dict.get('missing_skills'),
        ):
            rows_changed += 1

        cursor.execute("""
            UPDATE jobs SET
                fit_score = ?, priority = ?, company_type = ?, recommendation = ?,
                reason = ?, matched_skills = ?, missing_skills = ?
            WHERE job_id = ?
        """, (fit_score, priority, company_type, recommendation, reason, matched_skills, missing_skills, job_dict['job_id']))

        updated_fields_by_id[job_dict['job_id']] = {
            "Fit Score": fit_score,
            "Priority": priority,
            "Company Type": company_type,
            "Recommendation": recommendation,
            "Reason": reason,
            "Matched Skills": matched_skills,
            "Missing Skills": missing_skills,
        }

    conn.commit()
    conn.close()

    console.print(f"[dim]Rows evaluated: {len(jobs)} | Rows changed: {rows_changed}[/dim]")

    csv_rows_updated = 0
    csv_rows_missing = 0
    if os.path.exists(csv_path):
        with open(csv_path, mode='r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            csv_rows = list(reader)

        seen_ids = set()
        if fieldnames:
            for csv_row in csv_rows:
                jid = csv_row.get('Job ID')
                if jid in updated_fields_by_id:
                    csv_row.update(updated_fields_by_id[jid])
                    csv_rows_updated += 1
                    seen_ids.add(jid)

            csv_rows_missing = len(updated_fields_by_id) - len(seen_ids)

            backup_file_if_exists(csv_path)
            csv_out = f"{csv_path}.rescore_tmp"
            with open(csv_out, mode='w', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
                writer.writeheader()
                writer.writerows(csv_rows)
            shutil.move(csv_out, csv_path)

    console.print(f"[dim]CSV rows updated: {csv_rows_updated}[/dim]")
    if csv_rows_missing:
        console.print(f"[yellow]{csv_rows_missing} rescored job(s) exist in {resolved_db} but have no matching Job ID in {resolved_csv} -- their new scores are in the database but were not written to the CSV.[/yellow]")

    clean_existing_tracker(csv_path)
    console.print(f"[green]Successfully rescored {len(jobs)} active jobs and synced {os.path.basename(csv_path)}.[/green]")
    if legacy_rows_approximated:
        console.print(f"[yellow]{legacy_rows_approximated} job(s) predate stored posting text and were rescored from an approximated context -- their restriction/degree-requirement signals may not be fully accurate.[/yellow]")

def main():
    parser = argparse.ArgumentParser(description="Parse PDF Job cards and apply Job Review Rules v1.0")
    parser.add_argument("--pdf-dir", required=False, help="Directory containing PDF job lists")
    parser.add_argument("--dashboard", action="store_true", help="Print daily action dashboard from tracker and exit")
    parser.add_argument("--today", action="store_true", help="Print today's action queue and exit")
    parser.add_argument("--analytics", action="store_true", help="Print analytics dashboard showing conversion rates and exit")
    parser.add_argument("--dedup-physical", action="store_true", help="Find and combine physical duplicate rows in the tracker")
    parser.add_argument("--rescore", action="store_true", help="Recalculate skills and fit scores for all active jobs")
    parser.add_argument("--add", action="store_true", help="Manually add a job to the tracker")
    parser.add_argument("--date", help="Optional date override for manual addition (YYYY-MM-DD)")
    parser.add_argument("--update", nargs="?", const="", required=False, help="Company name, Job ID, or substring to update status (launches interactive menu if no company passed)")
    parser.add_argument("--status", required=False, help="New tracker status (e.g. Applied, Closed, Rejected, Cancelled, Expired)")
    parser.add_argument("--notes", required=False, help="Optional note to append to the job workflow record")
    parser.add_argument("--company", required=False, help="Company name for manual job addition")
    parser.add_argument("--position", required=False, help="Position title for manual job addition")
    parser.add_argument("--location", required=False, help="Location for manual job addition")
    parser.add_argument("--job-type", required=False, help="Job Type (Software Engineer or Operations)")
    parser.add_argument("--fit-score", required=False, type=int, help="Fit score (1-100)")
    parser.add_argument("--recommendation", required=False, help="Recommendation (e.g. ★★★★☆ Strong)")
    parser.add_argument("--provider", required=False, help="Provider / Source Type")
    parser.add_argument("--recruiter", required=False, help="Recruiter name")
    parser.add_argument("--hiring-manager", required=False, help="Hiring manager name")
    parser.add_argument("--url", required=False, help="Job posting URL")
    args = parser.parse_args()
    
    if args.add:
        handle_manual_add(
            company=args.company,
            position=args.position,
            location=args.location,
            job_type=args.job_type,
            provider=args.provider,
            recruiter=args.recruiter,
            hiring_manager=args.hiring_manager,
            url=args.url,
            fit_score=args.fit_score,
            recommendation=args.recommendation,
            status=args.status,
            notes=args.notes
        )
        return
        
    if args.today:
        print_today_queue()
        return
        
    if args.update is not None:
        if args.update == "" and not args.status:
            handle_interactive_update()
            return
        elif args.update != "" and not args.status:
            console.print("[red]Error: --status is required when specifying a company/job ID to update[/red]")
            return
        else:
            handle_status_update(args.update, args.status, args.notes)
            return
            
    if args.dedup_physical:
        handle_dedup_physical()
        return
        
    if args.rescore:
        handle_rescore()
        return
    
    if args.dashboard:
        _print_dashboard()
        return

    if args.analytics:
        print_analytics()
        return
    
    pdf_dir = args.pdf_dir
    if not pdf_dir:
        pdf_dir = select_pdf_directory()
        
    if not pdf_dir:
        console.print("[red]No directory selected. Exiting.[/red]")
        return
        
    if not os.path.exists(pdf_dir):
        console.print(f"[red]Directory not found: {pdf_dir}[/red]")
        return
        
    tracker_path = "master_tracker.csv"
    
    # Seed master tracker from any existing local CSV if master_tracker.csv doesn't exist yet
    if not os.path.exists(tracker_path):
        csv_files = [f for f in os.listdir(".") if f.endswith(".csv") and f != "master_tracker.csv"]
        if csv_files:
            seed_file = csv_files[0]
            try:
                shutil.copy(seed_file, tracker_path)
                console.print(f"[green]Seeded new master_tracker.csv from {seed_file}[/green]")
            except Exception as e:
                console.print(f"[yellow]Failed to seed master tracker: {e}[/yellow]")
        
    initialize_tracker(tracker_path)
    clean_existing_tracker(tracker_path)
    existing_jobs = load_tracker(tracker_path)

    # Open the DB early so we can use processed_files for incremental sync
    _sync_start = time.monotonic()
    _db_conn = sqlite3.connect("jobs.db")
    initialize_processed_files_table(_db_conn)

    # Run-level statistics collected during the scan
    run_stats = {
        "pdfs_discovered": 0,
        "pdfs_skipped":    0,
        "pdfs_processed":  0,
        "jobs_created":    0,
        "jobs_merged":     0,
        "files_failed":    0,
    }

    all_recommendations = []
    found_any_pdf = False

    # Store all unique job cards collected during the scan before reviewing
    raw_collected_jobs = {}  # job_id -> job dict
    empty_pdfs = []

    # Successful-parse processed_files records are held in memory and only
    # written once the final jobs.db/CSV save succeeds -- otherwise a PDF
    # whose jobs never made it to disk would be marked "success" and get
    # silently skipped (and its jobs permanently lost) on the next run.
    pending_success_records = []
    
    try:
        for root, dirs, files in os.walk(pdf_dir):
            pdf_files = sorted([f for f in files if f.lower().endswith('.pdf')])
            if not pdf_files:
                continue
                
            found_any_pdf = True
            
            # Check if the folder name is a valid date
            folder_name = os.path.basename(os.path.abspath(root))
            date_added = None
            for fmt in ("%Y-%m-%d", "%Y%m%d", "%m-%d-%Y", "%d-%m-%Y"):
                try:
                    dt = datetime.strptime(folder_name, fmt)
                    date_added = dt.strftime("%Y-%m-%d")
                    break
                except ValueError:
                    pass
                    
            if not date_added:
                date_added = datetime.now().strftime("%Y-%m-%d")
                
            console.print(f"[blue]Processing {len(pdf_files)} PDF files in {root} (Date Added: {date_added})...[/blue]")
            run_stats["pdfs_discovered"] += len(pdf_files)

            for pdf_idx, pdf_file in enumerate(pdf_files, start=1):
                pdf_path = os.path.join(root, pdf_file)
                pdf_uri = pathlib.Path(pdf_path).as_uri()

                # Ignore application confirmation emails that were saved as PDFs
                if "application was sent" in pdf_file.lower() or "application received" in pdf_file.lower():
                    run_stats["pdfs_skipped"] += 1
                    console.print(f"[dim]Skipping application confirmation: {pdf_file}[/dim]")
                    continue

                # --- Incremental sync: skip if content+parser-version unchanged ---
                pdf_hash = hash_pdf_file(pdf_path)
                if pdf_hash and check_pdf_processed(_db_conn, pdf_hash, PARSER_VERSION):
                    console.print(f"[dim]Skipping {pdf_file} (unchanged)[/dim]")
                    run_stats["pdfs_skipped"] += 1
                    continue

                console.print(f"[cyan]Parsing {pdf_file}...[/cyan]")

                try:
                    pdf_stat = os.stat(pdf_path)
                    reader = pypdf.PdfReader(pdf_path)
                    full_text = ""
                    for page in reader.pages:
                        t = page.extract_text(extraction_mode='layout')
                        if t:
                            full_text += t + "\n"

                    if not full_text.strip():
                        console.print(f"[yellow]No selectable text in {pdf_file}. Falling back to OCR...[/yellow]")
                        full_text = perform_ocr(pdf_path)

                    provider = detect_provider(full_text, pdf_file)

                    pdf_jobs_count = 0
                    job_idx = 1
                    for page_num, page in enumerate(reader.pages):
                        page_text = page.extract_text(extraction_mode='layout')
                        if not page_text or not page_text.strip():
                            continue

                        page_urls = extract_job_urls_from_page(page)
                        jobs = parse_job_cards_from_text(page_text, provider=provider, source_pdf=os.path.abspath(pdf_path))
                        pdf_jobs_count += len(jobs)

                        for idx, job in enumerate(jobs):
                            job["source_index"] = f"{pdf_idx}-{job_idx}"
                            job_idx += 1
                            # Map parsed job to top-to-bottom page annotation URL
                            if job.get("url", "N/A") == "N/A" and idx < len(page_urls):
                                job["url"] = page_urls[idx]

                            # Compute Job ID. New records get a fresh, permanent UUID --
                            # identity no longer depends on mutable fields, so a later
                            # parser correction (e.g. a fixed title) can't mint a new ID
                            # for what's really the same posting. A rediscovered posting
                            # that matches an existing tracked record (below) reuses that
                            # record's original Job ID instead of this freshly-generated one.
                            job_id = uuid.uuid4().hex

                            # Deduplicate before review using Canonical Key
                            current_canonical = canonical_job_key(job['company'], job['title'], job['location'])
                            is_aggregator = is_aggregator_placeholder(job['company'])

                            # Aggregator/digest placeholder "companies" (e.g.
                            # "Ladders-DailyDigest") don't identify a real employer, so
                            # canonical-key matching on company+title+location must never
                            # be used for them -- two unrelated digest postings would
                            # otherwise look like the same job just because they share a
                            # placeholder company name. Instead give them a strict
                            # occurrence fingerprint (provider + source PDF + date + this
                            # job's position within the PDF + normalized title) so that
                            # reprocessing the *same* PDF (e.g. after a parser-version bump
                            # defeats the incremental-sync hash skip) recognizes the row as
                            # already tracked instead of minting a new random ID for it
                            # every rescan.
                            job_fingerprint = None
                            if is_aggregator:
                                job_fingerprint = build_occurrence_fingerprint(
                                    job.get('provider', ''),
                                    os.path.abspath(pdf_path),
                                    date_added,
                                    job.get('source_index', ''),
                                    job['title'],
                                )
                                job['fingerprint'] = job_fingerprint

                            is_duplicate = False
                            existing_match = None

                            # 1. Check existing_jobs for a match. Real employers match on
                            # canonical key (with a fuzzy-title fallback flagged for manual
                            # review, never auto-merged); aggregator placeholders match only
                            # on the strict occurrence fingerprint above.
                            REAPPLY_DAYS = 60
                            REAPPLY_STATUSES = {"Applied", "Phone Screen", "Technical Interview", "Recruiter Submitted", "Waiting"}
                            possible_duplicate_note = None
                            for ej_id, ej in existing_jobs.items():
                                # existing_jobs is keyed by (job_id, date_added); the
                                # plain job_id is what jobs.db / job_workflow expect.
                                ej_job_id = ej_id[0] if isinstance(ej_id, tuple) else ej_id
                                ej_company = ej.get("Company", "")
                                ej_title = ej.get("Position", "")
                                ej_location = ej.get("Location", "")

                                if is_aggregator:
                                    if not job_fingerprint or ej.get("Fingerprint") != job_fingerprint:
                                        continue
                                else:
                                    ej_canonical = canonical_job_key(ej_company, ej_title, ej_location)

                                    if ej_canonical != current_canonical:
                                        # Similarity alone is never grounds for automatic
                                        # merging -- two different requisitions ("Senior
                                        # Software Engineer" vs "...II") can legitimately
                                        # share a title. Flag it for a human to decide
                                        # instead of silently collapsing the rows.
                                        if (
                                            not possible_duplicate_note
                                            and normalize_string(ej_company) == normalize_string(job['company'])
                                            and locations_compatible(ej_location, job['location'])
                                            and title_similarity(ej_title, job['title']) >= 0.7
                                        ):
                                            possible_duplicate_note = (
                                                f"Possible duplicate of existing job {ej_job_id} "
                                                f"('{ej_title}') -- title is similar but not an exact "
                                                f"match; needs manual review"
                                            )
                                        continue

                                staleness_date_str = ej.get("Last Seen") or ej.get("Date Added", "")
                                try:
                                    existing_date = date.fromisoformat(staleness_date_str[:10])
                                    current_date = date.fromisoformat(date_added)
                                    age_days = (current_date - existing_date).days
                                    if age_days < 0:
                                        # Existing row is future-dated relative to this
                                        # run -- don't treat it as a valid recent match.
                                        continue
                                    ej_status = ej.get("Tracker Status", "New")

                                    # Re-apply window: if job was applied to
                                    if ej_status in REAPPLY_STATUSES:
                                        added_date = date.fromisoformat(ej.get("Date Added", staleness_date_str[:10]))
                                        age_from_added = (current_date - added_date).days
                                        if age_from_added <= REAPPLY_DAYS:
                                            # Still within the reapply window -- merge into
                                            # the existing Applied/Interview record instead
                                            # of creating a duplicate row. This used to
                                            # delete the existing row's workflow entirely,
                                            # which lost real application history.
                                            reapply_note = (
                                                f"Re-listed {age_days} days after original application "
                                                f"(was {ej_status}, originally seen {staleness_date_str})"
                                            )
                                            ej["Notes"] = (ej.get("Notes", "") + "; " + reapply_note).lstrip("; ")
                                            existing_match = ej
                                            is_duplicate = True
                                        else:
                                            # Reapply window lapsed -- treat as a genuinely
                                            # new opportunity, linked back to the prior
                                            # application via Previous Job ID.
                                            reapply_note = (
                                                f"Re-listed {age_days} days after original application "
                                                f"(was {ej_status}, originally seen {staleness_date_str})"
                                            )
                                            job["notes"] = (job.get("notes", "") + "; " + reapply_note).lstrip("; ")
                                            job["previous_job_id"] = ej_job_id
                                        break

                                    # Expired jobs can resurface immediately (no 30-day wait like
                                    # active applications) since the user never acted on them.
                                    # Treated as a genuinely new opportunity, linked back to the
                                    # expired posting via Previous Job ID -- the old row is kept
                                    # as history instead of being deleted.
                                    if ej_status == "Expired":
                                        reapply_note = f"Re-listed after expiring (originally seen {staleness_date_str})"
                                        job["notes"] = (job.get("notes", "") + "; " + reapply_note).lstrip("; ")
                                        job["previous_job_id"] = ej_job_id
                                        break

                                    if age_days <= 90:
                                        existing_match = ej
                                        is_duplicate = True
                                        break
                                except (ValueError, TypeError):
                                    existing_match = ej
                                    is_duplicate = True
                                    break

                            # 2. Check raw_collected_jobs for canonical match (skipped for
                            # aggregator placeholders, for the same reason as above).
                            if not is_duplicate and not is_aggregator:
                                for rj_id, rj_item in raw_collected_jobs.items():
                                    rj_job = rj_item["job"]
                                    rj_canonical = canonical_job_key(rj_job['company'], rj_job['title'], rj_job['location'])
                                    if rj_canonical == current_canonical:
                                        # Merge into the raw_collected_job
                                        is_duplicate = True
                                        run_stats["jobs_merged"] += 1
                                        rj_job["provider"] = merge_delimited_field(
                                            rj_job.get("provider", ""),
                                            job.get("provider", ""),
                                        )

                                        rj_job["source_pdf"] = merge_delimited_field(
                                            rj_job.get("source_pdf", ""),
                                            job.get("source_pdf", ""),
                                        )
                                        break

                            if existing_match:
                                # Merge metadata into the existing database/CSV record
                                run_stats["jobs_merged"] += 1
                                existing_match["Provider"] = merge_delimited_field(
                                    existing_match.get("Provider", ""),
                                    job.get("provider", ""),
                                )

                                existing_match["Source PDF"] = merge_delimited_field(
                                    existing_match.get("Source PDF", ""),
                                    job.get("source_pdf", ""),
                                )

                                # This is a fresh sighting of the existing record.
                                existing_match["Last Seen"] = date_added

                            # (Spammy "Also discovered on" notes generation has been removed)

                            if not is_duplicate and possible_duplicate_note:
                                job["notes"] = (job.get("notes", "") + "; " + possible_duplicate_note).lstrip("; ")

                            if is_duplicate or job_id in raw_collected_jobs:
                                continue

                            # Store for review phase
                            raw_collected_jobs[job_id] = {
                                "job": job,
                                "job_id": job_id,
                                "date_added": date_added
                            }

                    if pdf_jobs_count == 0:
                        # Check if this empty PDF is a known non-job file to suppress warning
                        filename_lower = pdf_file.lower()
                        ignored_patterns = [
                            "resume report",
                            "weekly digest",
                            "northrop grumman",
                            "remote jobs that"
                        ]
                        if not any(pat in filename_lower for pat in ignored_patterns):
                            empty_pdfs.append(pathlib.Path(pdf_path).as_uri())

                    # Defer marking this PDF as successfully processed until the
                    # final jobs.db/CSV save succeeds (see pending_success_records).
                    run_stats["pdfs_processed"] += 1
                    if pdf_hash:
                        pending_success_records.append(
                            (pdf_hash, pdf_path, pdf_stat.st_size, pdf_stat.st_mtime)
                        )

                except Exception as e:
                    run_stats["files_failed"] += 1
                    console.print(f"[red]Error parsing {pdf_file}: {e}[/red]")
                    if pdf_hash:
                        record_pdf_processed(
                            _db_conn, pdf_hash, PARSER_VERSION, pdf_path,
                            os.path.getsize(pdf_path) if os.path.exists(pdf_path) else 0,
                            os.path.getmtime(pdf_path) if os.path.exists(pdf_path) else 0,
                            "error", str(e)
                        )
    except KeyboardInterrupt:
        console.print("\n[bold yellow]Scan interrupted by user (Ctrl+C). Saving progress for already parsed jobs...[/bold yellow]")
        found_any_pdf = True  # Fall through to save phase
        
    if not found_any_pdf:
        console.print(f"[yellow]No PDF files found in {pdf_dir}[/yellow]")
        _db_conn.close()
        return

    # Extract existing companies in the tracker to determine duplicate status
    existing_companies = {row.get("Company", "").strip().lower() for row in existing_jobs.values() if row.get("Company")}

    # Review Phase (Deduplicated)
    for job_id, item in raw_collected_jobs.items():
        job = item["job"]
        date_added = item["date_added"]
        
        should_rec, confidence, notes, fit_score, priority, company_type, recommendation, reason, matched_skills, missing_skills, job_type = evaluate_job(job)

        # evaluate_job() builds its own notes from scratch, so the reapply/expired
        # context recorded on job["notes"] during dedup detection above would
        # otherwise be silently discarded -- merge it back in here.
        reapply_note = job.get("notes", "")
        if reapply_note:
            notes = f"{reapply_note}; {notes}" if notes else reapply_note

        if should_rec:
            tracker_status = job.get("force_status", "New")
            review_status = "Closed" if tracker_status == "Cancelled" else "Imported"
            disposition = "Closed" if tracker_status == "Cancelled" else "Apply"
            
            # Action mapping
            if company_type == "Recruiting Firm" and recommendation in ["★★★★★ Apply Now", "★★★★☆ Strong"]:
                action = "Contact Recruiter"
            elif recommendation in ["★★★★★ Apply Now", "★★★★☆ Strong"]:
                action = "Apply"
            elif recommendation == "★★★☆☆ Maybe":
                action = "Review"
            else:
                action = "Ignore"
                
            already_in = "Yes" if job["company"].strip().lower() in existing_companies else "No"
            
            job_rec = {
                "Job ID": job_id,
                "Review Status": review_status,
                "Job Type": job_type,
                "Company": job["company"],
                "Position": job["title"],
                "Location": job["location"],
                "URL": job["url"],
                "Provider": job["provider"],
                "Source PDF": job["source_pdf"],
                "Source Index": job.get("source_index", ""),
                "Confidence": confidence,
                "Fit Score": fit_score,
                "Priority": priority,
                "Company Type": company_type,
                "Recommendation": recommendation,
                "Tracker Status": tracker_status,
                "Disposition": disposition,
                "Action": action,
                "Existing Company": already_in,
                "Reason": reason,
                "Matched Skills": matched_skills,
                "Missing Skills": missing_skills,
                "Date Added": date_added,
                "Last Seen": date_added,
                "Notes": notes,
                "Fingerprint": job.get("fingerprint") or canonical_job_key(job["company"], job["title"], job["location"]),
                "Previous Job ID": job.get("previous_job_id"),
                "Raw Context": job.get("raw_context", ""),
            }
            all_recommendations.append(job_rec)

    # Load all existing rows, preserve custom state fields, and map legacy fields
    existing_list = []
    known_tracker_companies = {"lvt", "decerto", "explorer software group", "infinity software development", "clearwaters.it", "new walton services", "american auto auction group", "co-diagnostics", "sunwest bank", "weave", "medallion bank"}
    for jid, row in existing_jobs.items():
        # Keep original "Existing Company" or compute if missing
        current_val = row.get("Existing Company", row.get("Already in Tracker"))
        if "Already in Tracker" in row:
            del row["Already in Tracker"]
            
        if current_val in ["Yes", "No"]:
            row["Existing Company"] = current_val
        else:
            comp = row.get("Company", "")
            if comp.strip().lower() in known_tracker_companies:
                row["Existing Company"] = "Yes"
            else:
                row["Existing Company"] = "No"
                
        # Classify if missing
        if "Job Type" not in row or not row["Job Type"]:
            row["Job Type"] = classify_job_type(row.get("Position", ""), row.get("Notes", ""))

        # Fingerprint is a derived audit field, not identity -- recompute it every
        # run from current fields rather than trusting a stale stored value, so
        # it stays accurate after manual corrections. Aggregator placeholders
        # are the exception: their Fingerprint is an occurrence key (provider +
        # source PDF + date + position-in-PDF + title), not derivable from the
        # row's current Company/Position/Location, so recomputing it here would
        # silently replace it with a canonical_job_key value that a later
        # rescan can never reproduce -- see the aggregator-idempotency tests.
        if is_aggregator_placeholder(row.get("Company", "")):
            if not row.get("Fingerprint"):
                row["Fingerprint"] = build_occurrence_fingerprint(
                    row.get("Provider", ""),
                    row.get("Source PDF", ""),
                    row.get("Date Added", ""),
                    "",
                    row.get("Position", ""),
                )
        else:
            row["Fingerprint"] = canonical_job_key(
                row.get("Company", ""), row.get("Position", ""), row.get("Location", "")
            )

        # Standardize Tracker Status
        status = row.get("Tracker Status", row.get("Status", "New"))
        if status not in VALID_STATUSES:
            if status == "Recruiter":
                status = "Recruiter Submitted"
            elif status == "Interview":
                status = "Phone Screen"
            elif status == "Technical":
                status = "Technical Interview"
            elif status in ["Skip", "Duplicate"]:
                status = "Cancelled"
            else:
                status = "New"
        row["Tracker Status"] = status

        # Auto-expire: if a job has sat as "New" for more than 7 days without being applied to, mark it Expired
        AUTO_EXPIRE_DAYS = 7
        if status == "New":
            date_added_str = row.get("Date Added", "")
            try:
                staleness_date_str = row.get("Last Seen") or date_added_str
                if not staleness_date_str: staleness_date_str = date.today().isoformat()
                staleness_date = date.fromisoformat(staleness_date_str[:10])
                if (date.today() - staleness_date).days > AUTO_EXPIRE_DAYS:
                    status = "Expired"
                    row["Tracker Status"] = "Expired"
                    row["Review Status"] = "Closed"
                    row["Disposition"] = "Closed"
                    row["Action"] = "Ignore"
            except (ValueError, TypeError):
                pass
        
        # Standardize Review Status
        review_status = row.get("Review Status")
        if not review_status:
            if status in ["Applied", "Phone Screen", "Technical Interview", "Recruiter Submitted", "Waiting", "Offer", "Accepted"]:
                review_status = "Applied"
            elif status in ["Rejected", "Cancelled", "Ghosted", "Expired"]:
                review_status = "Closed"
            else:
                review_status = "Imported"
        row["Review Status"] = review_status
        
        # Compute Priority if missing
        if "Priority" not in row or not row["Priority"]:
            age_val = row.get("Age (days)")
            age_days = int(age_val) if age_val and str(age_val).isdigit() else 0
            row["Priority"] = compute_priority(row.get("Recommendation", "★☆☆☆☆ Skip"), row.get("Action", "Ignore"), age_days)
            
        # Standardize existing Action column values
        act = row.get("Action", "Ignore")
        if act not in ["Apply", "Contact Recruiter", "Review", "Ignore", "Already Applied", "Waiting", "Interview", "Rejected", "Cancelled", "Expired", "Offer", "Accepted"]:
            if "apply" in act.lower():
                act = "Apply"
            elif "recruiter" in act.lower():
                act = "Contact Recruiter"
            elif "review" in act.lower():
                act = "Review"
            else:
                act = "Ignore"
        row["Action"] = act
        existing_list.append(row)
        
    combined_jobs = existing_list + all_recommendations
    
    # Sort combined jobs: Fit Score desc, Recommendation desc, Company asc
    combined_jobs.sort(key=lambda x: (
        -int(x.get("Fit Score", 0) if x.get("Fit Score") else 0),
        x.get("Recommendation", ""),
        x.get("Company", "").lower()
    ))
    
    # Write combined sorted jobs back to tracker CSV
    expected_headers = [
        "Job ID", "Review Status", "Job Type", "Company", "Position", "Location", "URL", "Provider",
        "Source PDF", "Source Index", "Confidence", "Fit Score", "Priority", "Company Type",
        "Recommendation", "Tracker Status", "Disposition", "Action", "Existing Company",
        "Age (days)", "Reason", "Matched Skills", "Missing Skills", "Date Added", "Last Seen", "Notes", "Recruiter", "Hiring Manager",
        "Fingerprint", "Previous Job ID"
    ]
    
    # Compute Age (days) for every row before writing
    today = date.today()
    for row in combined_jobs:
        date_added = row.get("Date Added", "")
        try:
            added = date.fromisoformat(date_added)
            row["Age (days)"] = (today - added).days
        except (ValueError, TypeError):
            row["Age (days)"] = ""
    
    # Synchronize all combined jobs to SQLite database 'jobs.db' and the
    # tracker CSV. These are two separate writes, not one atomic transaction,
    # so snapshot both first -- if the process is interrupted between them
    # (or mid-write), there's a recoverable pre-sync copy of each to restore
    # from instead of a jobs.db/master_tracker.csv pair that silently diverged.
    run_stats["jobs_created"] = len(all_recommendations)
    backup_file_if_exists("jobs.db")
    backup_file_if_exists(tracker_path)
    success = save_to_sqlite("jobs.db", combined_jobs)

    try:
        if success:
            write_tracker_csv_atomic(tracker_path, expected_headers, combined_jobs, extrasaction='ignore')
            # Only now mark this run's PDFs as successfully processed -- both the
            # jobs.db and CSV writes landed, so it's safe to skip them next time.
            for pdf_hash, pdf_path, file_size, modified_time in pending_success_records:
                record_pdf_processed(
                    _db_conn, pdf_hash, PARSER_VERSION, pdf_path,
                    file_size, modified_time, "success"
                )
        else:
            console.print("[red]Database save failed, aborting CSV write to prevent data divergence.[/red]")
            console.print("[red]PDFs parsed this run were not marked as processed and will be retried next run.[/red]")
            return
    finally:
        _db_conn.close()

    # Capture elapsed time
    _elapsed = time.monotonic() - _sync_start

    # ── SYNC COMPLETE banner (always shown, even when nothing is new) ──────────
    five_star_new  = sum(1 for r in all_recommendations if "★★★★★" in r.get("Recommendation", ""))
    four_star_new  = sum(1 for r in all_recommendations if "★★★★☆" in r.get("Recommendation", ""))
    console.print("\n[bold green]╔══════════════════════════════════════════════╗[/bold green]")
    console.print(f"[bold green]║[/bold green][bold green]{f'SYNC COMPLETE — {date.today()}':^46}[/bold green][bold green]║[/bold green]")
    console.print("[bold green]╠══════════════════════════════════════════════╣[/bold green]")
    console.print(f"[bold green]║[/bold green]  PDFs discovered:        [bold cyan]{run_stats['pdfs_discovered']:<6}[/bold cyan]              [bold green]║[/bold green]")
    console.print(f"[bold green]║[/bold green]  Unchanged PDFs skipped: [bold dim]{run_stats['pdfs_skipped']:<6}[/bold dim]              [bold green]║[/bold green]")
    console.print(f"[bold green]║[/bold green]  New/changed processed:  [bold cyan]{run_stats['pdfs_processed']:<6}[/bold cyan]              [bold green]║[/bold green]")
    console.print("[bold green]║                                              ║[/bold green]")
    console.print(f"[bold green]║[/bold green]  Jobs created:           [bold cyan]{run_stats['jobs_created']:<6}[/bold cyan]              [bold green]║[/bold green]")
    console.print(f"[bold green]║[/bold green]  Duplicates merged:      [bold cyan]{run_stats['jobs_merged']:<6}[/bold cyan]              [bold green]║[/bold green]")
    console.print(f"[bold green]║[/bold green]  New ★★★★★ recommendations this run:  [bold yellow]{five_star_new:<6}[/bold yellow]              [bold green]║[/bold green]")
    console.print(f"[bold green]║[/bold green]  New ★★★★☆ recommendations this run:  [bold yellow]{four_star_new:<6}[/bold yellow]              [bold green]║[/bold green]")
    console.print(f"[bold green]║[/bold green]  Files failed:           [bold red]{run_stats['files_failed']:<6}[/bold red]              [bold green]║[/bold green]")
    console.print(f"[bold green]║[/bold green]  Elapsed:                [bold white]{f'{_elapsed:.1f}s':<6}[/bold white]              [bold green]║[/bold green]")
    console.print("[bold green]╚══════════════════════════════════════════════╝[/bold green]\n")

    # Calculate summary metrics
    new_jobs_count = len(all_recommendations)
    existing_jobs_count = len(existing_jobs)
    
    already_applied_count = sum(1 for row in combined_jobs if row.get("Tracker Status") in ["Applied", "Phone Screen", "Technical Interview", "Recruiter Submitted", "Waiting"])
    closed_jobs_count = sum(1 for row in combined_jobs if row.get("Tracker Status") in ["Rejected", "Cancelled", "Ghosted", "Expired"])
    need_review_count = sum(1 for row in combined_jobs if row.get("Tracker Status") == "New" and row.get("Review Status") == "Imported")

    # Calculate priority breakdown
    p1_new = sum(1 for row in combined_jobs if row.get("Tracker Status") == "New" and row.get("Priority", "").startswith("P1"))
    p2_new = sum(1 for row in combined_jobs if row.get("Tracker Status") == "New" and row.get("Priority", "").startswith("P2"))
    p3_new = sum(1 for row in combined_jobs if row.get("Tracker Status") == "New" and row.get("Priority", "").startswith("P3"))
    p4_new = sum(1 for row in combined_jobs if row.get("Tracker Status") == "New" and row.get("Priority", "").startswith("P4"))

    # Calculate top missing skills across all new/imported jobs
    from collections import Counter
    missing_counter = Counter()
    for row in combined_jobs:
        if row.get("Tracker Status") == "New":
            for skill in row.get("Missing Skills", "").split(","):
                skill = skill.strip()
                if skill:
                    missing_counter[skill] += 1
    top_missing = missing_counter.most_common(5)

    # Output Console summary report
    console.print("\n[bold green]=========================================[/bold green]")
    console.print("[bold green]          JOB TRACKER SYNC REPORT        [/bold green]")
    console.print("[bold green]=========================================[/bold green]")
    console.print(f"Jobs tracked:        [bold cyan]{len(combined_jobs)}[/bold cyan]")
    console.print(f"New this run:        [bold cyan]{new_jobs_count}[/bold cyan]")
    console.print(f"")
    console.print(f"P1 \u2013 Apply today:     [bold cyan]{p1_new}[/bold cyan]")
    console.print(f"P2 \u2013 Apply this week: [bold cyan]{p2_new}[/bold cyan]")
    console.print(f"P3 \u2013 Investigate:     [bold yellow]{p3_new}[/bold yellow]")
    console.print(f"P4 \u2013 Ignore:          [dim]{p4_new}[/dim]")
    console.print(f"")
    console.print(f"Applied:             [bold green]{already_applied_count}[/bold green]")
    console.print(f"Closed:              [bold red]{closed_jobs_count}[/bold red]")
    console.print(f"Need review:         [bold yellow]{need_review_count}[/bold yellow]")
    if top_missing:
        console.print(f"")
        console.print("[bold]Top Missing Skills:[/bold]")
        for skill, count in top_missing:
            console.print(f"  [red]{skill}[/red] ({count} roles)")
    console.print("[bold green]=========================================[/bold green]\n")

    # Calculate pipeline metrics
    phone_screens = sum(1 for row in combined_jobs if row.get("Tracker Status") == "Phone Screen")
    technical_interviews = sum(1 for row in combined_jobs if row.get("Tracker Status") == "Technical Interview")
    recruiter_contacts = sum(1 for row in combined_jobs if row.get("Tracker Status") == "Recruiter Submitted" or row.get("Action") == "Contact Recruiter")
    waiting_count = sum(1 for row in combined_jobs if row.get("Tracker Status") == "Waiting")

    p1_count = sum(1 for row in combined_jobs if row.get("Tracker Status") == "New" and row.get("Priority", "").startswith("P1"))
    p2_count = sum(1 for row in combined_jobs if row.get("Tracker Status") == "New" and row.get("Priority", "").startswith("P2"))
    p3_count = sum(1 for row in combined_jobs if row.get("Tracker Status") == "New" and row.get("Priority", "").startswith("P3"))

    applied_count = sum(1 for row in combined_jobs if row.get("Tracker Status") == "Applied")
    rejected_count = sum(1 for row in combined_jobs if row.get("Tracker Status") == "Rejected")
    cancelled_count = sum(1 for row in combined_jobs if row.get("Tracker Status") == "Cancelled")
    ghosted_count = sum(1 for row in combined_jobs if row.get("Tracker Status") == "Ghosted")
    expired_count = sum(1 for row in combined_jobs if row.get("Tracker Status") == "Expired")

    # Calculate Pipeline Health metrics
    health_imported = len(combined_jobs)
    health_closed = sum(1 for row in combined_jobs if row.get("Tracker Status") in ["Rejected", "Cancelled", "Ghosted", "Expired"])
    health_active = health_imported - health_closed
    health_applied = sum(1 for row in combined_jobs if row.get("Tracker Status") == "Applied")
    health_interviewing = sum(1 for row in combined_jobs if row.get("Tracker Status") in ["Phone Screen", "Technical Interview"])
    
    health_active_apps = health_applied + health_interviewing
    health_app_rate = (health_applied / health_imported * 100) if health_imported > 0 else 0.0
    health_interview_rate = (health_interviewing / health_active_apps * 100) if health_active_apps > 0 else 0.0

    # Output Console Pipeline Health dashboard
    console.print("[bold magenta]=========================================[/bold magenta]")
    console.print("[bold magenta]            PIPELINE HEALTH              [/bold magenta]")
    console.print("[bold magenta]=========================================[/bold magenta]")
    console.print(f"Tracked:               [bold cyan]{health_imported}[/bold cyan]")
    console.print(f"Active:                [bold cyan]{health_active}[/bold cyan]")
    console.print(f"Applied:               [bold green]{health_applied}[/bold green]")
    console.print(f"Interviewing:          [bold yellow]{health_interviewing}[/bold yellow]")
    console.print(f"Closed:                [bold red]{health_closed}[/bold red]")
    console.print()
    console.print(f"Application Rate:      [bold green]{health_app_rate:.1f}%[/bold green]")
    if health_active_apps > 0:
        console.print(f"Interview Rate:        [bold yellow]{health_interview_rate:.1f}%[/bold yellow] ({health_interviewing} of {health_active_apps} active applications)")
    else:
        console.print(f"Interview Rate:        [bold yellow]0.0%[/bold yellow] (0 of 0 active applications)")
    console.print("[bold magenta]=========================================[/bold magenta]\n")

    # Output Console Pipeline dashboard
    console.print("[bold cyan]=========================================[/bold cyan]")
    console.print("[bold cyan]          APPLICATION PIPELINE           [/bold cyan]")
    console.print("[bold cyan]=========================================[/bold cyan]")
    console.print("[bold underline]Active Pipeline[/bold underline]")
    console.print(f"  Phone Screen:         [bold green]{phone_screens}[/bold green]")
    console.print(f"  Technical Interview:  [bold green]{technical_interviews}[/bold green]")
    console.print(f"  Recruiter Contact:    [bold green]{recruiter_contacts}[/bold green]")
    console.print(f"  Waiting:              [bold yellow]{waiting_count}[/bold yellow]")
    console.print("\n[bold underline]New Opportunities[/bold underline]")
    console.print(f"  P1 \u2013 Apply Today:     [bold cyan]{p1_count}[/bold cyan]")
    console.print(f"  P2 \u2013 Apply This Week:  [bold cyan]{p2_count}[/bold cyan]")
    console.print(f"  P3 \u2013 Investigate:     [bold yellow]{p3_count}[/bold yellow]")
    console.print("\n[bold underline]Closed / History[/bold underline]")
    console.print(f"  Applied (Pending):    [bold white]{applied_count}[/bold white]")
    console.print(f"  Rejected:             [bold red]{rejected_count}[/bold red]")
    console.print(f"  Cancelled:            [bold red]{cancelled_count}[/bold red]")
    console.print(f"  Ghosted:              [bold red]{ghosted_count}[/bold red]")
    console.print(f"  Expired:              [bold red]{expired_count}[/bold red]")
    console.print("[bold cyan]=========================================[/bold cyan]\n")

    # For console Table display: show all, or just new recommendations?
    if all_recommendations:
        all_recommendations.sort(key=lambda x: (
            -int(x["Fit Score"]),
            x["Recommendation"],
            x["Company"].lower()
        ))
        table = Table(title="New Job Recommendations (Sorted by Fit Score)")
        table.add_column("Job ID", style="dim")
        table.add_column("Review Status", style="blue")
        table.add_column("Job Type", style="cyan")
        table.add_column("Company", style="cyan")
        table.add_column("Position", style="magenta")
        table.add_column("Location", style="green")
        table.add_column("Fit Score", style="cyan")
        table.add_column("Priority", style="bold yellow")
        table.add_column("Recommendation", style="bold green")
        table.add_column("Confidence", style="bold")
        table.add_column("Action", style="yellow")
        table.add_column("Reason", style="blue")
        table.add_column("Matched Skills", style="green")
        table.add_column("Missing Skills", style="red")
        
        for rec in all_recommendations:
            table.add_row(
                rec["Job ID"], rec["Review Status"], rec["Job Type"], rec["Company"], rec["Position"], rec["Location"], 
                str(rec["Fit Score"]), rec["Priority"], rec["Recommendation"], rec["Confidence"], 
                rec["Action"], rec["Reason"], rec["Matched Skills"], rec["Missing Skills"]
            )
            
        console.print(table)
        console.print(f"[green]Successfully synced and sorted {len(combined_jobs)} total jobs (including {len(all_recommendations)} new) in {tracker_path} and jobs.db.[/green]")
    else:
        console.print("[yellow]No new recommendations found matching the criteria. Database is up to date.[/yellow]")
        
    if empty_pdfs:
        console.print("\n[yellow]No jobs parsed from the following PDF files (check formatting or OCR):[/yellow]")
        for f in empty_pdfs:
            console.print(f"  - {f}")

    # Always close with Current Opportunity Highlights — the one section that answers "anything exciting?"
    print_todays_highlights(all_recommendations, combined_jobs)

if __name__ == "__main__":
    main()
