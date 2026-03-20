import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("campaigns", "0006_perf_indexes"),
    ]

    operations = [
        # RegionInvestment.valor
        migrations.AddField(
            model_name="regioninvestment",
            name="valor",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True),
        ),
        # FinancialUpload
        migrations.CreateModel(
            name="FinancialUpload",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("file", models.FileField(upload_to="campaigns/financeiro/")),
                ("summary", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "campaign",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="financial_uploads",
                        to="campaigns.campaign",
                    ),
                ),
            ],
            options={
                "verbose_name": "Upload Financeiro",
                "verbose_name_plural": "Uploads Financeiros",
                "ordering": ["-created_at"],
            },
        ),
        # FinancialSummary
        migrations.CreateModel(
            name="FinancialSummary",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("data_by_channel", models.JSONField(blank=True, default=dict)),
                ("monthly_investment", models.JSONField(blank=True, default=list)),
                ("total_valor_tabela", models.DecimalField(blank=True, decimal_places=2, max_digits=18, null=True)),
                ("total_valor_negociado", models.DecimalField(blank=True, decimal_places=2, max_digits=18, null=True)),
                ("total_desembolso", models.DecimalField(blank=True, decimal_places=2, max_digits=18, null=True)),
                ("desconto_pct", models.DecimalField(blank=True, decimal_places=4, max_digits=7, null=True)),
                ("grp_pct", models.DecimalField(blank=True, decimal_places=2, max_digits=7, null=True)),
                ("cobertura_pct", models.DecimalField(blank=True, decimal_places=2, max_digits=7, null=True)),
                ("frequencia_eficaz", models.DecimalField(blank=True, decimal_places=2, max_digits=7, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "campaign",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="financial_summary",
                        to="campaigns.campaign",
                    ),
                ),
            ],
            options={
                "verbose_name": "Resumo Financeiro",
                "verbose_name_plural": "Resumos Financeiros",
            },
        ),
        # MediaEfficiency
        migrations.CreateModel(
            name="MediaEfficiency",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "channel_type",
                    models.CharField(
                        choices=[
                            ("tv_aberta", "TV Aberta"),
                            ("paytv", "Pay TV"),
                            ("radio", "Rádio"),
                            ("jornal", "Jornal"),
                        ],
                        max_length=20,
                    ),
                ),
                ("veiculo", models.CharField(max_length=200)),
                ("programa", models.CharField(blank=True, default="", max_length=200)),
                ("praca", models.CharField(blank=True, default="", max_length=100)),
                ("insercoes", models.PositiveIntegerField(default=0)),
                ("trp", models.DecimalField(blank=True, decimal_places=4, max_digits=10, null=True)),
                ("cpp", models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ("custo_tabela", models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ("custo_negociado", models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ("impactos", models.PositiveIntegerField(blank=True, null=True)),
                ("cpm", models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ("ia_pct", models.DecimalField(blank=True, decimal_places=4, max_digits=7, null=True)),
                ("formato", models.CharField(blank=True, default="", max_length=100)),
                ("circulacao", models.PositiveIntegerField(blank=True, null=True)),
                ("valor", models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                (
                    "campaign",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="media_efficiencies",
                        to="campaigns.campaign",
                    ),
                ),
            ],
            options={
                "verbose_name": "Eficiência de Mídia",
                "verbose_name_plural": "Eficiências de Mídia",
            },
        ),
        migrations.AddIndex(
            model_name="mediaefficiency",
            index=models.Index(fields=["campaign", "channel_type"], name="mediaeff_campaign_channel_idx"),
        ),
        # PIControl
        migrations.CreateModel(
            name="PIControl",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "pi_type",
                    models.CharField(
                        choices=[("tv_aberta", "TV Aberta"), ("tv_fechada", "TV Fechada")],
                        max_length=20,
                    ),
                ),
                ("pi_numero", models.CharField(blank=True, default="", max_length=50)),
                ("produto", models.CharField(blank=True, default="", max_length=200)),
                ("rede", models.CharField(blank=True, default="", max_length=200)),
                ("praca", models.CharField(blank=True, default="", max_length=100)),
                ("veiculacao_start", models.DateField(blank=True, null=True)),
                ("veiculacao_end", models.DateField(blank=True, null=True)),
                ("vencimento", models.DateField(blank=True, db_index=True, null=True)),
                ("insercoes", models.PositiveIntegerField(default=0)),
                ("valor_liquido", models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pendente", "Pendente"),
                            ("pago", "Pago"),
                            ("vencido", "Vencido"),
                            ("cancelado", "Cancelado"),
                        ],
                        default="pendente",
                        max_length=20,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "campaign",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="pi_controls",
                        to="campaigns.campaign",
                    ),
                ),
            ],
            options={
                "verbose_name": "Controle de PI",
                "verbose_name_plural": "Controle de PIs",
            },
        ),
        migrations.AddIndex(
            model_name="picontrol",
            index=models.Index(fields=["campaign", "vencimento"], name="picontrol_campaign_venc_idx"),
        ),
    ]
