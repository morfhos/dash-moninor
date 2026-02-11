"""Meta Ads (Facebook/Instagram) OAuth + Sync service.

Uses the Meta Graph API via REST (urllib.request) to:
- OAuth 2.0 authorization URL generation and token exchange
- Short-lived → long-lived token exchange
- Campaign sync (Meta Ads → PlacementLine)
- Metrics sync (Meta Ads → PlacementDay)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import urllib.request
import urllib.error
import urllib.parse
from datetime import date, timedelta
from typing import Any

from django.conf import settings
from django.utils import timezone

from accounts.models import Cliente
from campaigns.models import Campaign, PlacementLine, PlacementDay

from ..models import MetaAdsAccount, MetaSyncLog

logger = logging.getLogger(__name__)

META_GRAPH_VERSION = "v22.0"
META_GRAPH_BASE = f"https://graph.facebook.com/{META_GRAPH_VERSION}"
META_AUTH_BASE = f"https://www.facebook.com/{META_GRAPH_VERSION}"
SCOPES = "ads_read"


# ---------------------------------------------------------------------------
# OAuth helpers
# ---------------------------------------------------------------------------


def get_authorization_url(state: str = "") -> str:
    """Build the Meta OAuth consent URL (Facebook Login dialog)."""
    params = urllib.parse.urlencode({
        "client_id": settings.META_ADS_APP_ID,
        "redirect_uri": settings.META_ADS_REDIRECT_URI,
        "scope": SCOPES,
        "response_type": "code",
        "state": state,
    })
    return f"{META_AUTH_BASE}/dialog/oauth?{params}"


def exchange_code(code: str) -> dict[str, Any]:
    """Exchange authorization code for a long-lived access token.

    Step 1: code → short-lived token
    Step 2: short-lived → long-lived token (~60 days)
    """
    # Step 1: Exchange code for short-lived token
    params = urllib.parse.urlencode({
        "client_id": settings.META_ADS_APP_ID,
        "redirect_uri": settings.META_ADS_REDIRECT_URI,
        "client_secret": settings.META_ADS_APP_SECRET,
        "code": code,
    })
    url = f"{META_GRAPH_BASE}/oauth/access_token?{params}"
    req = urllib.request.Request(url, method="GET")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        logger.error("Meta token exchange error: %s", body[:500])
        raise RuntimeError(f"Erro ao trocar codigo OAuth: {body[:300]}") from e

    short_token = data.get("access_token", "")
    if not short_token:
        raise RuntimeError("Meta nao retornou access_token no exchange.")

    # Step 2: Exchange short-lived for long-lived token
    params2 = urllib.parse.urlencode({
        "grant_type": "fb_exchange_token",
        "client_id": settings.META_ADS_APP_ID,
        "client_secret": settings.META_ADS_APP_SECRET,
        "fb_exchange_token": short_token,
    })
    url2 = f"{META_GRAPH_BASE}/oauth/access_token?{params2}"
    req2 = urllib.request.Request(url2, method="GET")

    try:
        with urllib.request.urlopen(req2, timeout=30) as resp:
            data2 = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        logger.warning("Long-lived token exchange failed: %s", body[:300])
        # Fall back to short-lived token
        data2 = data

    long_token = data2.get("access_token", short_token)
    expires_in = data2.get("expires_in", 3600)  # seconds

    return {
        "access_token": long_token,
        "expires_in": expires_in,
    }


def _ensure_fresh_token(account: MetaAdsAccount) -> str:
    """Return a valid access token. Meta long-lived tokens last ~60 days."""
    if not account.is_token_expired and account.access_token:
        return account.access_token

    # Try to refresh the long-lived token (Meta allows refreshing before expiry)
    token = account.access_token
    if not token:
        raise RuntimeError(
            "Token Meta expirado e nao ha token para renovar. "
            "Reconecte a conta em Integracoes."
        )

    params = urllib.parse.urlencode({
        "grant_type": "fb_exchange_token",
        "client_id": settings.META_ADS_APP_ID,
        "client_secret": settings.META_ADS_APP_SECRET,
        "fb_exchange_token": token,
    })
    url = f"{META_GRAPH_BASE}/oauth/access_token?{params}"
    req = urllib.request.Request(url, method="GET")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        logger.error("Meta token refresh failed: %s", body[:300])
        raise RuntimeError(
            "Token Meta expirado e nao foi possivel renovar. "
            "Reconecte a conta em Integracoes."
        ) from e

    new_token = data.get("access_token", "")
    expires_in = data.get("expires_in", 3600)
    if new_token:
        account.access_token = new_token
        account.token_expiry = timezone.now() + timedelta(seconds=expires_in)
        account.save(update_fields=["_access_token", "token_expiry", "updated_at"])
        return new_token

    # If refresh didn't return a new token, use existing
    return token


# ---------------------------------------------------------------------------
# Graph API helpers
# ---------------------------------------------------------------------------


def _appsecret_proof(access_token: str) -> str:
    """Generate appsecret_proof HMAC-SHA256 for Meta API calls."""
    return hmac.new(
        settings.META_ADS_APP_SECRET.encode("utf-8"),
        access_token.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _graph_get(access_token: str, path: str, params: dict | None = None) -> dict:
    """Make a GET request to the Meta Graph API."""
    proof = _appsecret_proof(access_token)
    qs = urllib.parse.urlencode({
        "access_token": access_token,
        "appsecret_proof": proof,
        **(params or {}),
    })
    url = f"{META_GRAPH_BASE}/{path}?{qs}"
    req = urllib.request.Request(url, method="GET")

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        logger.error("Meta Graph API error %s: %s", e.code, body[:500])
        friendly = _parse_meta_error(body)
        raise RuntimeError(friendly) from e


def _parse_meta_error(error_body: str) -> str:
    """Extract a human-readable message from a Meta Graph API error."""
    try:
        err = json.loads(error_body)
        error = err.get("error", {})
        msg = error.get("message", "")
        error_type = error.get("type", "")
        code = error.get("code", "")
        if code == 190:
            return "Token de acesso invalido ou expirado. Reconecte a conta em Integracoes."
        if code == 17:
            return "Limite de requisicoes da API atingido. Tente novamente em alguns minutos."
        if code == 100:
            return f"Parametro invalido: {msg}"
        return f"{error_type}: {msg}" if msg else error_body[:300]
    except (json.JSONDecodeError, KeyError):
        pass
    return error_body[:300]


def list_ad_accounts(access_token: str) -> list[dict]:
    """List ad accounts accessible with the current token."""
    data = _graph_get(access_token, "me/adaccounts", {
        "fields": "account_id,name,account_status",
        "limit": "100",
    })
    accounts = []
    for acct in data.get("data", []):
        accounts.append({
            "id": acct.get("account_id", ""),
            "name": acct.get("name", ""),
            "status": acct.get("account_status", 0),
        })
    return accounts


# ---------------------------------------------------------------------------
# Campaign & Metrics sync
# ---------------------------------------------------------------------------


def _get_or_create_campaign(account: MetaAdsAccount) -> Campaign:
    """Get or create a Campaign to hold Meta Ads placements."""
    name = f"Meta Ads - {account.descriptive_name or account.ad_account_id}"
    campaign, _ = Campaign.objects.get_or_create(
        cliente=account.cliente,
        name=name,
        defaults={
            "status": Campaign.Status.ACTIVE,
            "media_type": Campaign.MediaType.ONLINE,
            "start_date": timezone.now(),
            "end_date": timezone.now() + timedelta(days=365),
        },
    )
    return campaign


def sync_campaigns(account: MetaAdsAccount) -> int:
    """Sync campaigns from Meta Ads → PlacementLine. Returns count."""
    access_token = _ensure_fresh_token(account)
    aid = account.ad_account_id
    if not aid.startswith("act_"):
        aid = f"act_{aid}"

    data = _graph_get(access_token, f"{aid}/campaigns", {
        "fields": "id,name,status,objective,start_time,stop_time",
        "limit": "500",
    })

    parent_campaign = _get_or_create_campaign(account)
    count = 0

    for camp in data.get("data", []):
        campaign_id = camp.get("id", "")
        if not campaign_id:
            continue

        defaults = {
            "media_type": PlacementLine.MediaType.ONLINE,
            "media_channel": PlacementLine.MediaChannel.META,
            "market": account.descriptive_name or account.ad_account_id,
            "channel": camp.get("name", ""),
            "property_text": f"Meta Ads Campaign #{campaign_id}",
        }

        start = camp.get("start_time", "")
        stop = camp.get("stop_time", "")
        if start:
            defaults["start_date"] = start[:10]  # ISO datetime → date
        if stop:
            defaults["end_date"] = stop[:10]

        PlacementLine.objects.update_or_create(
            campaign=parent_campaign,
            external_ref=str(campaign_id),
            defaults=defaults,
        )
        count += 1

    # Handle pagination
    paging = data.get("paging", {})
    next_url = paging.get("next")
    while next_url:
        req = urllib.request.Request(next_url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                page_data = json.loads(resp.read().decode("utf-8"))
        except Exception:
            break
        for camp in page_data.get("data", []):
            campaign_id = camp.get("id", "")
            if not campaign_id:
                continue
            defaults = {
                "media_type": PlacementLine.MediaType.ONLINE,
                "media_channel": PlacementLine.MediaChannel.META,
                "market": account.descriptive_name or account.ad_account_id,
                "channel": camp.get("name", ""),
                "property_text": f"Meta Ads Campaign #{campaign_id}",
            }
            start = camp.get("start_time", "")
            stop = camp.get("stop_time", "")
            if start:
                defaults["start_date"] = start[:10]
            if stop:
                defaults["end_date"] = stop[:10]
            PlacementLine.objects.update_or_create(
                campaign=parent_campaign,
                external_ref=str(campaign_id),
                defaults=defaults,
            )
            count += 1
        next_url = page_data.get("paging", {}).get("next")

    return count


def sync_metrics(account: MetaAdsAccount, days: int = 30) -> int:
    """Sync daily metrics from Meta Ads → PlacementDay. Returns count."""
    access_token = _ensure_fresh_token(account)
    parent_campaign = _get_or_create_campaign(account)

    aid = account.ad_account_id
    if not aid.startswith("act_"):
        aid = f"act_{aid}"

    start_date = (date.today() - timedelta(days=days)).strftime("%Y-%m-%d")
    end_date = date.today().strftime("%Y-%m-%d")

    data = _graph_get(access_token, f"{aid}/insights", {
        "fields": "campaign_id,campaign_name,impressions,clicks,spend",
        "level": "campaign",
        "time_increment": "1",  # daily breakdown
        "time_range": json.dumps({"since": start_date, "until": end_date}),
        "limit": "500",
    })

    count = 0
    all_rows = data.get("data", [])

    # Handle pagination
    paging = data.get("paging", {})
    next_url = paging.get("next")
    while next_url:
        req = urllib.request.Request(next_url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                page_data = json.loads(resp.read().decode("utf-8"))
        except Exception:
            break
        all_rows.extend(page_data.get("data", []))
        next_url = page_data.get("paging", {}).get("next")

    for row in all_rows:
        campaign_id = row.get("campaign_id", "")
        if not campaign_id:
            continue

        try:
            placement_line = PlacementLine.objects.get(
                campaign=parent_campaign,
                external_ref=str(campaign_id),
            )
        except PlacementLine.DoesNotExist:
            continue

        metric_date = row.get("date_start", "")
        if not metric_date:
            continue

        PlacementDay.objects.update_or_create(
            placement_line=placement_line,
            date=metric_date,
            defaults={
                "impressions": int(row.get("impressions", 0)),
                "clicks": int(row.get("clicks", 0)),
                "cost": float(row.get("spend", 0)),
            },
        )
        count += 1

    return count


def full_sync(account: MetaAdsAccount, days: int = 30) -> MetaSyncLog:
    """Run a full sync: campaigns + metrics. Returns the MetaSyncLog entry."""
    log = MetaSyncLog.objects.create(account=account)
    try:
        campaigns_count = sync_campaigns(account)
        metrics_count = sync_metrics(account, days=days)

        log.status = MetaSyncLog.Status.SUCCESS
        log.campaigns_synced = campaigns_count
        log.metrics_synced = metrics_count
        log.finished_at = timezone.now()
        log.save()

        account.last_sync = timezone.now()
        account.save(update_fields=["last_sync", "updated_at"])
    except Exception as exc:
        logger.exception("Meta Ads sync failed for account %s", account)
        log.status = MetaSyncLog.Status.ERROR
        log.error_message = str(exc)[:2000]
        log.finished_at = timezone.now()
        log.save()
    return log
