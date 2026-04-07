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
from campaigns.models import Campaign, CreativeAsset, Piece, PlacementCreative, PlacementLine, PlacementDay

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


def sync_ad_groups(
    account: GoogleAdsAccount,
    days: int = 30,
    target_customer_id: str | None = None,
    login_customer_id: str | None = None,
) -> int:
    """Sync ad groups from Google Ads → AdGroup + AdGroupDay. Returns count."""
    from campaigns.models import AdGroup, AdGroupDay

    access_token = _ensure_fresh_token(account)
    parent_campaign = _get_or_create_campaign(account)
    query_cid = target_customer_id or account.customer_id

    start_date = (date.today() - timedelta(days=days)).strftime("%Y-%m-%d")
    end_date = date.today().strftime("%Y-%m-%d")

    query = f"""
        SELECT
            campaign.id,
            ad_group.id,
            ad_group.name,
            ad_group.status,
            segments.date,
            metrics.impressions,
            metrics.clicks,
            metrics.cost_micros
        FROM ad_group
        WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
          AND campaign.status != 'REMOVED'
          AND ad_group.status != 'REMOVED'
    """

    rows = _ads_rest_search(access_token, query_cid, query, login_customer_id=login_customer_id)

    count = 0
    for row in rows:
        campaign_id = str(row.get("campaign", {}).get("id", ""))
        ag = row.get("adGroup", {})
        ag_id = str(ag.get("id", ""))
        if not campaign_id or not ag_id:
            continue

        try:
            placement_line = PlacementLine.objects.get(
                campaign=parent_campaign, external_ref=campaign_id,
            )
        except PlacementLine.DoesNotExist:
            continue

        status_map = {"ENABLED": "enabled", "PAUSED": "paused", "REMOVED": "removed"}

        ad_group_obj, _ = AdGroup.objects.update_or_create(
            placement_line=placement_line,
            external_ref=ag_id,
            defaults={
                "name": ag.get("name", ""),
                "platform": "google",
                "status": status_map.get(ag.get("status", ""), "enabled"),
            },
        )

        seg_date = row.get("segments", {}).get("date", "")
        metrics = row.get("metrics", {})
        if seg_date:
            cost_micros = int(metrics.get("costMicros", 0))
            AdGroupDay.objects.update_or_create(
                ad_group=ad_group_obj,
                date=seg_date,
                defaults={
                    "impressions": int(metrics.get("impressions", 0)),
                    "clicks": int(metrics.get("clicks", 0)),
                    "cost": cost_micros / 1_000_000,
                },
            )
            count += 1

    return count


def sync_ads(
    account: GoogleAdsAccount,
    days: int = 30,
    target_customer_id: str | None = None,
    login_customer_id: str | None = None,
) -> int:
    """Sync individual ads from Google Ads → Ad + AdDay. Returns count."""
    from campaigns.models import AdGroup, Ad, AdDay

    access_token = _ensure_fresh_token(account)
    parent_campaign = _get_or_create_campaign(account)
    query_cid = target_customer_id or account.customer_id

    start_date = (date.today() - timedelta(days=days)).strftime("%Y-%m-%d")
    end_date = date.today().strftime("%Y-%m-%d")

    query = f"""
        SELECT
            campaign.id,
            ad_group.id,
            ad_group_ad.ad.id,
            ad_group_ad.ad.name,
            ad_group_ad.ad.type,
            ad_group_ad.ad.final_urls,
            ad_group_ad.status,
            segments.date,
            metrics.impressions,
            metrics.clicks,
            metrics.cost_micros
        FROM ad_group_ad
        WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
          AND campaign.status != 'REMOVED'
          AND ad_group.status != 'REMOVED'
          AND ad_group_ad.status != 'REMOVED'
    """

    rows = _ads_rest_search(access_token, query_cid, query, login_customer_id=login_customer_id)

    # Map ad types
    ad_type_map = {
        "RESPONSIVE_SEARCH_AD": "responsive_search",
        "RESPONSIVE_DISPLAY_AD": "responsive_display",
        "VIDEO_AD": "video",
        "IMAGE_AD": "image",
        "SHOPPING_PRODUCT_AD": "shopping",
        "APP_AD": "app",
        "TEXT_AD": "text",
        "EXPANDED_TEXT_AD": "text",
    }
    status_map = {"ENABLED": "enabled", "PAUSED": "paused", "REMOVED": "removed"}

    count = 0
    for row in rows:
        campaign_id = str(row.get("campaign", {}).get("id", ""))
        ag_id = str(row.get("adGroup", {}).get("id", ""))
        ad_data = row.get("adGroupAd", {}).get("ad", {})
        ad_id = str(ad_data.get("id", ""))
        if not campaign_id or not ag_id or not ad_id:
            continue

        try:
            placement_line = PlacementLine.objects.get(
                campaign=parent_campaign, external_ref=campaign_id,
            )
        except PlacementLine.DoesNotExist:
            continue

        # Find or skip ad_group
        try:
            ad_group_obj = AdGroup.objects.get(
                placement_line=placement_line, external_ref=ag_id,
            )
        except AdGroup.DoesNotExist:
            continue

        final_urls = ad_data.get("finalUrls", [])
        final_url = final_urls[0] if final_urls else ""
        raw_type = ad_data.get("type", "")

        ad_obj, _ = Ad.objects.update_or_create(
            ad_group=ad_group_obj,
            external_ref=ad_id,
            defaults={
                "name": ad_data.get("name", ""),
                "headline": ad_data.get("name", "")[:250],
                "final_url": final_url[:500] if final_url else "",
                "ad_type": ad_type_map.get(raw_type, "other"),
                "platform": "google",
                "status": status_map.get(
                    row.get("adGroupAd", {}).get("status", ""), "enabled"
                ),
            },
        )

        seg_date = row.get("segments", {}).get("date", "")
        metrics = row.get("metrics", {})
        if seg_date:
            cost_micros = int(metrics.get("costMicros", 0))
            AdDay.objects.update_or_create(
                ad=ad_obj,
                date=seg_date,
                defaults={
                    "impressions": int(metrics.get("impressions", 0)),
                    "clicks": int(metrics.get("clicks", 0)),
                    "cost": cost_micros / 1_000_000,
                },
            )
            count += 1

    return count


def sync_creatives(
    account: GoogleAdsAccount,
    target_customer_id: str | None = None,
    login_customer_id: str | None = None,
) -> int:
    """Sync creative assets from Google Ads → Piece + CreativeAsset.

    Queries the ad_group_ad_asset_view to discover image/video assets
    associated with ads (especially Display campaigns), then creates
    Piece and CreativeAsset records linked to the parent Campaign.

    Returns count of assets synced.
    """
    import hashlib
    import os
    import tempfile
    from django.core.files.base import ContentFile

    access_token = _ensure_fresh_token(account)
    parent_campaign = _get_or_create_campaign(account)
    query_cid = target_customer_id or account.customer_id

    # Step 1: Get all ad-level creative info (headlines, images, video)
    # Using ad_group_ad_asset_view which links ads to their assets
    query = """
        SELECT
            campaign.id,
            campaign.name,
            campaign.advertising_channel_type,
            ad_group.id,
            ad_group_ad.ad.id,
            ad_group_ad.ad.name,
            ad_group_ad.ad.type,
            ad_group_ad_asset_view.field_type,
            asset.id,
            asset.name,
            asset.type,
            asset.image_asset.full_size.url,
            asset.image_asset.full_size.width_pixels,
            asset.image_asset.full_size.height_pixels,
            asset.image_asset.file_size,
            asset.youtube_video_asset.youtube_video_id,
            asset.youtube_video_asset.youtube_video_title
        FROM ad_group_ad_asset_view
        WHERE campaign.status != 'REMOVED'
          AND ad_group_ad.status != 'REMOVED'
          AND ad_group_ad_asset_view.enabled = true
    """

    try:
        rows = _ads_rest_search(access_token, query_cid, query, login_customer_id=login_customer_id)
    except RuntimeError as e:
        logger.warning("Creative sync query failed: %s", e)
        return 0

    count = 0
    seen_assets = set()  # avoid duplicates

    for row in rows:
        campaign_id = str(row.get("campaign", {}).get("id", ""))
        ad_data = row.get("adGroupAd", {}).get("ad", {})
        ad_id = str(ad_data.get("id", ""))
        asset_data = row.get("asset", {})
        asset_id = str(asset_data.get("id", ""))
        asset_view = row.get("adGroupAdAssetView", {})
        field_type = asset_view.get("fieldType", "")
        asset_type = asset_data.get("type", "")

        if not campaign_id or not asset_id:
            continue

        # Only process image and video assets
        if asset_type not in ("IMAGE", "YOUTUBE_VIDEO"):
            continue

        # Skip if already processed this asset for this campaign
        dedup_key = f"{campaign_id}:{asset_id}"
        if dedup_key in seen_assets:
            continue
        seen_assets.add(dedup_key)

        # Find the PlacementLine for this campaign
        try:
            placement_line = PlacementLine.objects.get(
                campaign=parent_campaign, external_ref=campaign_id,
            )
        except PlacementLine.DoesNotExist:
            continue

        # Determine piece type and metadata
        asset_name = asset_data.get("name", "") or f"Asset #{asset_id}"
        ad_name = ad_data.get("name", "") or ""
        ad_type_raw = ad_data.get("type", "")

        if asset_type == "IMAGE":
            piece_type = Piece.Type.IMAGE
            image_asset = asset_data.get("imageAsset", {})
            full_size = image_asset.get("fullSize", {})
            image_url = full_size.get("url", "")
            width = full_size.get("widthPixels", 0)
            height = full_size.get("heightPixels", 0)
            file_size = image_asset.get("fileSize", 0)

            title = asset_name[:250]
            if width and height:
                title = f"{asset_name[:200]} ({width}x{height})"

            metadata = {
                "google_asset_id": asset_id,
                "google_ad_id": ad_id,
                "google_campaign_id": campaign_id,
                "field_type": field_type,
                "ad_type": ad_type_raw,
                "width": width,
                "height": height,
                "file_size": file_size,
                "source": "google_ads_sync",
            }
        elif asset_type == "YOUTUBE_VIDEO":
            piece_type = Piece.Type.VIDEO
            yt = asset_data.get("youtubeVideoAsset", {})
            video_id = yt.get("youtubeVideoId", "")
            video_title = yt.get("youtubeVideoTitle", "")
            image_url = f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg" if video_id else ""

            title = (video_title or asset_name)[:250]

            metadata = {
                "google_asset_id": asset_id,
                "google_ad_id": ad_id,
                "google_campaign_id": campaign_id,
                "field_type": field_type,
                "ad_type": ad_type_raw,
                "youtube_video_id": video_id,
                "source": "google_ads_sync",
            }
        else:
            continue

        # Create or update Piece
        piece_code = f"GA{asset_id}"[:20]
        piece, created = Piece.objects.update_or_create(
            campaign=parent_campaign,
            code=piece_code,
            defaults={
                "title": title,
                "duration_sec": 0,
                "type": piece_type,
                "status": Piece.Status.APPROVED,
                "notes": f"Importado do Google Ads. Ad: {ad_name}. Campo: {field_type}",
            },
        )

        # Link Piece to PlacementLine
        PlacementCreative.objects.get_or_create(
            placement_line=placement_line,
            piece=piece,
        )

        # Download image and create CreativeAsset (if we have a URL)
        if image_url and not CreativeAsset.objects.filter(
            piece=piece, metadata__google_asset_id=asset_id,
        ).exists():
            try:
                req = urllib.request.Request(image_url, method="GET")
                req.add_header("User-Agent", "DashMonitor/1.0")
                with urllib.request.urlopen(req, timeout=30) as resp:
                    img_data = resp.read()
                    content_type = resp.headers.get("Content-Type", "image/jpeg")

                # Determine file extension
                ext_map = {
                    "image/jpeg": ".jpg",
                    "image/png": ".png",
                    "image/gif": ".gif",
                    "image/webp": ".webp",
                }
                ext = ext_map.get(content_type.split(";")[0].strip(), ".jpg")
                checksum = hashlib.md5(img_data).hexdigest()
                filename = f"gads_{asset_id}{ext}"

                creative_asset = CreativeAsset(
                    piece=piece,
                    preview_url=image_url,
                    checksum=checksum,
                    metadata=metadata,
                )
                creative_asset.file.save(filename, ContentFile(img_data), save=True)
                count += 1
                logger.info(
                    "Synced creative asset: %s (%s) for campaign %s",
                    asset_name, field_type, campaign_id,
                )
            except Exception as e:
                logger.warning("Failed to download asset %s: %s", asset_id, e)
                # Still create the asset record with just the URL
                CreativeAsset.objects.create(
                    piece=piece,
                    preview_url=image_url,
                    metadata=metadata,
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
            # Sync ad groups, ads, and creatives
            try:
                sync_ad_groups(account, days=days)
                sync_ads(account, days=days)
            except Exception:
                logger.warning("Ad group/ad sync failed (non-fatal)", exc_info=True)
            try:
                sync_creatives(account)
            except Exception:
                logger.warning("Creative sync failed (non-fatal)", exc_info=True)
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
                # Sync ad groups, ads, and creatives for child accounts
                try:
                    sync_ad_groups(account, days=days, target_customer_id=child_id, login_customer_id=manager_id)
                    sync_ads(account, days=days, target_customer_id=child_id, login_customer_id=manager_id)
                except Exception:
                    logger.warning("Ad group/ad sync failed for child %s (non-fatal)", child_id, exc_info=True)
                try:
                    sync_creatives(account, target_customer_id=child_id, login_customer_id=manager_id)
                except Exception:
                    logger.warning("Creative sync failed for child %s (non-fatal)", child_id, exc_info=True)

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
