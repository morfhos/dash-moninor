"""
Auto-audit signals: log model creates, updates, and deletes without
explicit calls in every view. Keeps the system lightweight by:
  - Only logging meaningful changes (skips auto_now fields)
  - Storing minimal details (model, pk, changed fields)
  - Using thread-local request to get the acting user
"""
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from accounts.middleware import get_current_request, get_current_user


# ── Helpers ──────────────────────────────────────────────────────────

# Fields to ignore when detecting "what changed" (auto-set by Django)
_SKIP_FIELDS = {"updated_at", "created_at", "last_login", "date_joined", "password"}


def _audit(event_type, instance, details):
    """Create an AuditLog entry using the current request context."""
    from accounts.models import AuditLog

    request = get_current_request()
    user = get_current_user()

    # Avoid logging during migrations / management commands
    if user is None and request is None:
        return

    cliente = None
    if hasattr(instance, "cliente_id") and instance.cliente_id:
        cliente_id = instance.cliente_id
        from accounts.models import Cliente
        try:
            cliente = Cliente.objects.get(pk=cliente_id)
        except Cliente.DoesNotExist:
            pass
    elif hasattr(instance, "campaign") and hasattr(instance.campaign, "cliente"):
        cliente = instance.campaign.cliente

    AuditLog.log(
        event_type=event_type,
        request=request,
        user=user,
        cliente=cliente,
        details=details,
    )


def _model_label(instance):
    return instance.__class__.__name__


def _summary(instance, fields=None):
    """Build a short summary dict from an instance."""
    d = {"model": _model_label(instance), "pk": instance.pk}
    if hasattr(instance, "name"):
        d["name"] = str(instance.name)[:100]
    elif hasattr(instance, "title"):
        d["name"] = str(instance.title)[:100]
    elif hasattr(instance, "username"):
        d["name"] = str(instance.username)[:100]
    elif hasattr(instance, "nome"):
        d["name"] = str(instance.nome)[:100]
    if fields:
        d["fields"] = fields
    return d


# ── Campaign signals ─────────────────────────────────────────────────

@receiver(post_save, sender="campaigns.Campaign")
def campaign_saved(sender, instance, created, **kwargs):
    if created:
        _audit("campaign_created", instance, _summary(instance))
    else:
        _audit("campaign_updated", instance, _summary(instance))


@receiver(pre_delete, sender="campaigns.Campaign")
def campaign_deleted(sender, instance, **kwargs):
    _audit("campaign_deleted", instance, _summary(instance))


# ── Piece signals ────────────────────────────────────────────────────

@receiver(post_save, sender="campaigns.Piece")
def piece_saved(sender, instance, created, **kwargs):
    if created:
        _audit("piece_created", instance, _summary(instance))


@receiver(pre_delete, sender="campaigns.Piece")
def piece_deleted(sender, instance, **kwargs):
    _audit("piece_deleted", instance, _summary(instance))


# ── User signals ─────────────────────────────────────────────────────

@receiver(post_save, sender="accounts.User")
def user_saved(sender, instance, created, **kwargs):
    if created:
        _audit("user_created", instance, _summary(instance))
    else:
        # Skip if just last_login changed (every login triggers save)
        update_fields = kwargs.get("update_fields")
        if update_fields and set(update_fields) <= _SKIP_FIELDS:
            return
        _audit("user_updated", instance, _summary(instance))


@receiver(pre_delete, sender="accounts.User")
def user_deleted(sender, instance, **kwargs):
    _audit("user_deleted", instance, _summary(instance))


# ── Cliente signals ──────────────────────────────────────────────────

@receiver(post_save, sender="accounts.Cliente")
def cliente_saved(sender, instance, created, **kwargs):
    if created:
        _audit("cliente_created", instance, _summary(instance))
    else:
        _audit("cliente_updated", instance, _summary(instance))


@receiver(pre_delete, sender="accounts.Cliente")
def cliente_deleted(sender, instance, **kwargs):
    _audit("cliente_deleted", instance, _summary(instance))


# ── Financial signals ────────────────────────────────────────────────

@receiver(post_save, sender="campaigns.FinancialSummary")
def financial_saved(sender, instance, created, **kwargs):
    _audit(
        "financial_updated",
        instance,
        {"model": "FinancialSummary", "pk": instance.pk, "campaign_id": instance.campaign_id},
    )


@receiver(post_save, sender="campaigns.MediaEfficiency")
def efficiency_saved(sender, instance, created, **kwargs):
    if not created:
        _audit(
            "efficiency_updated",
            instance,
            {"model": "MediaEfficiency", "pk": instance.pk, "veiculo": str(instance.veiculo)[:50]},
        )


@receiver(pre_delete, sender="campaigns.MediaEfficiency")
def efficiency_deleted(sender, instance, **kwargs):
    _audit(
        "efficiency_deleted",
        instance,
        {"model": "MediaEfficiency", "pk": instance.pk, "veiculo": str(instance.veiculo)[:50]},
    )


# ── Media plan / placement signals ───────────────────────────────────

@receiver(post_save, sender="campaigns.MediaPlanUpload")
def media_plan_uploaded(sender, instance, created, **kwargs):
    if created:
        _audit(
            "media_plan_uploaded",
            instance,
            {"model": "MediaPlanUpload", "pk": instance.pk, "campaign_id": instance.campaign_id},
        )


@receiver(post_save, sender="campaigns.FinancialUpload")
def financial_upload_saved(sender, instance, created, **kwargs):
    if created:
        _audit(
            "media_plan_uploaded",
            instance,
            {"model": "FinancialUpload", "pk": instance.pk, "campaign_id": instance.campaign_id, "type": "financial"},
        )
