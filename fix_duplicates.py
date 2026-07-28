import csv

from dedup_utils import (
    canonical_key,
    is_clean_location,
    merge_delimited_field,
    should_prefer_status,
)

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

            base = group[0].copy()

            # Combine logic
            for other in group[1:]:
                if should_prefer_status(base.get('Tracker Status', ''), other.get('Tracker Status', '')):
                    prev_status = base.get('Tracker Status')
                    base['Tracker Status'] = other.get('Tracker Status')
                    print(f"  -> Preserved advanced status: {prev_status} -> {base['Tracker Status']}")

                base["Provider"] = merge_delimited_field(base.get("Provider", ""), other.get("Provider", ""))
                base["Source PDF"] = merge_delimited_field(base.get("Source PDF", ""), other.get("Source PDF", ""))

                # Merge Notes
                notes1 = base.get("Notes", "")
                notes2 = other.get("Notes", "")
                if notes2 and notes2 not in notes1:
                    base["Notes"] = f"{notes1}; {notes2}".strip("; ")

                # Prefer clean location
                loc_base = base.get("Location", "")
                loc_other = other.get("Location", "")

                if not is_clean_location(loc_base) and is_clean_location(loc_other):
                    base["Location"] = loc_other
                    print(f"  -> Upgraded location from '{loc_base}' to '{loc_other}'")

            resolved_rows.append(base)
            
    with open(csv_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(resolved_rows)
        
    print(f"Deduplication complete. Kept {len(resolved_rows)} out of {len(rows)} records.")

if __name__ == "__main__":
    main()
