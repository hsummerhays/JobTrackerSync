#!/usr/bin/env python3
"""
Generate a standard vCard (.vcf) file for one or more contacts.
Usage:
  python generate_vcf.py --name "John Doe" --email "john@example.com" --phone "555-1234" --output "scratch/contact.vcf"
"""

import argparse
import os
import sys
from utils import create_vcard_entry

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
