import csv
import shutil
from datetime import datetime

from dedup_utils import (
    canonical_key,
    is_clean_location,
    locations_compatible,
    merge_delimited_field,
    should_prefer_status,
)

def resolve_group(group):
    """Split a company+position+date group into merged rows. Rows whose
    locations don't plausibly refer to the same posting (e.g. two distinct
    clean locations) are kept separate instead of being merged into one,
    which would silently drop one posting's data."""
    resolved = []
    bases = []  # list of merged-row accumulators, one per distinct location

    for row in group:
        loc = row.get("Location", "")
        match = next((b for b in bases if locations_compatible(b.get("Location", ""), loc)), None)
        if match is None:
            bases.append(row.copy())
            continue

        base = match
        other = row
        if should_prefer_status(base.get('Tracker Status', ''), other.get('Tracker Status', '')):
            prev_status = base.get('Tracker Status')
            base['Tracker Status'] = other.get('Tracker Status')
            base['Review Status'] = other.get('Review Status')
            base['Action'] = other.get('Action')
            base['Disposition'] = other.get('Disposition')
            print(f"  -> Preserved advanced status: {prev_status} -> {base['Tracker Status']}")

        base["Provider"] = merge_delimited_field(base.get("Provider", ""), other.get("Provider", ""))
        base["Source PDF"] = merge_delimited_field(base.get("Source PDF", ""), other.get("Source PDF", ""))

        notes1 = base.get("Notes", "")
        notes2 = other.get("Notes", "")
        if notes2 and notes2 not in notes1:
            base["Notes"] = f"{notes1}; {notes2}".strip("; ")

        loc_base = base.get("Location", "")
        if not is_clean_location(loc_base) and is_clean_location(loc):
            base["Location"] = loc
            print(f"  -> Upgraded location from '{loc_base}' to '{loc}'")

    resolved.extend(bases)
    return resolved


def main():
    csv_file = 'master_tracker.csv'

    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    # Group by company + position + date
    groups = {}
    for row in rows:
        key = canonical_key(row.get('Company', ''), row.get('Position', ''), row.get('Date Added', ''))
        groups.setdefault(key, []).append(row)

    resolved_rows = []

    for key, group in groups.items():
        if len(group) == 1:
            resolved_rows.append(group[0])
        else:
            print(f"Merging duplicates for {key}: {len(group)} records")
            resolved_rows.extend(resolve_group(group))

    if len(resolved_rows) < len(rows):
        backup_path = f"{csv_file}.bak.{datetime.now().strftime('%Y%m%d%H%M%S')}"
        shutil.copyfile(csv_file, backup_path)
        print(f"Backed up {csv_file} to {backup_path}")

    with open(csv_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(resolved_rows)

    print(f"Deduplication complete. Kept {len(resolved_rows)} out of {len(rows)} records.")

if __name__ == "__main__":
    main()
