from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse
import tempfile

from campaigns.models import Campaign, CreativeAsset, Piece, PlacementCreative, PlacementDay, PlacementLine


class LoginFlowTests(TestCase):
    def setUp(self) -> None:
        User = get_user_model()
        self.user = User.objects.create_user(
            username="usuario@email.com",
            email="usuario@email.com",
            password="senha1234",
            role=getattr(User, "Role").ADMIN,
        )
        self.superuser = User.objects.create_superuser(
            username="admin",
            email="admin@email.com",
            password="senha1234",
        )

    def test_protected_page_redirects_to_login(self):
        resp = self.client.get(reverse("web:administracao"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login/", resp["Location"])

    def test_login_success_redirects_to_admin(self):
        resp = self.client.post(
            reverse("web:login"),
            {"login": "usuario@email.com", "password": "senha1234", "remember": "on"},
            follow=False,
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], reverse("web:administracao"))

    def test_login_invalid_shows_error(self):
        resp = self.client.post(
            reverse("web:login"),
            {"login": "usuario@email.com", "password": "errada"},
            follow=True,
        )
        self.assertContains(resp, "Login/e-mail ou senha inválidos.")

    def test_superuser_sees_full_menu(self):
        self.client.force_login(self.superuser)
        resp = self.client.get(reverse("web:dashboard"))
        self.assertContains(resp, "Campanhas")

    @override_settings(MEDIA_ROOT=tempfile.gettempdir())
    def test_cliente_sidebar_uses_uploaded_logo(self):
        User = get_user_model()
        cliente = getattr(User, "cliente").field.related_model.objects.create(
            nome="Cliente A",
            ativo=True,
            logo=SimpleUploadedFile("logo.png", b"fakepng", content_type="image/png"),
        )
        user = User.objects.create_user(
            username="cliente",
            email="cliente@email.com",
            password="senha1234",
            role=getattr(User, "Role").CLIENTE,
            cliente=cliente,
        )
        self.client.force_login(user)
        resp = self.client.get(reverse("web:dashboard"))
        self.assertContains(resp, cliente.logo.url)


@override_settings(MEDIA_ROOT=tempfile.gettempdir())
class ContractWizardTests(TestCase):
    def setUp(self) -> None:
        User = get_user_model()
        self.cliente = getattr(User, "cliente").field.related_model.objects.create(nome="Cliente A", ativo=True)
        self.admin = User.objects.create_user(
            username="adm",
            email="adm@email.com",
            password="senha1234",
            role=getattr(User, "Role").ADMIN,
        )
        self.user_cliente = User.objects.create_user(
            username="cli",
            email="cli@email.com",
            password="senha1234",
            role=getattr(User, "Role").CLIENTE,
            cliente=self.cliente,
        )

    def test_admin_opening_entry_redirects_to_client_selection(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("web:contract_wizard_entry"))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], reverse("web:clientes"))

    def test_admin_can_start_upload_from_client_action(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("web:clientes_upload", args=[self.cliente.id]))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], reverse("web:contract_wizard_step1", args=[self.cliente.id]))
        resp2 = self.client.get(reverse("web:contract_wizard_step1", args=[self.cliente.id]))
        self.assertContains(resp2, "Cliente: " + self.cliente.nome)

    def test_cliente_cannot_access_wizard(self):
        self.client.force_login(self.user_cliente)
        resp = self.client.get(reverse("web:contract_wizard_step1", args=[self.cliente.id]))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], reverse("web:dashboard"))

    def test_admin_can_create_campaign_and_upload_contract(self):
        self.client.force_login(self.admin)
        resp = self.client.post(
            reverse("web:contract_wizard_step1", args=[self.cliente.id]),
            {
                "name": "Campanha X",
                "start_date": "2025-12-01T00:00",
                "end_date": "2026-02-28T23:59",
                "timezone": "America/Sao_Paulo",
                "media_type": "online",
                "total_budget": "",
            },
            follow=False,
        )
        self.assertEqual(resp.status_code, 302)
        campaign = Campaign.objects.get(name="Campanha X", cliente_id=self.cliente.id)
        self.assertEqual(resp["Location"], reverse("web:contract_wizard_step2", args=[campaign.id]))

        resp2 = self.client.post(
            reverse("web:contract_wizard_step2", args=[campaign.id]),
            {
                "contract_file": SimpleUploadedFile("contrato.csv", b"a,b,c\n1,2,3\n", content_type="text/csv"),
            },
            follow=False,
        )
        self.assertEqual(resp2.status_code, 302)
        self.assertEqual(resp2["Location"], reverse("web:contract_done", args=[campaign.id]))

    def test_cliente_sair_visao_cliente_clears_session_and_redirects(self):
        User = get_user_model()
        cliente = getattr(User, "cliente").field.related_model.objects.create(nome="Cliente B", ativo=True)
        user = User.objects.create_user(
            username="cliente2",
            email="cliente2@email.com",
            password="senha1234",
            role=getattr(User, "Role").CLIENTE,
            cliente=cliente,
        )
        self.client.force_login(user)
        session = self.client.session
        session["impersonate_cliente_id"] = cliente.id
        session.save()
        resp = self.client.get(reverse("web:sair_visao_cliente"), follow=False)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], reverse("web:dashboard"))
        self.assertNotIn("impersonate_cliente_id", self.client.session)


@override_settings(MEDIA_ROOT=tempfile.gettempdir())
class CampaignUploadFlowTests(TestCase):
    def setUp(self) -> None:
        User = get_user_model()
        self.cliente = getattr(User, "cliente").field.related_model.objects.create(nome="Cliente A", ativo=True)
        self.admin = User.objects.create_user(
            username="adm",
            email="adm@email.com",
            password="senha1234",
            role=getattr(User, "Role").ADMIN,
        )
        self.user_cliente = User.objects.create_user(
            username="cli",
            email="cli@email.com",
            password="senha1234",
            role=getattr(User, "Role").CLIENTE,
            cliente=self.cliente,
        )
        self.campaign = Campaign.objects.create(
            cliente=self.cliente,
            name="Campanha X",
            timezone="America/Sao_Paulo",
            media_type=Campaign.MediaType.ONLINE,
            status=Campaign.Status.DRAFT,
            created_by=self.admin,
        )

    def test_cliente_cannot_access_plan_upload(self):
        self.client.force_login(self.user_cliente)
        resp = self.client.get(reverse("web:campaign_media_plan_upload", args=[self.campaign.id]))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], reverse("web:dashboard"))

    def test_admin_validate_plan_upload_shows_result(self):
        self.client.force_login(self.admin)
        dummy = SimpleUploadedFile(
            "plano.xlsx",
            b"not-a-real-xlsx",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        resp = self.client.post(
            reverse("web:campaign_media_plan_upload", args=[self.campaign.id]),
            {"_action": "validate", "xlsx_file": dummy, "replace_existing": "on"},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("result", resp.context)

    def test_admin_import_plan_upload_creates_lines_days_and_links(self):
        self.skipTest("Importação .xlsx depende de openpyxl; ambiente de testes não suporta.")

    def test_admin_assets_upload_creates_piece_and_asset(self):
        self.client.force_login(self.admin)
        f = SimpleUploadedFile("A_video.mp4", b"fakevideo", content_type="video/mp4")
        resp = self.client.post(
            reverse("web:campaign_assets_upload", args=[self.campaign.id]),
            {"files": [f]},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Piece.objects.filter(campaign=self.campaign, code="A").count(), 1)
        self.assertEqual(CreativeAsset.objects.filter(piece__campaign=self.campaign).count(), 1)

    def test_admin_can_open_client_campaigns_page(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("web:cliente_campaigns", args=[self.cliente.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Campanhas")
        self.assertContains(resp, self.campaign.name)

    def test_cliente_cannot_open_client_campaigns_page(self):
        self.client.force_login(self.user_cliente)
        resp = self.client.get(reverse("web:cliente_campaigns", args=[self.cliente.id]))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], reverse("web:dashboard"))

    def test_admin_can_edit_campaign(self):
        self.client.force_login(self.admin)
        resp = self.client.post(
            reverse("web:campaign_edit", args=[self.campaign.id]),
            {
                "name": "Campanha Editada",
                "start_date": "2025-12-01T08:00",
                "end_date": "2026-02-28T08:00",
                "timezone": "America/Sao_Paulo",
                "media_type": "offline",
                "total_budget": "",
                "status": "active",
            },
            follow=False,
        )
        self.assertEqual(resp.status_code, 302)
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.name, "Campanha Editada")
        self.assertEqual(self.campaign.status, "active")

    def test_admin_can_delete_campaign(self):
        self.client.force_login(self.admin)
        resp = self.client.post(reverse("web:campaign_delete", args=[self.campaign.id]), follow=False)
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Campaign.objects.filter(id=self.campaign.id).exists())

    def test_cliente_cannot_edit_or_delete_campaign(self):
        self.client.force_login(self.user_cliente)
        resp = self.client.get(reverse("web:campaign_edit", args=[self.campaign.id]))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], reverse("web:dashboard"))
        resp2 = self.client.post(reverse("web:campaign_delete", args=[self.campaign.id]), follow=False)
        self.assertEqual(resp2.status_code, 302)
        self.assertEqual(resp2["Location"], reverse("web:dashboard"))
