"""
Send periodic WhatsApp reports to clients with whatsapp_reports=True.

Usage:
  python manage.py send_whatsapp_reports            # all eligible clients
  python manage.py send_whatsapp_reports --cliente 1 # specific client
  python manage.py send_whatsapp_reports --dry-run   # preview without sending

Schedule with cron every 3 days:
  0 9 */3 * * cd /path/to/backend && python manage.py send_whatsapp_reports
"""

from django.core.management.base import BaseCommand
from django.db.models import Sum

from accounts.models import Cliente
from campaigns.models import PlacementDay, PlacementLine


class Command(BaseCommand):
    help = "Send WhatsApp performance reports to eligible clients"

    def add_arguments(self, parser):
        parser.add_argument("--cliente", type=int, help="Send to specific client ID only")
        parser.add_argument("--dry-run", action="store_true", help="Preview messages without sending")
        parser.add_argument("--days", type=int, default=3, help="Report period in days (default: 3)")

    def handle(self, *args, **options):
        from datetime import date, timedelta
        from web.services.whatsapp import send_whatsapp, build_report_message

        dry_run = options["dry_run"]
        days = options["days"]
        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        # Select eligible clients
        qs = Cliente.objects.filter(ativo=True, whatsapp_reports=True).exclude(whatsapp="")
        if options["cliente"]:
            qs = qs.filter(id=options["cliente"])

        if not qs.exists():
            self.stdout.write(self.style.WARNING("Nenhum cliente elegível para relatório WhatsApp."))
            return

        sent = 0
        errors = 0

        for cliente in qs:
            self.stdout.write(f"\n[WA] {cliente.nome} -> {cliente.whatsapp}")

            # Compute metrics for this client in the period
            line_ids = list(
                PlacementLine.objects.filter(campaign__cliente=cliente)
                .values_list("id", flat=True)
            )
            if not line_ids:
                self.stdout.write(self.style.WARNING(f"  Sem dados de veiculação. Pulando."))
                continue

            stats = (
                PlacementDay.objects.filter(
                    placement_line_id__in=line_ids,
                    date__gte=start_date,
                    date__lte=end_date,
                )
                .aggregate(
                    total_imp=Sum("impressions"),
                    total_clk=Sum("clicks"),
                    total_cost=Sum("cost"),
                )
            )

            total_imp = stats["total_imp"] or 0
            total_clk = stats["total_clk"] or 0
            total_cost = float(stats["total_cost"] or 0)

            if total_imp == 0 and total_clk == 0:
                self.stdout.write(self.style.WARNING(f"  Sem dados no período {start_date} a {end_date}. Pulando."))
                continue

            global_ctr = round((total_clk / total_imp * 100), 2) if total_imp > 0 else 0
            global_cpc = round((total_cost / total_clk), 2) if total_clk > 0 else 0
            cpm = round((total_cost / total_imp * 1000), 2) if total_imp > 0 else 0

            # Try to get AI summary (from cache/DB)
            ai_summary = ""
            ai_recommendation = ""
            try:
                from web.services.ai_analytics import generate_analytics_insights
                ai_ctx = {
                    "total_imp": total_imp, "total_clk": total_clk,
                    "global_ctr": global_ctr, "cpc": global_cpc, "cpm": cpm,
                    "total_cost": round(total_cost, 2),
                    "date_from": str(start_date), "date_to": str(end_date),
                    "benchmarks": {"ctr": 2.0, "cpc": 3.50, "cpm": 15.00},
                }
                result = generate_analytics_insights(ai_ctx, cliente_id=cliente.id)
                if result:
                    ai_summary = result.get("executive_summary", "")
                    recs = result.get("recommendations", [])
                    if recs:
                        ai_recommendation = recs[0].get("text", "")
            except Exception:
                pass

            msg = build_report_message(
                cliente_nome=cliente.nome,
                total_imp=total_imp,
                total_clk=total_clk,
                global_ctr=global_ctr,
                global_cpc=global_cpc,
                cpm=cpm,
                total_cost=total_cost,
                ai_summary=ai_summary,
                ai_recommendation=ai_recommendation,
            )

            self.stdout.write(f"  Período: {start_date} a {end_date}")
            self.stdout.write(f"  Metricas: {total_imp:,} imp | {total_clk:,} clk | R$ {total_cost:,.2f}")

            if dry_run:
                # Encode-safe for Windows console
                safe_msg = msg.encode("ascii", "replace").decode("ascii")
                self.stdout.write(f"  [DRY RUN] Mensagem:\n{safe_msg}")
                sent += 1
                continue

            result = send_whatsapp(cliente.whatsapp, msg)
            if result.get("ok"):
                self.stdout.write(self.style.SUCCESS(f"  Enviado via {result.get('provider', 'unknown')}"))
                sent += 1
            else:
                self.stdout.write(self.style.ERROR(f"  Erro: {result.get('error', 'unknown')}"))
                errors += 1

        self.stdout.write(f"\n{'='*40}")
        self.stdout.write(self.style.SUCCESS(f"Enviados: {sent}") + f" | Erros: {errors}")
