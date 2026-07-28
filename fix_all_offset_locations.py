import argparse
import csv
import re
import shutil
from datetime import datetime

# Matches a right-hand side that actually looks like a location, so a
# 'Company · Location' Location field is only ever split when we can confirm
# the "location" side is really a location -- not just any string containing
# a '·', which could be legitimate text from an unrelated source.
_LOCATION_PATTERN = re.compile(
    r'\b(Remote|Hybrid|On-?site|United States|US|Canada|Utah|UT|CA|NY|TX|WA|'
    r'Salt Lake City)\b',
    re.IGNORECASE,
)


def _looks_like_location(text):
    return bool(_LOCATION_PATTERN.search(text))


def plan_fixes(rows, source_pdf_contains=None):
    """Return (fixes, skipped) without mutating rows. fixes is a list of
    (row, old_location, new_location); skipped is a list of (row, reason)."""
    fixes = []
    skipped = []
    for row in rows:
        loc = row.get('Location', '')
        if '·' not in loc:
            continue

        if source_pdf_contains and source_pdf_contains not in row.get('Source PDF', ''):
            continue

        prefix, _, suffix = loc.partition('·')
        prefix = prefix.strip()
        suffix = suffix.strip()

        if not suffix or not _looks_like_location(suffix):
            skipped.append((row, f"right side doesn't look like a location: {loc!r}"))
            continue

        fixes.append((row, loc, suffix))
    return fixes, skipped


def main():
    parser = argparse.ArgumentParser(
        description="Strip an offset 'Company · Location' prefix from the Location column."
    )
    parser.add_argument('--apply', action='store_true',
                         help="Write changes to master_tracker.csv. Without this flag, only prints the plan.")
    parser.add_argument('--source-pdf-contains', default=None,
                         help="Only touch rows whose Source PDF contains this substring.")
    args = parser.parse_args()

    csv_file = 'master_tracker.csv'

    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    fixes, skipped = plan_fixes(rows, args.source_pdf_contains)

    for row, old_loc, new_loc in fixes:
        print(f"{'FIX' if args.apply else 'WOULD FIX'} Job ID {row.get('Job ID')}: {old_loc!r} -> {new_loc!r}")
    for row, reason in skipped:
        print(f"SKIP Job ID {row.get('Job ID')}: {reason}")

    if not args.apply:
        print(f"\nDry run: {len(fixes)} row(s) would be fixed, {len(skipped)} row(s) skipped. Re-run with --apply to write changes.")
        return

    if fixes:
        backup_path = f"{csv_file}.bak.{datetime.now().strftime('%Y%m%d%H%M%S')}"
        shutil.copyfile(csv_file, backup_path)
        print(f"Backed up {csv_file} to {backup_path}")

    for row, old_loc, new_loc in fixes:
        row['Location'] = new_loc

    with open(csv_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Fixed {len(fixes)} malformed locations. Skipped {len(skipped)}.")

if __name__ == "__main__":
    main()
