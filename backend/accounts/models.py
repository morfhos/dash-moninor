from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


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
        ADMIN = "admin", "Administrador"
        COLABORADOR = "colaborador", "Colaborador"
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
        if self.role in (self.Role.ADMIN, self.Role.COLABORADOR):
            self.cliente_id = None
            self.funcao = ""
            if self.role == self.Role.ADMIN:
                if not self.is_staff and not self.is_superuser:
                    self.is_staff = True
        elif self.role == self.Role.CLIENTE and not self.funcao:
            self.funcao = self.Funcao.VIEWER
        super().save(*args, **kwargs)


class AuditLog(models.Model):
    """Modelo para registrar eventos de auditoria no sistema."""

    class EventType(models.TextChoices):
        LOGIN = "login", "Login"
        LOGOUT = "logout", "Logout"
        LOGIN_FAILED = "login_failed", "Login Falhou"
        PIECE_DELETED = "piece_deleted", "Peca Deletada"
        PIECE_CREATED = "piece_created", "Peca Criada"
        CAMPAIGN_CREATED = "campaign_created", "Campanha Criada"
        CAMPAIGN_DELETED = "campaign_deleted", "Campanha Deletada"
        CAMPAIGN_UPDATED = "campaign_updated", "Campanha Atualizada"
        ASSET_UPLOADED = "asset_uploaded", "Asset Enviado"
        USER_CREATED = "user_created", "Usuario Criado"
        USER_UPDATED = "user_updated", "Usuario Atualizado"
        USER_DELETED = "user_deleted", "Usuario Deletado"
        CLIENTE_CREATED = "cliente_created", "Cliente Criado"
        CLIENTE_UPDATED = "cliente_updated", "Cliente Atualizado"
        MEDIA_PLAN_UPLOADED = "media_plan_uploaded", "Plano de Midia Enviado"
        CONTRACT_UPLOADED = "contract_uploaded", "Contrato Enviado"

    event_type = models.CharField(max_length=30, choices=EventType.choices, db_index=True)
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True, default="")
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        verbose_name = "Log de Auditoria"
        verbose_name_plural = "Logs de Auditoria"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["event_type", "created_at"]),
            models.Index(fields=["user", "created_at"]),
        ]

    def __str__(self) -> str:
        user_str = self.user.username if self.user else "Sistema"
        return f"{self.get_event_type_display()} - {user_str} - {self.created_at}"

    @classmethod
    def log(cls, event_type: str, request=None, user=None, cliente=None, details=None):
        """Helper para criar logs de auditoria."""
        ip_address = None
        user_agent = ""

        if request:
            x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
            if x_forwarded_for:
                ip_address = x_forwarded_for.split(",")[0].strip()
            else:
                ip_address = request.META.get("REMOTE_ADDR")
            user_agent = request.META.get("HTTP_USER_AGENT", "")[:500]

            if user is None and hasattr(request, "user") and request.user.is_authenticated:
                user = request.user

        return cls.objects.create(
            event_type=event_type,
            user=user,
            cliente=cliente,
            ip_address=ip_address,
            user_agent=user_agent,
            details=details or {},
        )
