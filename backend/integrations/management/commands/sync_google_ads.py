"""Management command to sync Google Ads data.

Usage:
    python manage.py sync_google_ads              # sync all active accounts
    python manage.py sync_google_ads --cliente-id=1  # sync specific client
    python manage.py sync_google_ads --days=7      # last 7 days only
"""

from django.core.management.base import BaseCommand

from integrations.models import GoogleAdsAccount
from integrations.services.google_ads import full_sync


class Command(BaseCommand):
    help = "Sincroniza campanhas e métricas do Google Ads"

    def add_arguments(self, parser):
        parser.add_argument(
            "--cliente-id",
            type=int,
            default=None,
            help="ID do cliente para sincronizar (default: todos)",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Quantidade de dias de métricas para buscar (default: 30)",
        )

    def handle(self, *args, **options):
        qs = GoogleAdsAccount.objects.filter(is_active=True)
        if options["cliente_id"]:
            qs = qs.filter(cliente_id=options["cliente_id"])

        accounts = list(qs.select_related("cliente"))
        if not accounts:
            self.stdout.write(self.style.WARNING("Nenhuma conta Google Ads ativa encontrada."))
            return

        days = options["days"]
        for account in accounts:
            self.stdout.write(f"Sincronizando: {account} ...")
            log = full_sync(account, days=days)
            if log.status == "success":
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  OK — {log.campaigns_synced} campanhas, {log.metrics_synced} métricas"
                    )
                )
            else:
                self.stdout.write(
                    self.style.ERROR(f"  ERRO — {log.error_message[:200]}")
                )

        self.stdout.write(self.style.SUCCESS("Sync concluído."))
