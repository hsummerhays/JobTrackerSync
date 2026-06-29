import os
import re
import csv
import json
from datetime import datetime
import pypdf
from rich.console import Console
from rich.table import Table

# Initialize Rich Console for beautiful outputs
console = Console()

# Rules and configuration constants
TRACKER_PATH = "job_tracker.csv"
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

# Rule 11 Legacy keywords
LEGACY_KEYWORDS = [
    "FileMaker", "Perl", "Monolith", "Legacy Java", "Enterprise modernization"
]

# FAANG scale companies for Rule 12 comparison
FAANG_COMPANIES = ["Google", "Apple", "Meta", "Facebook", "Amazon", "Netflix", "Microsoft"]

def initialize_tracker():
    """Ensure the tracker CSV exists and has the correct headers."""
    if not os.path.exists(TRACKER_PATH):
        with open(TRACKER_PATH, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["Company", "Position", "Location", "Link", "Provider", "Source PDF", "Confidence", "Status", "Date Added", "Notes"])
        console.print(f"[green]Initialized new tracker at {TRACKER_PATH}[/green]")

def clean_existing_tracker():
    """Clean up any existing rows in the tracker that fail the company name rules and migrate schema if needed."""
    if not os.path.exists(TRACKER_PATH):
        return
    
    rows_to_keep = []
    cleaned_any = False
    migrated_schema = False
    
    expected_headers = ["Company", "Position", "Location", "Link", "Provider", "Source PDF", "Confidence", "Status", "Date Added", "Notes"]
    
    try:
        with open(TRACKER_PATH, mode='r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            if not fieldnames:
                return
            
            if "Source PDF" not in fieldnames or "Link" not in fieldnames:
                migrated_schema = True
                
            for row in reader:
                company = row.get("Company", "")
                position = row.get("Position", "")
                if not company:
                    continue
                comp_lower = company.strip().lower()
                generic_roles = {
                    "software developer", "software engineer", "java developer", 
                    "backend developer", "backend engineer", "developer", "engineer",
                    "full stack developer", "full stack engineer", "java software developer",
                    "java software engineer", "j2ee developer", "j2ee software developer",
                    "software developer", "c developer", "react js developer", ".net developer"
                }
                if (comp_lower.startswith("hugh summerhays") or
                    "gmail" in comp_lower or
                    comp_lower.startswith("1 message") or
                    comp_lower.startswith("looking for") or
                    comp_lower.startswith("https://") or
                    comp_lower == "(remote)" or
                    comp_lower in generic_roles or
                    "create" in comp_lower or
                    "create" in position.lower()):
                    cleaned_any = True
                    continue
                
                # Migrate row structure
                migrated_row = {}
                for h in expected_headers:
                    if h == "Link":
                        migrated_row[h] = row.get("Link", row.get("URL", ""))
                    elif h == "Source PDF":
                        migrated_row[h] = row.get("Source PDF", "Unknown")
                    else:
                        migrated_row[h] = row.get(h, "")
                rows_to_keep.append(migrated_row)
                
        if cleaned_any or migrated_schema:
            with open(TRACKER_PATH, mode='w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=expected_headers)
                writer.writeheader()
                writer.writerows(rows_to_keep)
            if cleaned_any:
                console.print(f"[green]Cleaned up invalid rows from existing tracker at {TRACKER_PATH}[/green]")
            if migrated_schema:
                console.print(f"[green]Migrated tracker schema to include 'Link' and 'Source PDF' columns.[/green]")
    except Exception as e:
        console.print(f"[yellow]Failed to clean/migrate existing tracker: {e}[/yellow]")

def load_tracker():
    """Load existing jobs from tracker to prevent duplicates."""
    existing_jobs = set()
    if os.path.exists(TRACKER_PATH):
        with open(TRACKER_PATH, mode='r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Key based on normalized Company + Position
                key = (row["Company"].strip().lower(), row["Position"].strip().lower())
                existing_jobs.add(key)
    return existing_jobs

def load_config():
    """Load config file to retrieve last used folder."""
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_config(pdf_dir):
    """Save the selected folder to the config file."""
    try:
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump({"last_pdf_dir": pdf_dir}, f, indent=4)
    except Exception as e:
        console.print(f"[yellow]Failed to save config: {e}[/yellow]")

def select_pdf_directory():
    """Prompt the user for a PDF folder via GUI dialog or console input."""
    config = load_config()
    default_dir = config.get("last_pdf_dir", "")
    
    # Try GUI directory selection
    selected_dir = ""
    try:
        import tkinter as tk
        from tkinter import filedialog
        
        root = tk.Tk()
        root.withdraw()  # Hide main window
        root.attributes("-topmost", True)  # Bring dialog to front
        
        initial = default_dir if default_dir and os.path.exists(default_dir) else os.getcwd()
        console.print("[cyan]Opening folder selection dialog...[/cyan]")
        selected_dir = filedialog.askdirectory(title="Select Folder containing PDFs", initialdir=initial)
        root.destroy()
    except Exception as e:
        # Tkinter might fail in headless environments
        pass
        
    # Fallback/validation console prompt
    if not selected_dir:
        prompt_text = f"Enter PDF directory path"
        if default_dir:
            prompt_text += f" [default: {default_dir}]"
        prompt_text += ": "
        
        user_input = input(prompt_text).strip()
        if not user_input and default_dir:
            selected_dir = default_dir
        else:
            selected_dir = user_input
            
    if selected_dir:
        selected_dir = os.path.abspath(selected_dir)
        save_config(selected_dir)
        
    return selected_dir

def detect_provider(text, filename=""):
    """Detect job board provider from PDF content or filename."""
    full_text = (text + " " + filename).lower()
    if "linkedin" in full_text:
        return "LinkedIn"
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
            t = page.extract_text()
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

def parse_job_cards_from_text(text, provider="Unknown/Other", source_pdf="Unknown"):
    """
    Parse potential job cards from extracted text.
    Keying off patterns like:
    [Title]
    [Company]
    [Location]
    """
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
        is_title = any(kw in line.lower() for kw in ["engineer", "developer", "programmer", "architect", "analyst", "lead", "specialist", "manager", "support", "trainer"])
        
        if is_title and i + 1 < len(filtered_lines):
            title = line
            company = filtered_lines[i+1]
            location = ""
            url = ""
            
            # Look ahead for location and URL
            next_idx = i + 2
            found_location = False
            while next_idx < min(i + 6, len(filtered_lines)):
                next_line = filtered_lines[next_idx]
                if any(kw in next_line.lower() for kw in ["engineer", "developer", "programmer", "architect", "lead"]) and next_line != title:
                    break
                if state_city_pattern.search(next_line) or "remote" in next_line.lower():
                    location = next_line
                    found_location = True
                if "http" in next_line or "www." in next_line or next_line.startswith("linkedin.com"):
                    url = next_line
                next_idx += 1
            
            # Clean up company name
            company = re.split(r'\s+·\s+|\s+\d\.\d', company)[0].strip()
            
            if not found_location and i + 2 < len(filtered_lines):
                location = filtered_lines[i+2]
                
            jobs.append({
                "title": title,
                "company": company,
                "location": location,
                "url": url,
                "provider": provider,
                "source_pdf": source_pdf,
                "raw_context": "\n".join(filtered_lines[max(0, i-2):min(len(filtered_lines), i+8)])
            })
            i = next_idx - 1
        i += 1
        
    return jobs

def evaluate_job(job):
    """
    Apply Job Review Rules v1.0 to decide if the job should be recommended.
    Returns: (should_recommend: bool, confidence: str, notes: str)
    """
    title = job["title"]
    company = job["company"]
    location = job["location"]
    context = job["raw_context"].lower()
    
    # Rule 3 & 4: Must have company and title
    if not title or not company:
        return False, "🔴 Low", "Rule 4: Missing company or title"
        
    # User rejects: company name filters
    comp_lower = company.strip().lower()
    # List of generic role titles that sometimes get incorrectly parsed as company names
    generic_roles = {
        "software developer", "software engineer", "java developer", 
        "backend developer", "backend engineer", "developer", "engineer",
        "full stack developer", "full stack engineer", "java software developer",
        "java software engineer", "j2ee developer", "j2ee software developer",
        "software developer", "c developer", "react js developer", ".net developer"
    }
    if (comp_lower.startswith("hugh summerhays") or
        "gmail" in comp_lower or
        comp_lower.startswith("1 message") or
        comp_lower.startswith("looking for") or
        comp_lower.startswith("https://") or
        comp_lower == "(remote)" or
        comp_lower in generic_roles or
        "create" in comp_lower or
        "create" in title.lower()):
        return False, "🔴 Low", "Failed company name or title exclusion criteria"
        
    # Rule 6: Relocation check (Utah or Remote only)
    is_utah = any(kw in location.lower() for kw in ["ut", "utah", "salt lake", "slc", "lehi", "provo", "ogden"])
    is_remote = "remote" in location.lower() or "remote" in title.lower()
    if not (is_utah or is_remote):
        return False, "🔴 Low", f"Rule 6: Relocation required (Location: {location})"
        
    # Rule 7: Hard bachelor's degree requirement
    degree_required = re.search(r"bachelor'?s?\s+degree\s+required", context) or re.search(r"\bbs\b.*\brequired\b", context)
    degree_preferred = re.search(r"bachelor'?s?\s+degree\s+preferred", context) or re.search(r"\bbs\b.*\bpreferred\b", context)
    if degree_required and not degree_preferred:
        return False, "🔴 Low", "Rule 7: Hard bachelor's degree requirement detected"
        
    # Rule 8: Skip list unless compelling reason
    compelling_reason = any(tech.lower() in context for tech in TECH_KEYWORDS)
    for pattern in SKIP_KEYWORDS:
        if re.search(pattern, title, re.IGNORECASE):
            if not compelling_reason:
                return False, "🔴 Low", f"Rule 8: Excluded role type ({pattern})"
                
    # Rule 16: Confidence determination
    confidence = "🔴 Low"
    notes = []
    
    # Check technology fits (Rule 10)
    matched_techs = [tech for tech in TECH_KEYWORDS if tech.lower() in context or tech.lower() in title.lower()]
    if matched_techs:
        notes.append(f"Tech matches: {', '.join(matched_techs)}")
        
    # Check legacy modernization fits (Rule 11)
    matched_legacy = [legacy for legacy in LEGACY_KEYWORDS if legacy.lower() in context]
    if matched_legacy:
        notes.append(f"Legacy modernization: {', '.join(matched_legacy)}")
        
    # Rule 12: Smaller-to-mid-sized preference
    is_faang = any(faang.lower() in company.lower() for faang in FAANG_COMPANIES)
    if is_faang:
        notes.append("FAANG scale (lower preference)")
    else:
        notes.append("Small-to-mid-sized (preferred)")
        
    # Determine confidence level
    is_priority = any(re.search(pat, title, re.IGNORECASE) for pat in PRIORITY_KEYWORDS)
    if is_priority and matched_techs:
        confidence = "🟢 High"
    elif matched_techs or is_priority:
        confidence = "🟡 Medium"
        
    notes_str = "; ".join(notes)
    
    # Rule 16: Low confidence jobs are never recommended
    should_recommend = confidence in ["🟢 High", "🟡 Medium"]
    
    return should_recommend, confidence, notes_str

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Parse PDF Job cards and apply Job Review Rules v1.0")
    parser.add_argument("--pdf-dir", required=False, help="Directory containing PDF job lists")
    args = parser.parse_args()
    
    pdf_dir = args.pdf_dir
    if not pdf_dir:
        pdf_dir = select_pdf_directory()
        
    if not pdf_dir:
        console.print("[red]No directory selected. Exiting.[/red]")
        return
        
    if not os.path.exists(pdf_dir):
        console.print(f"[red]Directory not found: {pdf_dir}[/red]")
        return
        
    initialize_tracker()
    clean_existing_tracker()
    existing_jobs = load_tracker()
    
    all_recommendations = []
    found_any_pdf = False
    
    for root, dirs, files in os.walk(pdf_dir):
        pdf_files = [f for f in files if f.lower().endswith('.pdf')]
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
        
        for pdf_file in pdf_files:
            pdf_path = os.path.join(root, pdf_file)
            console.print(f"[cyan]Parsing {pdf_file}...[/cyan]")
            
            text = extract_pdf_text(pdf_path)
            if not text.strip():
                continue
                
            provider = detect_provider(text, pdf_file)
            jobs = parse_job_cards_from_text(text, provider=provider, source_pdf=pdf_file)
            console.print(f"  Extracted {len(jobs)} potential job cards (Provider: {provider}).")
            
            for job in jobs:
                key = (job["company"].strip().lower(), job["title"].strip().lower())
                if key in existing_jobs:
                    continue
                    
                should_rec, confidence, notes = evaluate_job(job)
                
                if should_rec:
                    job_rec = {
                        "Company": job["company"],
                        "Position": job["title"],
                        "Location": job["location"],
                        "Link": job["url"] or "N/A",
                        "Provider": job["provider"],
                        "Source PDF": job["source_pdf"],
                        "Confidence": confidence,
                        "Status": "New",
                        "Date Added": date_added,
                        "Notes": notes
                    }
                    all_recommendations.append(job_rec)
                
    if not found_any_pdf:
        console.print(f"[yellow]No PDF files found in {pdf_dir}[/yellow]")
        return

    if all_recommendations:
        table = Table(title="New Job Recommendations")
        table.add_column("Company", style="cyan")
        table.add_column("Position", style="magenta")
        table.add_column("Location", style="green")
        table.add_column("Link", style="blue")
        table.add_column("Provider", style="yellow")
        table.add_column("Source PDF", style="blue")
        table.add_column("Confidence", style="bold")
        table.add_column("Notes", style="white")
        
        with open(TRACKER_PATH, mode='a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            for rec in all_recommendations:
                table.add_row(rec["Company"], rec["Position"], rec["Location"], rec["Link"], rec["Provider"], rec["Source PDF"], rec["Confidence"], rec["Notes"])
                writer.writerow([
                    rec["Company"], rec["Position"], rec["Location"], rec["Link"],
                    rec["Provider"], rec["Source PDF"], rec["Confidence"], rec["Status"], rec["Date Added"], rec["Notes"]
                ])
                
        console.print(table)
        console.print(f"[green]Added {len(all_recommendations)} new recommendations to {TRACKER_PATH}[/green]")
    else:
        console.print("[yellow]No new recommendations found matching the criteria.[/yellow]")

if __name__ == "__main__":
    main()
