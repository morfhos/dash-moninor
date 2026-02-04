from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class LoginFlowTests(TestCase):
    def setUp(self) -> None:
        User = get_user_model()
        self.user = User.objects.create_user(
            username="usuario@email.com",
            email="usuario@email.com",
            password="senha1234",
            role=getattr(User, "Role").ADMIN,
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
