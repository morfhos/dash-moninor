from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0005_cliente_slug"),
    ]

    operations = [
        migrations.CreateModel(
            name="Alert",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("titulo", models.CharField(max_length=200)),
                ("mensagem", models.TextField()),
                ("prioridade", models.CharField(
                    choices=[("low", "Baixa"), ("normal", "Normal"), ("high", "Alta"), ("urgent", "Urgente")],
                    default="normal",
                    max_length=20,
                )),
                ("lido", models.BooleanField(default=False)),
                ("lido_em", models.DateTimeField(blank=True, null=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("cliente", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="alertas",
                    to="accounts.cliente",
                )),
                ("enviado_por", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="alertas_enviados",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("lido_por", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="alertas_lidos",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                "verbose_name": "Alerta",
                "verbose_name_plural": "Alertas",
                "ordering": ["-criado_em"],
            },
        ),
    ]
