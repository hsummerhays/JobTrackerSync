import csv
import shutil
from datetime import datetime

from dedup_utils import (
    canonical_key,
    is_clean_location,
    merge_delimited_field,
    should_prefer_status,
    title_similarity,
)

# Below this, a malformed row isn't confidently matched to any clean row in
# its group; it's left untouched rather than guessed at.
MATCH_THRESHOLD = 0.5


def _merge_malformed_into(base, other):
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


def _match_malformed_to_clean(clean_records, malformed_records):
    """Pair each malformed row with the clean row whose Position it most
    resembles. Returns (matches, unmatched) where matches is a list of
    (clean_record, [malformed_record, ...]) and unmatched is malformed rows
    that had no unique high-confidence match."""
    if len(clean_records) == 1:
        # Nothing to disambiguate: only one possible destination.
        return [(clean_records[0], list(malformed_records))], []

    matches = {id(c): (c, []) for c in clean_records}
    unmatched = []
    for m in malformed_records:
        scored = sorted(
            clean_records,
            key=lambda c: title_similarity(c.get('Position', ''), m.get('Position', '')),
            reverse=True,
        )
        best = scored[0]
        best_score = title_similarity(best.get('Position', ''), m.get('Position', ''))
        second_score = (
            title_similarity(scored[1].get('Position', ''), m.get('Position', ''))
            if len(scored) > 1 else -1
        )
        if best_score >= MATCH_THRESHOLD and best_score > second_score:
            matches[id(best)][1].append(m)
        else:
            unmatched.append(m)
    return list(matches.values()), unmatched


def main():
    csv_file = 'master_tracker.csv'

    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    # Group by company + position + date, not company + date alone --
    # a company can legitimately post several different jobs the same day.
    groups = {}
    for row in rows:
        key = canonical_key(row.get('Company', ''), row.get('Position', ''), row.get('Date Added', ''))
        groups.setdefault(key, []).append(row)

    resolved_rows = []
    merged_count = 0

    for key, group in groups.items():
        if len(group) == 1:
            resolved_rows.append(group[0])
            continue

        clean_records = [r for r in group if is_clean_location(r.get('Location', ''))]
        malformed_records = [r for r in group if not is_clean_location(r.get('Location', ''))]

        if clean_records and malformed_records:
            print(f"Merging offset duplicates for {key}: {len(malformed_records)} malformed, {len(clean_records)} clean")

            matches, unmatched = _match_malformed_to_clean(clean_records, malformed_records)
            for clean_rec, matched_malformed in matches:
                base = clean_rec.copy()
                for other in matched_malformed:
                    merged_count += 1
                    _merge_malformed_into(base, other)
                resolved_rows.append(base)

            for m in unmatched:
                print(f"  -> WARNING: could not confidently match malformed row (Job ID {m.get('Job ID')}) to a clean duplicate; left unchanged")
                resolved_rows.append(m)
        else:
            # They are either all clean or all malformed. Keep them as is.
            resolved_rows.extend(group)

    if merged_count:
        backup_path = f"{csv_file}.bak.{datetime.now().strftime('%Y%m%d%H%M%S')}"
        shutil.copyfile(csv_file, backup_path)
        print(f"Backed up {csv_file} to {backup_path}")

    with open(csv_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(resolved_rows)

    print(f"Deduplication by company complete. Merged {merged_count} malformed records.")

if __name__ == "__main__":
    main()
