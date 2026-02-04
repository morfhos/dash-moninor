from django.contrib.auth.models import AbstractUser
from django.db import models


class Cliente(models.Model):
    nome = models.CharField(max_length=200)
    cnpj = models.CharField(max_length=30, blank=True, default="")
    ativo = models.BooleanField(default=True)
    logo = models.FileField(upload_to="clientes/logos/", blank=True, null=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"

    def __str__(self) -> str:
        return self.nome


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        CLIENTE = "cliente", "Cliente"

    class Funcao(models.TextChoices):
        VIEWER = "viewer", "Apenas ver"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CLIENTE)
    funcao = models.CharField(max_length=30, choices=Funcao.choices, blank=True, default="")
    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="usuarios",
    )

    def save(self, *args, **kwargs):
        if self.role == self.Role.ADMIN:
            self.cliente_id = None
            self.funcao = ""
            if not self.is_staff and not self.is_superuser:
                self.is_staff = True
        elif self.role == self.Role.CLIENTE and not self.funcao:
            self.funcao = self.Funcao.VIEWER
        super().save(*args, **kwargs)
