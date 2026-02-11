from django.core import signing
from django.db import models
from django.utils import timezone

from accounts.models import Cliente


class GoogleAdsAccount(models.Model):
    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.CASCADE,
        related_name="google_ads_accounts",
    )
    customer_id = models.CharField(
        max_length=20,
        help_text="Google Ads Customer ID (xxx-xxx-xxxx)",
    )
    descriptive_name = models.CharField(max_length=250, blank=True, default="")
    _access_token = models.TextField(db_column="access_token", blank=True, default="")
    _refresh_token = models.TextField(db_column="refresh_token", blank=True, default="")
    token_expiry = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    last_sync = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Conta Google Ads"
        verbose_name_plural = "Contas Google Ads"
        unique_together = ("cliente", "customer_id")

    def __str__(self) -> str:
        return f"{self.cliente} - {self.customer_id} ({self.descriptive_name})"

    @property
    def access_token(self) -> str:
        if not self._access_token:
            return ""
        try:
            return signing.loads(self._access_token)
        except signing.BadSignature:
            return ""

    @access_token.setter
    def access_token(self, value: str) -> None:
        self._access_token = signing.dumps(value) if value else ""

    @property
    def refresh_token(self) -> str:
        if not self._refresh_token:
            return ""
        try:
            return signing.loads(self._refresh_token)
        except signing.BadSignature:
            return ""

    @refresh_token.setter
    def refresh_token(self, value: str) -> None:
        self._refresh_token = signing.dumps(value) if value else ""

    @property
    def is_token_expired(self) -> bool:
        if not self.token_expiry:
            return True
        return timezone.now() >= self.token_expiry


class SyncLog(models.Model):
    class Status(models.TextChoices):
        RUNNING = "running", "Em execução"
        SUCCESS = "success", "Sucesso"
        ERROR = "error", "Erro"

    account = models.ForeignKey(
        GoogleAdsAccount,
        on_delete=models.CASCADE,
        related_name="sync_logs",
    )
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.RUNNING)
    campaigns_synced = models.IntegerField(default=0)
    metrics_synced = models.IntegerField(default=0)
    error_message = models.TextField(blank=True, default="")

    class Meta:
        verbose_name = "Log de sincronização"
        verbose_name_plural = "Logs de sincronização"
        ordering = ["-started_at"]

    def __str__(self) -> str:
        return f"{self.account} - {self.started_at} ({self.status})"


# ---------------------------------------------------------------------------
# Meta Ads
# ---------------------------------------------------------------------------


class MetaAdsAccount(models.Model):
    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.CASCADE,
        related_name="meta_ads_accounts",
    )
    ad_account_id = models.CharField(
        max_length=30,
        help_text="Meta Ads Account ID (act_XXXXXXXXX)",
    )
    descriptive_name = models.CharField(max_length=250, blank=True, default="")
    _access_token = models.TextField(db_column="meta_access_token", blank=True, default="")
    token_expiry = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    last_sync = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Conta Meta Ads"
        verbose_name_plural = "Contas Meta Ads"
        unique_together = ("cliente", "ad_account_id")

    def __str__(self) -> str:
        return f"{self.cliente} - {self.ad_account_id} ({self.descriptive_name})"

    @property
    def access_token(self) -> str:
        if not self._access_token:
            return ""
        try:
            return signing.loads(self._access_token)
        except signing.BadSignature:
            return ""

    @access_token.setter
    def access_token(self, value: str) -> None:
        self._access_token = signing.dumps(value) if value else ""

    @property
    def is_token_expired(self) -> bool:
        if not self.token_expiry:
            return True
        return timezone.now() >= self.token_expiry


class MetaSyncLog(models.Model):
    class Status(models.TextChoices):
        RUNNING = "running", "Em execucao"
        SUCCESS = "success", "Sucesso"
        ERROR = "error", "Erro"

    account = models.ForeignKey(
        MetaAdsAccount,
        on_delete=models.CASCADE,
        related_name="sync_logs",
    )
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.RUNNING)
    campaigns_synced = models.IntegerField(default=0)
    metrics_synced = models.IntegerField(default=0)
    error_message = models.TextField(blank=True, default="")

    class Meta:
        verbose_name = "Log de sincronizacao Meta"
        verbose_name_plural = "Logs de sincronizacao Meta"
        ordering = ["-started_at"]

    def __str__(self) -> str:
        return f"{self.account} - {self.started_at} ({self.status})"
