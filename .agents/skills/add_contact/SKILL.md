---
name: add_contact
description: Generate a standard vCard (.vcf) file or import link to add contacts into Google Contacts (hsummerhays1@gmail.com).
---
# Add Contact Skill

Use this skill whenever the user asks to add or save contacts to Google Contacts (`hsummerhays1@gmail.com`).

## Workflow

1. Generate a `.vcf` vCard file containing the contact(s) using the helper script:
   ```bash
   python generate_vcf.py --name "[Full Name]" --email "[Email]" --phone "[Phone]" --output "scratch/[filename].vcf"
   ```
2. For multiple contacts, you can write the full `.vcf` file directly to [scratch/contacts.vcf](file:///c:/HughApps/JobTrackerSync/scratch/contacts.vcf).
3. Return:
   - A summary of the contact information.
   - A clickable link to the generated `.vcf` file.
   - A direct link to [Google Contacts Import](https://contacts.google.com/?authuser=hsummerhays1@gmail.com) where uploading the file adds them with one click.
