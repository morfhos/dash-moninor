"""Reconcile Campaign.media_type and PlacementLine.media_type with reality.

The Campaign.media_type field and PlacementLine.media_type may drift from the
actual nature of the media (e.g. radio inserts saved as 'online') because of
old imports or manual edits made before the placement lines were synced.

This command applies three rules and reports/fixes inconsistencies:

1. Force PlacementLine.media_type based on its media_channel:
     radio / jornal / tv_aberta  -> offline
     google / search / youtube / display / meta / tiktok / linkedin /
       dv360* (any DV360 variant)               -> online

2. For lines with media_channel='other' (ambiguous), fall back to a
   broadcast-name whitelist (radio/TV stations, newspapers) that detects
   well-known offline media by substring patterns or explicit names.

3. After fixing the lines, recompute Campaign.media_type from the line counts:
     majority online -> 'online'
     majority offline -> 'offline'
     ties -> online
     no lines -> leave as-is

Google Ads / Meta Ads campaigns (whose names start with "Google Ads - " or
"Meta Ads - ") are always forced to 'online' regardless of placement lines,
since they may not have any PlacementLine attached at all.

Usage:
    python manage.py fix_campaign_media_type            # apply changes
    python manage.py fix_campaign_media_type --dry-run  # report only
    python manage.py fix_campaign_media_type --cliente-id=1
"""

import re
from collections import Counter

from django.core.management.base import BaseCommand
from django.db import transaction

from campaigns.models import Campaign, PlacementLine


# media_channel values that are intrinsically offline
OFFLINE_CHANNELS = {"radio", "jornal", "tv_aberta"}

# media_channel values that are intrinsically online
ONLINE_CHANNELS = {
    "google", "search", "youtube", "display",
    "meta", "tiktok", "linkedin",
    "dv360", "dv360_youtube", "dv360_spotify", "dv360_eletromid",
    "dv360_netflix", "dv360_globoplay", "dv360_admooh",
}

# ─────────────────────────────────────────────────────────────────────
# Broadcast whitelist — used to fix lines saved as media_channel='other'
# whose `channel` field actually points at a known offline broadcaster.
# ─────────────────────────────────────────────────────────────────────

# Substring patterns (already uppercased & cleaned). Match anywhere in the
# channel name. These are intentionally specific to avoid false positives.
OFFLINE_NAME_PATTERNS = [
    re.compile(r"\bFM\b"),                # Any "* FM" radio
    re.compile(r"\bAM\b"),                # AM radio
    re.compile(r"\bR[ÁA]DIO\b"),          # "RADIO X"
    re.compile(r"\bTV\b"),                # "TV X"
    re.compile(r"\bJORNAL\b"),
    re.compile(r"\bDI[ÁA]RIO\b"),         # "DIARIO DO ABC"
    re.compile(r"\bNEWS\b"),              # GLOBONEWS, BAND NEWS, RECORD NEWS
    re.compile(r"\bCNN\b"),
    re.compile(r"\bBANDEIRANTES\b"),
    re.compile(r"\bCULTURA\b"),
    re.compile(r"\bGLOBO\b"),
    re.compile(r"\bSBT\b"),
    re.compile(r"\bRECORD\b"),
    re.compile(r"\bGAZETA\b"),
    re.compile(r"\bREDE TV\b"),
    re.compile(r"\bJOVEM PAN\b"),
    re.compile(r"\bKISS\b"),
    re.compile(r"\bMASSA\b"),
    re.compile(r"\bMIX\b"),
    re.compile(r"\bCBN\b"),
    re.compile(r"\bALPHA\b"),
    re.compile(r"\bANTENA\b"),
    re.compile(r"\bDISNEY\b"),
    re.compile(r"\bROTATIVO\b"),
    re.compile(r"\bTRANSAM[EÉ]RICA\b"),
    re.compile(r"\bTRANSCONTINENTAL\b"),
    re.compile(r"\bNATIVA\b"),
    re.compile(r"\bNOVABRASIL\b"),
    re.compile(r"\bBAND\b"),
    re.compile(r"\bENERGIA\b"),
    re.compile(r"\bFRONTEIRA\b"),
    re.compile(r"\bCLUBE\b"),
    re.compile(r"\bCARAGUA\b"),
    re.compile(r"\bBEIRA MAR\b"),
    re.compile(r"\bFAIXA MUSICAL\b"),
    re.compile(r"\bVIVA ABC\b"),
    re.compile(r"\bIMPRENSA\b"),
    re.compile(r"\bCOMERCIO\b"),
]

# Explicit known broadcaster names that don't naturally match the patterns
# above (single-word names, abbreviations, region markers, etc).
# Add as you discover new ones during dry-runs.
OFFLINE_NAME_EXPLICIT = {
    # Radios
    "SANTA CECILIA",
    "B9 ROCK FM",
    "101 FM",
    "105 FM",
    "98,1",
    "98.1",
    "97 FM",
    "ROTATIVO",
    "CHANNEL",
    "CANAL ABC",
    # Compound TV broadcaster names (single-word, can't use \b boundary)
    "GLOBONEWS",
    "BANDNEWS",
    "RECORDNEWS",
    # Local TV affiliates / news shows / regional editions
    "SP1",       # TV Globo SP local news show
    "SP2",
    "10",        # ambiguous, seen as TV-affiliate marker
    "SANTOS",
    "CAMPINAS",
    "RIBEIRÃO PRETO",
    "RIBEIRAO PRETO",
    "SÃO JOSÉ DOS CAMPOS",
    "SAO JOSE DOS CAMPOS",
    "FRANCA",
}


def is_offline_broadcaster(channel_name: str) -> bool:
    """Return True if the channel name looks like an offline broadcaster
    (radio, TV station, newspaper) based on the whitelist patterns/names."""
    if not channel_name:
        return False
    norm = channel_name.upper().strip()
    if norm in OFFLINE_NAME_EXPLICIT:
        return True
    return any(p.search(norm) for p in OFFLINE_NAME_PATTERNS)


class Command(BaseCommand):
    help = "Reconcile Campaign.media_type and PlacementLine.media_type with reality."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only show what would change, don't write to the database.",
        )
        parser.add_argument(
            "--cliente-id",
            type=int,
            default=None,
            help="Restrict to campaigns of a single client.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        cliente_id = options["cliente_id"]

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — no changes will be persisted\n"))

        # ── Step 1a: fix PlacementLine.media_type by media_channel ──
        lines_qs = PlacementLine.objects.all()
        if cliente_id:
            lines_qs = lines_qs.filter(campaign__cliente_id=cliente_id)

        line_fix_count = 0
        line_fix_by_channel: Counter = Counter()
        # Track per-line fixes triggered by the broadcaster whitelist so we can
        # report them separately (these are the "subtle" catches).
        whitelist_hits: list[tuple[int, str]] = []  # (line_id, channel name)

        with transaction.atomic():
            # Lines that should be offline but aren't
            wrong_offline = lines_qs.filter(
                media_channel__in=OFFLINE_CHANNELS
            ).exclude(media_type="offline")
            for ch, n in Counter(
                wrong_offline.values_list("media_channel", flat=True)
            ).items():
                line_fix_by_channel[f"{ch} -> offline"] += n
            n_off = wrong_offline.count()
            if n_off and not dry_run:
                wrong_offline.update(media_type="offline")
            line_fix_count += n_off

            # Lines that should be online but aren't
            wrong_online = lines_qs.filter(
                media_channel__in=ONLINE_CHANNELS
            ).exclude(media_type="online")
            for ch, n in Counter(
                wrong_online.values_list("media_channel", flat=True)
            ).items():
                line_fix_by_channel[f"{ch} -> online"] += n
            n_on = wrong_online.count()
            if n_on and not dry_run:
                wrong_online.update(media_type="online")
            line_fix_count += n_on

            # ── Step 1b: whitelist fallback for media_channel='other' ──
            # Catches lines like SANTA CECILIA, GLOBONEWS, BAND NEWS that were
            # imported as 'other' but are clearly offline broadcasters.
            ambiguous = lines_qs.filter(media_channel="other").exclude(
                media_type="offline"
            ).exclude(channel__isnull=True).exclude(channel="")
            ids_to_fix: list[int] = []
            for line in ambiguous.only("id", "channel"):
                if is_offline_broadcaster(line.channel):
                    ids_to_fix.append(line.id)
                    whitelist_hits.append((line.id, line.channel))
            if ids_to_fix:
                line_fix_by_channel[f"other -> offline (whitelist)"] += len(ids_to_fix)
                line_fix_count += len(ids_to_fix)
                if not dry_run:
                    PlacementLine.objects.filter(id__in=ids_to_fix).update(
                        media_type="offline"
                    )

            if dry_run:
                # Roll back any inadvertent writes — we did update() outside,
                # but we keep the atomic block for consistency.
                transaction.set_rollback(True)

        self.stdout.write(self.style.HTTP_INFO(
            f"\n[1/2] PlacementLine fixes: {line_fix_count} lines"
        ))
        for desc, n in line_fix_by_channel.most_common():
            self.stdout.write(f"    {n:>5}  {desc}")

        if whitelist_hits:
            self.stdout.write(self.style.HTTP_INFO(
                f"\n      Whitelist matches ({len(whitelist_hits)} lines):"
            ))
            sample = Counter(name for _, name in whitelist_hits)
            for name, n in sample.most_common(20):
                self.stdout.write(f"        {n:>4}  {name}")

        # ── Step 2: recompute Campaign.media_type ──
        # We have to re-count after the line update above.
        campaigns_qs = Campaign.objects.all()
        if cliente_id:
            campaigns_qs = campaigns_qs.filter(cliente_id=cliente_id)

        camp_fixes: list[tuple[int, str, str, str]] = []  # (id, name, old, new)
        for c in campaigns_qs:
            is_google_meta = (
                c.name.startswith("Google Ads - ")
                or c.name.startswith("Meta Ads - ")
            )

            on_count = PlacementLine.objects.filter(
                campaign=c, media_type="online"
            ).count()
            off_count = PlacementLine.objects.filter(
                campaign=c, media_type="offline"
            ).count()

            if is_google_meta:
                new_type = "online"
            elif on_count == 0 and off_count == 0:
                continue  # no signal — leave as-is
            elif off_count > on_count:
                new_type = "offline"
            elif on_count > off_count:
                new_type = "online"
            else:
                new_type = "online"  # tie-breaker

            if c.media_type != new_type:
                camp_fixes.append((c.id, c.name, c.media_type, new_type))
                if not dry_run:
                    c.media_type = new_type
                    c.save(update_fields=["media_type"])

        self.stdout.write(self.style.HTTP_INFO(
            f"\n[2/2] Campaign.media_type fixes: {len(camp_fixes)} campaigns"
        ))
        for cid, name, old, new in camp_fixes:
            short = name if len(name) <= 60 else name[:57] + "..."
            self.stdout.write(f"    #{cid:<5} {short:<60} {old} -> {new}")

        # ── Summary ──
        self.stdout.write("")
        if dry_run:
            self.stdout.write(self.style.WARNING(
                f"DRY RUN summary — would fix {line_fix_count} lines and "
                f"{len(camp_fixes)} campaigns. Re-run without --dry-run to apply."
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"Done. Fixed {line_fix_count} placement lines and "
                f"{len(camp_fixes)} campaigns."
            ))
