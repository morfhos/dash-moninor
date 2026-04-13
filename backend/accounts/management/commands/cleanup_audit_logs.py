"""
Management command to clean up old audit logs.
Keeps the system lightweight by removing logs older than N days.

Usage:
  python manage.py cleanup_audit_logs              # default: 90 days
  python manage.py cleanup_audit_logs --days 180   # keep 180 days
  python manage.py cleanup_audit_logs --dry-run    # preview without deleting
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Remove audit logs older than N days (default: 90)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=90,
            help="Delete logs older than this many days (default: 90)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show how many logs would be deleted without actually deleting",
        )

    def handle(self, *args, **options):
        from accounts.models import AuditLog

        days = options["days"]
        cutoff = timezone.now() - timedelta(days=days)
        qs = AuditLog.objects.filter(created_at__lt=cutoff)
        count = qs.count()

        if options["dry_run"]:
            self.stdout.write(
                self.style.WARNING(f"DRY RUN: {count} logs older than {days} days would be deleted (before {cutoff.date()})")
            )
            return

        if count == 0:
            self.stdout.write(self.style.SUCCESS(f"No logs older than {days} days."))
            return

        # Delete in batches to avoid memory issues
        batch_size = 5000
        deleted_total = 0
        while True:
            ids = list(qs.values_list("pk", flat=True)[:batch_size])
            if not ids:
                break
            deleted, _ = AuditLog.objects.filter(pk__in=ids).delete()
            deleted_total += deleted
            self.stdout.write(f"  Deleted batch: {deleted} (total: {deleted_total}/{count})")

        self.stdout.write(
            self.style.SUCCESS(f"Done. Deleted {deleted_total} audit logs older than {days} days.")
        )
