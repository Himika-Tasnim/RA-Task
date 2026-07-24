"""
Seed the enrollment registry (MemberRecord) checked by /request/.

Stands in for syncing from a real records system (admissions/SIS/HR): 10
students and 5 faculty. Two of them -- Himika and Sadika -- are seeded
already `issued`, since those are the real credentials already issued to
real wallets in this demo; everyone else starts unissued and is claimable
through the normal /request/ flow.

Idempotent -- safe to re-run; existing id_numbers are left alone except that
Himika/Sadika are always (re-)confirmed issued.

    python manage.py seed_members
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from ssi.models import MemberRecord

ALREADY_ISSUED = {"1234", "710004033"}

STUDENTS = [
    {"full_name": "Himika", "id_number": "1234", "department": "Software Engineering", "email": "himikatasnim2002@gmail.com"},
    {"full_name": "Ayesha Rahman", "id_number": "STU-001", "department": "Software Engineering", "email": "ayesha@university.edu"},
    {"full_name": "Rahim Ahmed", "id_number": "STU-002", "department": "Computer Science", "email": "rahim@university.edu"},
    {"full_name": "Nusrat Jahan", "id_number": "STU-003", "department": "Information Technology", "email": "nusrat@university.edu"},
    {"full_name": "Tanvir Hasan", "id_number": "STU-004", "department": "Electrical Engineering", "email": "tanvir@university.edu"},
    {"full_name": "Farhana Akter", "id_number": "STU-005", "department": "Computer Science", "email": "farhana@university.edu"},
    {"full_name": "Imran Kabir", "id_number": "STU-006", "department": "Software Engineering", "email": "imran@university.edu"},
    {"full_name": "Sabrina Islam", "id_number": "STU-007", "department": "Information Technology", "email": "sabrina@university.edu"},
    {"full_name": "Mahin Chowdhury", "id_number": "STU-008", "department": "Electrical Engineering", "email": "mahin@university.edu"},
    {"full_name": "Tania Sultana", "id_number": "STU-009", "department": "Computer Science", "email": "tania@university.edu"},
]

FACULTY = [
    {"full_name": "Sadika", "id_number": "710004033", "department": "CSE", "email": "tasnim@gmail.com"},
    {"full_name": "Karim Hossain", "id_number": "FAC-001", "department": "Computer Science", "email": "karim@university.edu"},
    {"full_name": "Nasrin Sultana", "id_number": "FAC-002", "department": "Software Engineering", "email": "nasrin@university.edu"},
    {"full_name": "Mahbub Alam", "id_number": "FAC-003", "department": "Information Technology", "email": "mahbub@university.edu"},
    {"full_name": "Farida Yasmin", "id_number": "FAC-004", "department": "Electrical Engineering", "email": "farida@university.edu"},
]


class Command(BaseCommand):
    help = "Seed the enrollment registry (10 students, 5 faculty) that /request/ checks against."

    def handle(self, *args, **options):
        created = 0
        for role, rows in (("student", STUDENTS), ("faculty", FACULTY)):
            for data in rows:
                record, was_created = MemberRecord.objects.get_or_create(
                    id_number=data["id_number"], defaults={**data, "role": role}
                )
                created += int(was_created)

                if data["id_number"] in ALREADY_ISSUED and not record.issued:
                    record.issued = True
                    record.issued_at = timezone.now()
                    record.save(update_fields=["issued", "issued_at"])

        total = len(STUDENTS) + len(FACULTY)
        self.stdout.write(self.style.SUCCESS(
            f"Seeded {created} new record(s) ({total} total: {len(STUDENTS)} students, {len(FACULTY)} faculty)."
        ))

        self.stdout.write("")
        self.stdout.write("Registry:")
        for r in MemberRecord.objects.all():
            state = "issued" if r.issued else "unissued"
            self.stdout.write(f"  [{state}] {r.full_name} ({r.id_number}, {r.role}) - {r.department}")
