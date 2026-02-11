"""Management command to sync Meta Ads campaigns and metrics."""

from django.core.management.base import BaseCommand

from integrations.models import MetaAdsAccount
from integrations.services.meta_ads import full_sync


class Command(BaseCommand):
    help = "Sync Meta Ads campaigns and metrics for active accounts."

    def add_arguments(self, parser):
        parser.add_argument(
            "--cliente-id",
            type=int,
            default=None,
            help="Sync only for this cliente ID.",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Number of days of metrics to sync (default: 30).",
        )

    def handle(self, *args, **options):
        qs = MetaAdsAccount.objects.filter(is_active=True)

        if options["cliente_id"]:
            qs = qs.filter(cliente_id=options["cliente_id"])

        accounts = list(qs.select_related("cliente"))
        if not accounts:
            self.stdout.write(self.style.WARNING("No active Meta Ads accounts found."))
            return

        days = options["days"]
        for account in accounts:
            self.stdout.write(f"Syncing {account} (last {days} days)...")
            log = full_sync(account, days=days)
            if log.status == "success":
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  OK — {log.campaigns_synced} campaigns, {log.metrics_synced} metrics"
                    )
                )
            else:
                self.stdout.write(
                    self.style.ERROR(f"  FAILED — {log.error_message[:200]}")
                )
