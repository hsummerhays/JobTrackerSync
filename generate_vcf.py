#!/usr/bin/env python3
"""
Generate a standard vCard (.vcf) file for one or more contacts.
Usage:
  python generate_vcf.py --name "John Doe" --email "john@example.com" --phone "555-1234" --output "scratch/contact.vcf"
"""

import argparse
import os
import sys

def create_vcard_entry(name: str, email: str = "", phone: str = "", org: str = "", title: str = "", notes: str = "") -> str:
    lines = [
        "BEGIN:VCARD",
        "VERSION:3.0"
    ]
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

def main():
    parser = argparse.ArgumentParser(description="Generate vCard (.vcf) file")
    parser.add_argument("--name", required=True, help="Full Name")
    parser.add_argument("--email", default="", help="Email address")
    parser.add_argument("--phone", default="", help="Phone number")
    parser.add_argument("--org", default="", help="Company / Organization")
    parser.add_argument("--title", default="", help="Job Title")
    parser.add_argument("--notes", default="", help="Additional notes")
    parser.add_argument("--output", default="scratch/contact.vcf", help="Output .vcf file path")
    parser.add_argument("--append", action="store_true", help="Append to existing vcf file")

    args = parser.parse_args()

    vcard = create_vcard_entry(
        name=args.name,
        email=args.email,
        phone=args.phone,
        org=args.org,
        title=args.title,
        notes=args.notes
    )

    out_path = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    mode = "a" if args.append else "w"
    with open(out_path, mode, encoding="utf-8") as f:
        f.write(vcard)

    print(f"vCard created at: {out_path}")

if __name__ == "__main__":
    main()
