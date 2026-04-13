from __future__ import annotations

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

from django.conf import settings
from django.db import models
from django.utils import timezone

from accounts.models import Cliente


class Campaign(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        PAUSED = "paused", "Paused"
        FINISHED = "finished", "Finished"
        ARCHIVED = "archived", "Archived"

    class MediaType(models.TextChoices):
        ONLINE = "online", "ONLINE"
        OFFLINE = "offline", "OFFLINE"

    class RuntimeState(models.TextChoices):
        LIVE_NOW = "live_now", "LIVE_NOW"
        SCHEDULED = "scheduled", "SCHEDULED"
        ENDED = "ended", "ENDED"

    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name="campaigns")
    name = models.CharField(max_length=250)
    start_date = models.DateTimeField(default=timezone.now)
    end_date = models.DateTimeField(default=timezone.now)
    timezone = models.CharField(max_length=64, default="America/Sao_Paulo")
    total_budget = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    media_type = models.CharField(max_length=20, choices=MediaType.choices, default=MediaType.ONLINE)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_campaigns"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Campanha"
        verbose_name_plural = "Campanhas"
        indexes = [
            models.Index(fields=["cliente", "status"], name="campaign_cliente_status_idx"),
            models.Index(fields=["cliente", "start_date", "end_date"], name="campaign_cliente_dates_idx"),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def runtime_state(self) -> str:
        now = timezone.now()
        tz = timezone.get_current_timezone()
        if ZoneInfo is not None:
            try:
                tz = ZoneInfo(self.timezone)
            except Exception:
                tz = timezone.get_current_timezone()
        now_local = now.astimezone(tz)
        if now_local < self.start_date.astimezone(tz):
            return self.RuntimeState.SCHEDULED
        if now_local > self.end_date.astimezone(tz):
            return self.RuntimeState.ENDED
        return self.RuntimeState.LIVE_NOW


class RegionInvestment(models.Model):
    """Armazena a porcentagem de investimento por região para uma campanha."""
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="region_investments")
    region_name = models.CharField(max_length=200)
    percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    valor = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    order = models.PositiveIntegerField(default=0)
    color = models.CharField(max_length=20, default="#6366f1")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Investimento por Região"
        verbose_name_plural = "Investimentos por Região"
        unique_together = ("campaign", "region_name")
        ordering = ["order", "region_name"]

    def __str__(self) -> str:
        return f"{self.campaign_id} - {self.region_name}: {self.percentage}%"


class Piece(models.Model):
    class Type(models.TextChoices):
        VIDEO = "video", "Video"
        IMAGE = "image", "Image"
        AUDIO = "audio", "Audio"
        HTML5 = "html5", "HTML5"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        ARCHIVED = "archived", "Archived"

    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="pieces")
    code = models.CharField(max_length=20)
    title = models.CharField(max_length=250)
    duration_sec = models.PositiveIntegerField()
    type = models.CharField(max_length=20, choices=Type.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, blank=True)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Peça"
        verbose_name_plural = "Peças"
        unique_together = ("campaign", "code")

    def __str__(self) -> str:
        return f"{self.campaign_id} {self.code}"


class PlacementLine(models.Model):
    class MediaType(models.TextChoices):
        ONLINE = "online", "ONLINE"
        OFFLINE = "offline", "OFFLINE"

    class MediaChannel(models.TextChoices):
        TV_ABERTA = "tv_aberta", "TV_ABERTA"
        PAYTV = "paytv", "PAYTV"
        RADIO = "radio", "RADIO"
        OOH = "ooh", "OOH"
        JORNAL = "jornal", "JORNAL"
        META = "meta", "META"
        GOOGLE = "google", "GOOGLE"
        YOUTUBE = "youtube", "YOUTUBE"
        DISPLAY = "display", "DISPLAY"
        SEARCH = "search", "SEARCH"
        SOCIAL = "social", "SOCIAL"
        TIKTOK = "tiktok", "TIKTOK"
        LINKEDIN = "linkedin", "LINKEDIN"
        DV360 = "dv360", "DV360"
        DV360_YOUTUBE = "dv360_youtube", "DV360_YOUTUBE"
        DV360_SPOTIFY = "dv360_spotify", "DV360_SPOTIFY"
        DV360_ELETROMIDIA = "dv360_eletromid", "DV360_ELETROMIDIA"
        DV360_NETFLIX = "dv360_netflix", "DV360_NETFLIX"
        DV360_GLOBOPLAY = "dv360_globoplay", "DV360_GLOBOPLAY"
        DV360_ADMOOH = "dv360_admooh", "DV360_ADMOOH"
        OTHER = "other", "OTHER"

    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="placement_lines")
    media_type = models.CharField(max_length=20, choices=MediaType.choices, default=MediaType.ONLINE)
    media_channel = models.CharField(max_length=20, choices=MediaChannel.choices, default=MediaChannel.OTHER)
    market = models.CharField(max_length=100)
    channel = models.CharField(max_length=100, blank=True, default="")
    program = models.CharField(max_length=150, blank=True, default="")
    property_text = models.CharField(max_length=250, blank=True, default="")
    format_text = models.CharField(max_length=250, blank=True, default="")
    duration_sec = models.PositiveIntegerField(null=True, blank=True)
    external_ref = models.CharField(max_length=120, blank=True, default="", db_index=True)
    start_date = models.DateTimeField(null=True, blank=True)
    end_date = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Linha de mídia"
        verbose_name_plural = "Linhas de mídia"
        indexes = [
            models.Index(fields=["campaign", "media_channel"], name="placement_campaign_channel_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.market} - {self.channel}"


class PlacementDay(models.Model):
    placement_line = models.ForeignKey(PlacementLine, on_delete=models.CASCADE, related_name="days")
    date = models.DateField()
    insertions = models.PositiveBigIntegerField(default=0)
    cost = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    impressions = models.PositiveBigIntegerField(null=True, blank=True)
    clicks = models.PositiveBigIntegerField(null=True, blank=True)

    class Meta:
        verbose_name = "Dia de veiculação"
        verbose_name_plural = "Dias de veiculação"
        unique_together = ("placement_line", "date")
        indexes = [
            models.Index(fields=["date"], name="placementday_date_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.placement_line_id} {self.date}"


class AdGroup(models.Model):
    """Grupo de anúncios — nível intermediário entre Campaign e Ad."""
    class Status(models.TextChoices):
        ENABLED = "enabled", "Ativo"
        PAUSED = "paused", "Pausado"
        REMOVED = "removed", "Removido"

    placement_line = models.ForeignKey(PlacementLine, on_delete=models.CASCADE, related_name="ad_groups")
    name = models.CharField(max_length=250)
    external_ref = models.CharField(max_length=120, db_index=True)
    platform = models.CharField(max_length=20, default="google")  # google, meta
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ENABLED)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Grupo de Anúncios"
        verbose_name_plural = "Grupos de Anúncios"
        unique_together = ("placement_line", "external_ref")
        indexes = [
            models.Index(fields=["platform", "external_ref"], name="adgroup_plat_ref_idx"),
        ]

    def __str__(self):
        return f"{self.name} ({self.external_ref})"


class AdGroupDay(models.Model):
    """Métricas diárias por grupo de anúncios."""
    ad_group = models.ForeignKey(AdGroup, on_delete=models.CASCADE, related_name="days")
    date = models.DateField()
    impressions = models.PositiveBigIntegerField(default=0)
    clicks = models.PositiveBigIntegerField(default=0)
    cost = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        unique_together = ("ad_group", "date")
        indexes = [
            models.Index(fields=["date"], name="adgroupday_date_idx"),
        ]


class Ad(models.Model):
    """Anúncio individual dentro de um grupo."""
    class Status(models.TextChoices):
        ENABLED = "enabled", "Ativo"
        PAUSED = "paused", "Pausado"
        REMOVED = "removed", "Removido"

    class AdType(models.TextChoices):
        TEXT = "text", "Texto"
        RESPONSIVE_SEARCH = "responsive_search", "Pesquisa Responsiva"
        RESPONSIVE_DISPLAY = "responsive_display", "Display Responsivo"
        VIDEO = "video", "Vídeo"
        IMAGE = "image", "Imagem"
        SHOPPING = "shopping", "Shopping"
        APP = "app", "App"
        OTHER = "other", "Outro"

    ad_group = models.ForeignKey(AdGroup, on_delete=models.CASCADE, related_name="ads")
    name = models.CharField(max_length=250, blank=True, default="")
    headline = models.CharField(max_length=250, blank=True, default="")
    description = models.TextField(blank=True, default="")
    final_url = models.URLField(max_length=500, blank=True, default="")
    ad_type = models.CharField(max_length=30, choices=AdType.choices, default=AdType.OTHER)
    external_ref = models.CharField(max_length=120, db_index=True)
    platform = models.CharField(max_length=20, default="google")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ENABLED)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Anúncio"
        verbose_name_plural = "Anúncios"
        unique_together = ("ad_group", "external_ref")
        indexes = [
            models.Index(fields=["platform", "external_ref"], name="ad_plat_ref_idx"),
        ]

    def __str__(self):
        return self.name or self.headline or f"Ad #{self.external_ref}"


class AdDay(models.Model):
    """Métricas diárias por anúncio."""
    ad = models.ForeignKey(Ad, on_delete=models.CASCADE, related_name="days")
    date = models.DateField()
    impressions = models.PositiveBigIntegerField(default=0)
    clicks = models.PositiveBigIntegerField(default=0)
    cost = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        unique_together = ("ad", "date")
        indexes = [
            models.Index(fields=["date"], name="adday_date_idx"),
        ]


class CreativeAsset(models.Model):
    piece = models.ForeignKey(Piece, on_delete=models.CASCADE, related_name="assets")
    file = models.FileField(upload_to="campaigns/assets/")
    preview_url = models.URLField(blank=True, default="")
    thumb_url = models.URLField(blank=True, default="")
    checksum = models.CharField(max_length=128, blank=True, default="")
    metadata = models.JSONField(blank=True, default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Asset criativo"
        verbose_name_plural = "Assets criativos"

    def __str__(self) -> str:
        return f"{self.piece_id} {self.id}"


class ContractUpload(models.Model):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="contract_uploads")
    file = models.FileField(upload_to="campaigns/contracts/")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Contrato de upload"
        verbose_name_plural = "Contratos de upload"

    def __str__(self) -> str:
        return f"{self.campaign_id} {self.id}"


class MediaPlanUpload(models.Model):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="media_plan_uploads")
    file = models.FileField(upload_to="campaigns/media_plans/")
    summary = models.JSONField(blank=True, default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Upload de plano de mídia"
        verbose_name_plural = "Uploads de plano de mídia"

    def __str__(self) -> str:
        return f"{self.campaign_id} {self.id}"


class PlacementCreative(models.Model):
    placement_line = models.ForeignKey(PlacementLine, on_delete=models.CASCADE, related_name="placement_creatives")
    piece = models.ForeignKey(Piece, on_delete=models.CASCADE, related_name="placement_creatives")
    weight = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Vínculo linha x peça"
        verbose_name_plural = "Vínculos linha x peça"
        unique_together = ("placement_line", "piece")

    def __str__(self) -> str:
        return f"{self.placement_line_id} {self.piece_id}"


# ── Financial models ──────────────────────────────────────────────────────────

class FinancialUpload(models.Model):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="financial_uploads")
    file = models.FileField(upload_to="campaigns/financeiro/")
    summary = models.JSONField(blank=True, default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Upload Financeiro"
        verbose_name_plural = "Uploads Financeiros"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"FinancialUpload #{self.id} campaign={self.campaign_id}"


class FinancialSummary(models.Model):
    campaign = models.OneToOneField(Campaign, on_delete=models.CASCADE, related_name="financial_summary")
    # Dict keyed by meio (TV Aberta, Pay TV, Rádio, Jornal, Digital, OOH)
    # Each value: {valor_bruto, valor_liquido, desconto_pct, insercoes}
    data_by_channel = models.JSONField(blank=True, default=dict)
    # List of {month: 'YYYY-MM', valor: float}
    monthly_investment = models.JSONField(blank=True, default=list)
    total_valor_tabela = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    total_valor_negociado = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    total_desembolso = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    desconto_pct = models.DecimalField(max_digits=7, decimal_places=4, null=True, blank=True)
    grp_pct = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    cobertura_pct = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    frequencia_eficaz = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    # Controle de visibilidade para clientes
    client_visible = models.BooleanField(default=False, help_text="Se True, cliente pode ver a página financeira")
    # Dict com campos ocultos: {"total_valor_tabela": false, "desconto_pct": false, ...}
    # True = visível ao cliente, False/ausente = oculto ao cliente
    visibility = models.JSONField(blank=True, default=dict, help_text="Campos visíveis ao cliente")

    class Meta:
        verbose_name = "Resumo Financeiro"
        verbose_name_plural = "Resumos Financeiros"

    def __str__(self) -> str:
        return f"FinancialSummary campaign={self.campaign_id}"


class MediaEfficiency(models.Model):
    class ChannelType(models.TextChoices):
        TV_ABERTA = "tv_aberta", "TV Aberta"
        PAYTV = "paytv", "Pay TV"
        RADIO = "radio", "Rádio"
        JORNAL = "jornal", "Jornal"

    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="media_efficiencies")
    channel_type = models.CharField(max_length=20, choices=ChannelType.choices)
    veiculo = models.CharField(max_length=200)
    programa = models.CharField(max_length=200, blank=True, default="")
    praca = models.CharField(max_length=100, blank=True, default="")
    insercoes = models.PositiveIntegerField(default=0)
    trp = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    cpp = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    custo_tabela = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    custo_negociado = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    impactos = models.PositiveBigIntegerField(null=True, blank=True)
    cpm = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    ia_pct = models.DecimalField(max_digits=7, decimal_places=4, null=True, blank=True)
    formato = models.CharField(max_length=100, blank=True, default="")
    circulacao = models.PositiveBigIntegerField(null=True, blank=True)
    valor = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    class Meta:
        verbose_name = "Eficiência de Mídia"
        verbose_name_plural = "Eficiências de Mídia"
        indexes = [
            models.Index(fields=["campaign", "channel_type"], name="mediaeff_campaign_channel_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.channel_type} | {self.veiculo} | {self.praca}"


class PIControl(models.Model):
    class PIType(models.TextChoices):
        TV_ABERTA = "tv_aberta", "TV Aberta"
        TV_FECHADA = "tv_fechada", "TV Fechada"

    class Status(models.TextChoices):
        PENDENTE = "pendente", "Pendente"
        PAGO = "pago", "Pago"
        VENCIDO = "vencido", "Vencido"
        CANCELADO = "cancelado", "Cancelado"

    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="pi_controls")
    pi_type = models.CharField(max_length=20, choices=PIType.choices)
    pi_numero = models.CharField(max_length=50, blank=True, default="")
    produto = models.CharField(max_length=200, blank=True, default="")
    rede = models.CharField(max_length=200, blank=True, default="")
    praca = models.CharField(max_length=100, blank=True, default="")
    veiculacao_start = models.DateField(null=True, blank=True)
    veiculacao_end = models.DateField(null=True, blank=True)
    vencimento = models.DateField(null=True, blank=True, db_index=True)
    insercoes = models.PositiveIntegerField(default=0)
    valor_liquido = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDENTE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Controle de PI"
        verbose_name_plural = "Controle de PIs"
        indexes = [
            models.Index(fields=["campaign", "vencimento"], name="picontrol_campaign_venc_idx"),
        ]

    def __str__(self) -> str:
        return f"PI {self.pi_numero} | {self.rede} | {self.praca}"
