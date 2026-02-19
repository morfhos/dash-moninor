"""Google Ads OAuth + Sync service.

Uses the Google Ads REST API (not gRPC) to avoid grpcio compatibility issues.

Handles:
- OAuth 2.0 authorization URL generation and token exchange
- Token refresh
- Campaign sync (Google Ads → PlacementLine)
- Metrics sync (Google Ads → PlacementDay)
"""

from __future__ import annotations

import json
import logging
import urllib.request
import urllib.error
from datetime import date, timedelta
from typing import Any

from django.conf import settings
from django.utils import timezone
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import Flow

from accounts.models import Cliente
from campaigns.models import Campaign, PlacementLine, PlacementDay

from ..models import GoogleAdsAccount, SyncLog

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/adwords"]
GOOGLE_ADS_API_VERSION = "v23"
GOOGLE_ADS_BASE_URL = f"https://googleads.googleapis.com/{GOOGLE_ADS_API_VERSION}"


def _client_config() -> dict:
    return {
        "web": {
            "client_id": settings.GOOGLE_ADS_CLIENT_ID,
            "client_secret": settings.GOOGLE_ADS_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.GOOGLE_ADS_REDIRECT_URI],
        }
    }


def get_authorization_url(state: str = "") -> str:
    """Build the Google OAuth consent URL."""
    flow = Flow.from_client_config(_client_config(), scopes=SCOPES)
    flow.redirect_uri = settings.GOOGLE_ADS_REDIRECT_URI
    url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        state=state,
    )
    return url


def exchange_code(code: str) -> dict[str, Any]:
    """Exchange the authorization code for tokens."""
    flow = Flow.from_client_config(_client_config(), scopes=SCOPES)
    flow.redirect_uri = settings.GOOGLE_ADS_REDIRECT_URI
    flow.fetch_token(code=code)
    creds = flow.credentials
    return {
        "access_token": creds.token,
        "refresh_token": creds.refresh_token,
        "expiry": creds.expiry,
    }


# ---------------------------------------------------------------------------
# REST API helpers
# ---------------------------------------------------------------------------


def _ensure_fresh_token(account: GoogleAdsAccount) -> str:
    """Return a valid access token, refreshing if expired."""
    if not account.is_token_expired and account.access_token:
        return account.access_token

    creds = Credentials(
        token=account.access_token,
        refresh_token=account.refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.GOOGLE_ADS_CLIENT_ID,
        client_secret=settings.GOOGLE_ADS_CLIENT_SECRET,
        scopes=SCOPES,
    )
    creds.refresh(Request())
    account.access_token = creds.token
    account.token_expiry = creds.expiry
    account.save(update_fields=["_access_token", "token_expiry", "updated_at"])
    return creds.token


def _parse_ads_error(error_body: str) -> str:
    """Extract a human-readable message from a Google Ads API error response."""
    try:
        err = json.loads(error_body)
        details = err.get("error", {}).get("details", [{}])[0]
        errors = details.get("errors", [{}])
        if errors:
            code = errors[0].get("errorCode", {})
            msg = errors[0].get("message", "")
            error_key = list(code.values())[0] if code else ""
            if error_key == "DEVELOPER_TOKEN_NOT_APPROVED":
                return (
                    "Developer Token com acesso apenas para contas de teste. "
                    "Solicite Basic Access no Google Ads API Center "
                    "(Ferramentas > Config > Centro da API)."
                )
            if error_key == "CUSTOMER_NOT_ENABLED":
                return (
                    "Conta Google Ads desativada ou nao habilitada. "
                    "Verifique se o Customer ID esta correto e a conta esta ativa."
                )
            return f"{error_key}: {msg}"
    except (json.JSONDecodeError, KeyError, IndexError):
        pass
    return error_body[:300]


def list_accessible_customers(access_token: str) -> list[str]:
    """List customer IDs accessible with the current credentials."""
    url = f"{GOOGLE_ADS_BASE_URL}/customers:listAccessibleCustomers"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "developer-token": settings.GOOGLE_ADS_DEVELOPER_TOKEN,
    }
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            # resourceNames like "customers/1234567890"
            return [r.split("/")[-1] for r in data.get("resourceNames", [])]
    except Exception as exc:
        logger.warning("Failed to list accessible customers: %s", exc)
        return []


def list_client_accounts(access_token: str, manager_customer_id: str) -> list[dict]:
    """List non-manager client accounts under a manager (MCC) account."""
    cid = manager_customer_id.replace("-", "")
    query = """
        SELECT
            customer_client.id,
            customer_client.descriptive_name,
            customer_client.manager,
            customer_client.status
        FROM customer_client
        WHERE customer_client.status = 'ENABLED'
          AND customer_client.manager = false
    """
    try:
        rows = _ads_rest_search(access_token, cid, query, login_customer_id=cid)
    except RuntimeError:
        return []
    clients = []
    for row in rows:
        cc = row.get("customerClient", {})
        client_id = cc.get("id", "")
        if client_id:
            clients.append({
                "id": str(client_id),
                "name": cc.get("descriptiveName", ""),
            })
    return clients


def _ads_rest_search(
    access_token: str,
    customer_id: str,
    query: str,
    login_customer_id: str | None = None,
) -> list[dict]:
    """Execute a Google Ads query via REST API (paginated search).

    Args:
        login_customer_id: Manager account ID used for auth when querying
            a child account through MCC.

    Returns list of result rows as dicts.
    """
    cid = customer_id.replace("-", "")
    url = f"{GOOGLE_ADS_BASE_URL}/customers/{cid}/googleAds:search"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "developer-token": settings.GOOGLE_ADS_DEVELOPER_TOKEN,
        "Content-Type": "application/json",
    }
    if login_customer_id:
        headers["login-customer-id"] = login_customer_id.replace("-", "")

    all_rows = []
    page_token = None

    while True:
        payload = {"query": query}
        if page_token:
            payload["pageToken"] = page_token

        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            logger.error("Google Ads REST error %s: %s", e.code, error_body[:500])
            friendly = _parse_ads_error(error_body)
            raise RuntimeError(friendly) from e

        all_rows.extend(data.get("results", []))

        page_token = data.get("nextPageToken")
        if not page_token:
            break

    return all_rows


# ---------------------------------------------------------------------------
# Campaign & Metrics sync
# ---------------------------------------------------------------------------


def _get_or_create_campaign(account: GoogleAdsAccount) -> Campaign:
    """Get or create a Campaign to hold Google Ads placements."""
    name = f"Google Ads - {account.descriptive_name or account.customer_id}"
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


def _map_channel_type(channel_type: str) -> str:
    """Map Google Ads AdvertisingChannelType to PlacementLine.MediaChannel."""
    mapping = {
        "SEARCH": PlacementLine.MediaChannel.SEARCH,
        "DISPLAY": PlacementLine.MediaChannel.DISPLAY,
        "VIDEO": PlacementLine.MediaChannel.YOUTUBE,
        "SHOPPING": PlacementLine.MediaChannel.GOOGLE,
        "MULTI_CHANNEL": PlacementLine.MediaChannel.GOOGLE,
        "PERFORMANCE_MAX": PlacementLine.MediaChannel.GOOGLE,
    }
    return mapping.get(channel_type, PlacementLine.MediaChannel.GOOGLE)


def sync_campaigns(
    account: GoogleAdsAccount,
    target_customer_id: str | None = None,
    login_customer_id: str | None = None,
) -> int:
    """Sync campaigns from Google Ads → PlacementLine. Returns count.

    Args:
        target_customer_id: Child account ID to query (for MCC access).
        login_customer_id: Manager account ID for auth header.
    """
    access_token = _ensure_fresh_token(account)
    query_cid = target_customer_id or account.customer_id

    query = """
        SELECT
            campaign.id,
            campaign.name,
            campaign.status,
            campaign.advertising_channel_type
        FROM campaign
        WHERE campaign.status != 'REMOVED'
        ORDER BY campaign.name
    """

    rows = _ads_rest_search(access_token, query_cid, query, login_customer_id=login_customer_id)
    parent_campaign = _get_or_create_campaign(account)

    count = 0
    for row in rows:
        camp = row.get("campaign", {})
        campaign_id = camp.get("id", "")
        if not campaign_id:
            continue

        external_ref = str(campaign_id)
        channel = _map_channel_type(camp.get("advertisingChannelType", ""))

        defaults = {
            "media_type": PlacementLine.MediaType.ONLINE,
            "media_channel": channel,
            "market": account.descriptive_name or account.customer_id,
            "channel": camp.get("name", ""),
            "property_text": f"Google Ads Campaign #{campaign_id}",
        }

        PlacementLine.objects.update_or_create(
            campaign=parent_campaign,
            external_ref=external_ref,
            defaults=defaults,
        )
        count += 1

    return count


def sync_metrics(
    account: GoogleAdsAccount,
    days: int = 30,
    target_customer_id: str | None = None,
    login_customer_id: str | None = None,
) -> int:
    """Sync daily metrics from Google Ads → PlacementDay. Returns count.

    Args:
        target_customer_id: Child account ID to query (for MCC access).
        login_customer_id: Manager account ID for auth header.
    """
    access_token = _ensure_fresh_token(account)
    parent_campaign = _get_or_create_campaign(account)
    query_cid = target_customer_id or account.customer_id

    start_date = (date.today() - timedelta(days=days)).strftime("%Y-%m-%d")
    end_date = date.today().strftime("%Y-%m-%d")

    query = f"""
        SELECT
            campaign.id,
            segments.date,
            metrics.impressions,
            metrics.clicks,
            metrics.cost_micros
        FROM campaign
        WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
          AND campaign.status != 'REMOVED'
    """

    rows = _ads_rest_search(access_token, query_cid, query, login_customer_id=login_customer_id)

    count = 0
    for row in rows:
        campaign_id = str(row.get("campaign", {}).get("id", ""))
        if not campaign_id:
            continue

        try:
            placement_line = PlacementLine.objects.get(
                campaign=parent_campaign,
                external_ref=campaign_id,
            )
        except PlacementLine.DoesNotExist:
            continue

        segments = row.get("segments", {})
        metrics = row.get("metrics", {})

        metric_date = segments.get("date", "")
        if not metric_date:
            continue

        cost_micros = int(metrics.get("costMicros", 0))
        cost_reais = cost_micros / 1_000_000

        PlacementDay.objects.update_or_create(
            placement_line=placement_line,
            date=metric_date,
            defaults={
                "impressions": int(metrics.get("impressions", 0)),
                "clicks": int(metrics.get("clicks", 0)),
                "cost": cost_reais,
            },
        )
        count += 1

    return count


def full_sync(account: GoogleAdsAccount, days: int = 30) -> SyncLog:
    """Run a full sync: campaigns + metrics. Returns the SyncLog entry.

    Automatically detects manager (MCC) accounts and syncs each child
    client account through the manager.
    """
    log = SyncLog.objects.create(account=account)
    try:
        access_token = _ensure_fresh_token(account)
        manager_id = account.customer_id

        # Try direct sync first
        try:
            campaigns_count = sync_campaigns(account)
            metrics_count = sync_metrics(account, days=days)
        except RuntimeError as e:
            if "REQUESTED_METRICS_FOR_MANAGER" not in str(e):
                raise
            # This is a Manager (MCC) account — sync child accounts
            logger.info(
                "Account %s is a Manager account. Listing child accounts...",
                manager_id,
            )
            child_accounts = list_client_accounts(access_token, manager_id)
            if not child_accounts:
                raise RuntimeError(
                    "Conta Manager (MCC) sem contas-filhas acessiveis. "
                    "Verifique as permissoes no Google Ads."
                ) from e

            campaigns_count = 0
            metrics_count = 0
            for child in child_accounts:
                child_id = child["id"]
                logger.info("Syncing child account %s (%s)", child_id, child["name"])
                campaigns_count += sync_campaigns(
                    account,
                    target_customer_id=child_id,
                    login_customer_id=manager_id,
                )
                metrics_count += sync_metrics(
                    account,
                    days=days,
                    target_customer_id=child_id,
                    login_customer_id=manager_id,
                )

        log.status = SyncLog.Status.SUCCESS
        log.campaigns_synced = campaigns_count
        log.metrics_synced = metrics_count
        log.finished_at = timezone.now()
        log.save()

        account.last_sync = timezone.now()
        account.save(update_fields=["last_sync", "updated_at"])
    except Exception as exc:
        logger.exception("Google Ads sync failed for account %s", account)
        log.status = SyncLog.Status.ERROR
        log.error_message = str(exc)[:2000]
        log.finished_at = timezone.now()
        log.save()
    return log
