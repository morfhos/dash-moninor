from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import os
from typing import Any, Iterable

from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.utils import timezone

from .models import (
    Campaign, CreativeAsset, FinancialSummary, FinancialUpload,
    MediaEfficiency, PIControl, Piece, PlacementCreative, PlacementDay,
    PlacementLine, RegionInvestment,
)


def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = (
        s.replace("á", "a")
        .replace("à", "a")
        .replace("â", "a")
        .replace("ã", "a")
        .replace("é", "e")
        .replace("ê", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ô", "o")
        .replace("õ", "o")
        .replace("ú", "u")
        .replace("ç", "c")
    )
    return s


def detect_media_from_sheet(sheet_name: str) -> tuple[str, str]:
    n = _norm(sheet_name)
    if "open tv" in n or "tv aberta" in n:
        return (PlacementLine.MediaType.OFFLINE, PlacementLine.MediaChannel.TV_ABERTA)
    if "paytv" in n or "pay tv" in n:
        return (PlacementLine.MediaType.OFFLINE, PlacementLine.MediaChannel.PAYTV)
    if "radio" in n:
        return (PlacementLine.MediaType.OFFLINE, PlacementLine.MediaChannel.RADIO)
    if "jornal" in n:
        return (PlacementLine.MediaType.OFFLINE, PlacementLine.MediaChannel.JORNAL)
    if "ooh" in n:
        return (PlacementLine.MediaType.OFFLINE, PlacementLine.MediaChannel.OOH)
    if "meta" in n:
        return (PlacementLine.MediaType.ONLINE, PlacementLine.MediaChannel.META)
    if "google" in n:
        return (PlacementLine.MediaType.ONLINE, PlacementLine.MediaChannel.GOOGLE)
    if "youtube" in n:
        return (PlacementLine.MediaType.ONLINE, PlacementLine.MediaChannel.YOUTUBE)
    if "display" in n:
        return (PlacementLine.MediaType.ONLINE, PlacementLine.MediaChannel.DISPLAY)
    if "search" in n:
        return (PlacementLine.MediaType.ONLINE, PlacementLine.MediaChannel.SEARCH)
    if "social" in n or "digital" in n:
        return (PlacementLine.MediaType.ONLINE, PlacementLine.MediaChannel.SOCIAL)
    return (PlacementLine.MediaType.ONLINE, PlacementLine.MediaChannel.OTHER)


def _try_parse_date(v: Any) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, str):
        s = v.strip()
        for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
            try:
                return datetime.strptime(s, fmt).date()
            except Exception:
                pass
    return None


def _try_parse_datetime(v: Any) -> datetime | None:
    if isinstance(v, datetime):
        return v
    if isinstance(v, date):
        return datetime(v.year, v.month, v.day)
    if isinstance(v, str):
        s = v.strip()
        for fmt in (
            "%d/%m/%Y %H:%M",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d",
            "%d/%m/%Y",
        ):
            try:
                return datetime.strptime(s, fmt)
            except Exception:
                pass
    return None


def _parse_int(v: Any) -> int | None:
    if v is None:
        return None
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int,)):
        return int(v)
    if isinstance(v, float):
        if v.is_integer():
            return int(v)
        return int(round(v))
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        s = s.replace(",", ".")
        try:
            f = float(s)
            return int(round(f))
        except Exception:
            return None
    return None


def _parse_decimal_str(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        s = s.replace(".", "").replace(",", ".") if re.search(r"\d+\.\d+,\d+", s) else s.replace(",", ".")
        return s
    return None


def _split_piece_codes(v: Any) -> list[str]:
    if v is None:
        return []
    s = str(v).strip()
    if not s:
        return []
    tokens = re.split(r"[^A-Za-z0-9]+", s)
    codes: list[str] = []
    for t in tokens:
        t = t.strip().upper()
        if not t:
            continue
        if len(t) > 12:
            continue
        codes.append(t)
    return sorted(set(codes))


@dataclass(frozen=True)
class ParsedPlacementRow:
    sheet: str
    media_type: str
    media_channel: str
    data: dict[str, Any]
    days: list[tuple[date, int]]
    piece_codes: list[str]


def parse_media_plan_xlsx(uploaded_file: UploadedFile) -> dict[str, Any]:
    errors: list[str] = []
    parsed_rows: list[ParsedPlacementRow] = []
    pieces: list[dict[str, Any]] = []

    temp_path = None
    source_path = getattr(uploaded_file, "path", None)
    if source_path:
        temp_path = source_path
    else:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
        temp_path = tmp.name
        for chunk in uploaded_file.chunks():
            tmp.write(chunk)
        tmp.close()

    try:
        backend_dir = getattr(settings, "BASE_DIR", None)
        if backend_dir is not None:
            backend_dir = str(backend_dir)
        else:
            backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        proc = subprocess.run(
            [sys.executable, "-m", "campaigns.xlsx_worker", temp_path],
            capture_output=True,
            text=True,
            check=False,
            cwd=backend_dir,
        )
        if proc.returncode != 0 or not proc.stdout:
            detail = (proc.stderr or "").strip()
            if detail:
                detail = detail.splitlines()[-1][:300]
                errors.append(f"Falha ao ler planilha .xlsx. Detalhe: {detail}")
            else:
                errors.append("Falha ao ler planilha .xlsx. Verifique a instalação do openpyxl.")
            return {"ok": False, "errors": errors, "sheets": [], "total_rows": 0, "detected": {}, "parsed_rows": []}

        data = json.loads(proc.stdout)
        detected = data.get("detected") or {}
        sheets = data.get("sheets") or []
        total_rows = int(data.get("total_rows") or 0)
        rows = data.get("rows") or []
        pieces = list(data.get("pieces") or [])

        for r in rows:
            start_dt = _try_parse_datetime(r.get("data", {}).get("start_date"))
            end_dt = _try_parse_datetime(r.get("data", {}).get("end_date"))
            days: list[tuple[date, int]] = []
            for d_iso, ins in r.get("days", []):
                d = _try_parse_date(d_iso)
                if d is None:
                    continue
                ins_i = _parse_int(ins) or 0
                if ins_i > 0:
                    days.append((d, ins_i))
            parsed_rows.append(
                ParsedPlacementRow(
                    sheet=str(r.get("sheet") or ""),
                    media_type=str(r.get("media_type") or ""),
                    media_channel=str(r.get("media_channel") or ""),
                    data={
                        **(r.get("data") or {}),
                        "start_date": start_dt,
                        "end_date": end_dt,
                    },
                    days=days,
                    piece_codes=list(r.get("piece_codes") or []),
                )
            )

        if not parsed_rows:
            errors.append("Nenhuma linha válida detectada no arquivo.")

        return {
            "ok": len(errors) == 0,
            "errors": errors,
            "sheets": sheets,
            "total_rows": total_rows,
            "detected": detected,
            "parsed_rows": parsed_rows,
            "pieces": pieces,
        }
    finally:
        if source_path is None and temp_path:
            try:
                os.unlink(temp_path)
            except Exception:
                pass


def import_media_plan_xlsx(*, campaign: Campaign, uploaded_file: UploadedFile, replace_existing: bool, selected_sheets: list[str] | None = None) -> dict[str, Any]:
    parsed = parse_media_plan_xlsx(uploaded_file)

    # Auto-detecção: se nenhuma linha tática foi encontrada, tenta formato de patrocínio
    if not parsed.get("parsed_rows"):
        uploaded_file.seek(0)
        return import_sponsorship_xlsx(campaign=campaign, uploaded_file=uploaded_file, replace_existing=replace_existing, selected_sheets=selected_sheets)

    if not parsed.get("ok"):
        return {"ok": False, "errors": parsed.get("errors", ["Falha ao ler planilha."])}

    parsed_rows: list[ParsedPlacementRow] = parsed.get("parsed_rows", [])

    # Filtra apenas as abas selecionadas pelo usuário
    if selected_sheets is not None:
        parsed_rows = [r for r in parsed_rows if r.sheet in selected_sheets]
        if not parsed_rows:
            return {"ok": False, "errors": ["Nenhuma linha válida nas abas selecionadas."]}
    pieces_table: list[dict[str, Any]] = parsed.get("pieces", [])

    created_lines = 0
    created_days = 0
    created_pieces = 0
    created_links = 0

    with transaction.atomic():
        if replace_existing:
            PlacementCreative.objects.filter(placement_line__campaign=campaign).delete()
            PlacementDay.objects.filter(placement_line__campaign=campaign).delete()
            PlacementLine.objects.filter(campaign=campaign).delete()

        pieces_by_code: dict[str, Piece] = {p.code.upper(): p for p in campaign.pieces.all()}

        for item in pieces_table:
            code = str(item.get("code") or "").strip().upper()
            if not code:
                continue
            title = str(item.get("title") or "").strip()
            dur = _parse_int(item.get("duration_sec"))
            existing = pieces_by_code.get(code)
            if existing is None:
                existing = Piece.objects.create(
                    campaign=campaign,
                    code=code,
                    title=title[:250] if title else f"Peça {code}",
                    duration_sec=max(0, int(dur or 0)),
                    type=Piece.Type.VIDEO,
                    status=Piece.Status.PENDING,
                )
                pieces_by_code[code] = existing
                created_pieces += 1
            else:
                update_fields = []
                if title and (existing.title.startswith("Peça ") or existing.title.strip() == existing.code):
                    existing.title = title[:250]
                    update_fields.append("title")
                if dur and not existing.duration_sec:
                    existing.duration_sec = max(0, int(dur))
                    update_fields.append("duration_sec")
                if update_fields:
                    existing.save(update_fields=update_fields)

        # Verificar se há linhas sem piece_codes - se sim, criar peças genéricas por canal
        lines_without_pieces = [r for r in parsed_rows if not r.piece_codes and r.days]
        if lines_without_pieces and not pieces_table:
            # Agrupar por media_channel para criar uma peça genérica por canal
            channels_seen: set[str] = set()
            for row in lines_without_pieces:
                channel_key = row.media_channel or "other"
                if channel_key not in channels_seen:
                    channels_seen.add(channel_key)
                    code = f"GEN_{channel_key.upper()}"
                    if code not in pieces_by_code:
                        channel_names = {
                            "radio": "Rádio",
                            "tv_aberta": "TV Aberta",
                            "paytv": "PayTV",
                            "jornal": "Jornal",
                            "ooh": "OOH",
                            "meta": "Meta",
                            "google": "Google",
                            "youtube": "YouTube",
                            "display": "Display",
                            "search": "Search",
                            "social": "Social",
                            "other": "Outros",
                        }
                        title = channel_names.get(channel_key, channel_key.title())
                        p = Piece.objects.create(
                            campaign=campaign,
                            code=code,
                            title=f"Veiculação {title}",
                            duration_sec=0,
                            type=Piece.Type.VIDEO,
                            status=Piece.Status.PENDING,
                        )
                        pieces_by_code[code] = p
                        created_pieces += 1

        for row in parsed_rows:
            # Para impressos (jornal/revista/impresso), inclui tiragem no property_text
            prop_text = str(row.data.get("property_text") or "")[:250]
            circulation = row.data.get("circulation")
            if circulation and row.media_channel in ("jornal", "revista", "impresso", "magazine"):
                circ_str = f"{circulation:,}".replace(",", ".")
                prop_text = f"Tiragem: {circ_str}" if not prop_text else f"{prop_text} | Tiragem: {circ_str}"
                prop_text = prop_text[:250]

            line = PlacementLine.objects.create(
                campaign=campaign,
                media_type=row.media_type,
                media_channel=row.media_channel,
                market=str(row.data.get("market") or "")[:100],
                channel=str(row.data.get("channel") or "")[:100],
                program=str(row.data.get("program") or "")[:150],
                property_text=prop_text,
                format_text=str(row.data.get("format_text") or "")[:250],
                duration_sec=row.data.get("duration_sec") or None,
                external_ref=str(row.data.get("external_ref") or "")[:120],
                start_date=row.data.get("start_date"),
                end_date=row.data.get("end_date"),
            )
            created_lines += 1

            for d, ins in row.days:
                PlacementDay.objects.create(placement_line=line, date=d, insertions=ins)
                created_days += 1

            # Se a linha tem piece_codes, vincular às peças correspondentes
            if row.piece_codes:
                for code in row.piece_codes:
                    p = pieces_by_code.get(code)
                    if p is None:
                        p = Piece.objects.create(
                            campaign=campaign,
                            code=code,
                            title=f"Peça {code}",
                            duration_sec=max(0, int(row.data.get("duration_sec") or 0)),
                            type=Piece.Type.VIDEO,
                            status=Piece.Status.PENDING,
                        )
                        pieces_by_code[code] = p
                        created_pieces += 1
                    PlacementCreative.objects.get_or_create(placement_line=line, piece=p)
                    created_links += 1
            elif row.days:
                # Se não tem piece_codes mas tem dias, vincular à peça genérica do canal
                channel_key = row.media_channel or "other"
                gen_code = f"GEN_{channel_key.upper()}"
                p = pieces_by_code.get(gen_code)
                if p is not None:
                    PlacementCreative.objects.get_or_create(placement_line=line, piece=p)
                    created_links += 1

    return {
        "ok": True,
        "created": {
            "placement_lines": created_lines,
            "placement_days": created_days,
            "pieces": created_pieces,
            "placement_creatives": created_links,
        },
    }


def parse_sponsorship_xlsx(uploaded_file: UploadedFile) -> dict[str, Any]:
    """Roda o sponsorship_xlsx_worker e retorna parsed_rows com custo/impressões."""
    errors: list[str] = []
    parsed_rows: list[ParsedPlacementRow] = []

    temp_path = None
    source_path = getattr(uploaded_file, "path", None)
    if source_path:
        temp_path = source_path
    else:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
        temp_path = tmp.name
        for chunk in uploaded_file.chunks():
            tmp.write(chunk)
        tmp.close()

    try:
        backend_dir = getattr(settings, "BASE_DIR", None)
        backend_dir = str(backend_dir) if backend_dir else os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

        proc = subprocess.run(
            [sys.executable, "-m", "campaigns.sponsorship_xlsx_worker", temp_path],
            capture_output=True,
            text=True,
            check=False,
            cwd=backend_dir,
        )
        if proc.returncode != 0 or not proc.stdout:
            detail = (proc.stderr or "").strip()
            if detail:
                detail = detail.splitlines()[-1][:300]
            errors.append(f"Falha ao ler planilha de patrocínio. Detalhe: {detail}")
            return {"ok": False, "errors": errors, "sheets": [], "total_rows": 0, "detected": {}, "parsed_rows": []}

        data = json.loads(proc.stdout)
        for r in data.get("rows") or []:
            start_dt = _try_parse_datetime(r.get("data", {}).get("start_date"))
            end_dt = _try_parse_datetime(r.get("data", {}).get("end_date"))
            days: list[tuple[date, int]] = []
            for entry in r.get("days", []):
                d_iso, ins = entry[0], entry[1]
                d = _try_parse_date(d_iso)
                ins_i = _parse_int(ins) or 0
                if d is not None and ins_i > 0:
                    days.append((d, ins_i))
            row_data = {**(r.get("data") or {}), "start_date": start_dt, "end_date": end_dt}
            parsed_rows.append(
                ParsedPlacementRow(
                    sheet=str(r.get("sheet") or ""),
                    media_type=str(r.get("media_type") or ""),
                    media_channel=str(r.get("media_channel") or ""),
                    data=row_data,
                    days=days,
                    piece_codes=list(r.get("piece_codes") or []),
                )
            )

        if not parsed_rows:
            errors.append("Nenhuma entrega de patrocínio detectada no arquivo.")

        return {
            "ok": len(errors) == 0,
            "errors": errors,
            "sheets": data.get("sheets", []),
            "total_rows": int(data.get("total_rows") or 0),
            "detected": data.get("detected") or {},
            "parsed_rows": parsed_rows,
            "pieces": [],
            "format": "sponsorship",
        }
    finally:
        if source_path is None and temp_path:
            try:
                os.unlink(temp_path)
            except Exception:
                pass


def import_sponsorship_xlsx(*, campaign: Campaign, uploaded_file: UploadedFile, replace_existing: bool, selected_sheets: list[str] | None = None) -> dict[str, Any]:
    """
    Importa planilha de patrocínio/proposta comercial.
    Mesma lógica de import_media_plan_xlsx, com suporte a cost e impressions por dia.
    """
    parsed = parse_sponsorship_xlsx(uploaded_file)
    if not parsed.get("ok"):
        return {"ok": False, "errors": parsed.get("errors", ["Falha ao ler planilha de patrocínio."])}

    parsed_rows: list[ParsedPlacementRow] = parsed.get("parsed_rows", [])

    if selected_sheets is not None:
        parsed_rows = [r for r in parsed_rows if r.sheet in selected_sheets]
        if not parsed_rows:
            return {"ok": False, "errors": ["Nenhuma linha válida nas abas selecionadas."]}

    created_lines = 0
    created_days = 0

    with transaction.atomic():
        if replace_existing:
            PlacementCreative.objects.filter(placement_line__campaign=campaign).delete()
            PlacementDay.objects.filter(placement_line__campaign=campaign).delete()
            PlacementLine.objects.filter(campaign=campaign).delete()

        for row in parsed_rows:
            line = PlacementLine.objects.create(
                campaign=campaign,
                media_type=row.media_type,
                media_channel=row.media_channel,
                market=str(row.data.get("market") or "")[:100],
                channel=str(row.data.get("channel") or "")[:100],
                program=str(row.data.get("program") or "")[:150],
                property_text=str(row.data.get("property_text") or "")[:250],
                format_text=str(row.data.get("format_text") or "")[:250],
                duration_sec=row.data.get("duration_sec") or None,
                external_ref=str(row.data.get("external_ref") or "")[:120],
                start_date=row.data.get("start_date"),
                end_date=row.data.get("end_date"),
            )
            created_lines += 1

            day_costs = row.data.get("day_costs") or []
            day_impressions = row.data.get("day_impressions") or []

            for i, (d, ins) in enumerate(row.days):
                cost = day_costs[i] if i < len(day_costs) else None
                impressions = day_impressions[i] if i < len(day_impressions) else None
                PlacementDay.objects.create(
                    placement_line=line,
                    date=d,
                    insertions=ins,
                    cost=cost if cost is not None else None,
                    impressions=impressions if impressions else None,
                )
                created_days += 1

    return {
        "ok": True,
        "format": "sponsorship",
        "created": {
            "placement_lines": created_lines,
            "placement_days": created_days,
            "pieces": 0,
            "placement_creatives": 0,
        },
    }


def compute_sha256(uploaded_file: UploadedFile) -> str:
    h = hashlib.sha256()
    for chunk in uploaded_file.chunks():
        h.update(chunk)
    return h.hexdigest()


def infer_piece_code_from_filename(filename: str) -> str | None:
    base = (filename or "").strip()
    if not base:
        return None
    m = re.match(r"^\s*([A-Za-z])\b", base)
    if not m:
        m = re.match(r"^\s*([A-Za-z])[-_ ]", base)
    if not m:
        return None
    return m.group(1).upper()


def infer_piece_type_from_filename(filename: str) -> str:
    n = _norm(filename)
    if n.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
        return Piece.Type.IMAGE
    if n.endswith((".mp3", ".wav", ".aac", ".m4a")):
        return Piece.Type.AUDIO
    if n.endswith((".zip", ".html", ".htm")):
        return Piece.Type.HTML5
    return Piece.Type.VIDEO


def try_ffprobe(path: str) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", path],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return {}
    if proc.returncode != 0 or not proc.stdout:
        return {}
    try:
        return json.loads(proc.stdout)
    except Exception:
        return {}


def extract_duration_sec_from_ffprobe(meta: dict[str, Any]) -> int | None:
    fmt = meta.get("format") or {}
    dur = fmt.get("duration")
    if dur is None:
        return None
    try:
        return max(0, int(round(float(dur))))
    except Exception:
        return None


def attach_assets_to_campaign(*, campaign: Campaign, files: Iterable[UploadedFile]) -> dict[str, Any]:
    created_pieces = 0
    created_assets = 0
    skipped_duplicates = 0

    pieces_by_code: dict[str, Piece] = {p.code.upper(): p for p in campaign.pieces.all()}

    with transaction.atomic():
        for f in files:
            code = infer_piece_code_from_filename(getattr(f, "name", ""))
            if not code:
                code = "X"
            piece = pieces_by_code.get(code)
            if piece is None:
                piece = Piece.objects.create(
                    campaign=campaign,
                    code=code,
                    title=(getattr(f, "name", "") or f"Peça {code}")[:250],
                    duration_sec=0,
                    type=infer_piece_type_from_filename(getattr(f, "name", "")),
                    status=Piece.Status.PENDING,
                )
                pieces_by_code[code] = piece
                created_pieces += 1

            checksum = compute_sha256(f)
            if checksum and CreativeAsset.objects.filter(piece=piece, checksum=checksum).exists():
                skipped_duplicates += 1
                continue

            asset = CreativeAsset.objects.create(
                piece=piece,
                file=f,
                checksum=checksum,
                metadata={
                    "original_name": getattr(f, "name", ""),
                    "content_type": getattr(f, "content_type", ""),
                    "size_bytes": getattr(f, "size", None),
                },
            )
            created_assets += 1

            meta = try_ffprobe(asset.file.path)
            if meta:
                merged = dict(asset.metadata or {})
                merged["ffprobe"] = meta
                dur = extract_duration_sec_from_ffprobe(meta)
                if dur is not None:
                    merged["duration_sec"] = dur
                    if piece.duration_sec == 0:
                        piece.duration_sec = dur
                        piece.save(update_fields=["duration_sec"])
                asset.metadata = merged
                asset.save(update_fields=["metadata"])

    return {"ok": True, "created_pieces": created_pieces, "created_assets": created_assets, "skipped_duplicates": skipped_duplicates}


# ── Financial integration ──────────────────────────────────────────────────────

def parse_financial_xlsx(uploaded_file) -> dict:
    """
    Run financial_xlsx_worker as subprocess, return parsed JSON dict.
    Works with FieldFile (from model) or UploadedFile (from form).
    """
    import tempfile, os

    # Write to temp file
    if hasattr(uploaded_file, "path"):
        path = uploaded_file.path
        tmp = None
    else:
        suffix = ".xlsx"
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        try:
            for chunk in uploaded_file.chunks():
                tmp.write(chunk)
        except AttributeError:
            uploaded_file.seek(0)
            tmp.write(uploaded_file.read())
        tmp.close()
        path = tmp.name

    try:
        result = subprocess.run(
            [sys.executable, "-m", "campaigns.financial_xlsx_worker", path],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            return {"ok": False, "errors": [result.stderr or "Worker exited with error"]}
        return json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        return {"ok": False, "errors": ["Timeout ao processar arquivo"]}
    except json.JSONDecodeError as e:
        return {"ok": False, "errors": [f"JSON inválido do worker: {e}"]}
    finally:
        if tmp:
            os.unlink(path)


@transaction.atomic
def import_financial_data(campaign: "Campaign", parsed: dict) -> dict:
    """
    Persist parsed financial data into DB:
      - FinancialSummary (upsert)
      - MediaEfficiency rows (replace all for campaign)
      - PIControl rows (replace all for campaign)
      - RegionInvestment.valor (update from resumo_meios)
    """
    from decimal import Decimal, InvalidOperation

    def _dec(v):
        if v is None:
            return None
        try:
            return Decimal(str(v))
        except InvalidOperation:
            return None

    summary_data = parsed.get("summary") or {}
    resumo_meios = parsed.get("resumo_meios") or {}
    pi_rows = parsed.get("pi_controls") or []
    eff_rows = parsed.get("media_efficiencies") or []

    # FinancialSummary upsert
    fs, _ = FinancialSummary.objects.get_or_create(campaign=campaign)
    fs.data_by_channel = resumo_meios
    fs.monthly_investment = summary_data.get("monthly_investment") or []
    fs.total_valor_tabela = _dec(summary_data.get("total_valor_tabela"))
    fs.total_valor_negociado = _dec(summary_data.get("total_valor_negociado"))
    fs.total_desembolso = _dec(summary_data.get("total_desembolso"))
    fs.desconto_pct = _dec(summary_data.get("desconto_pct"))
    fs.grp_pct = _dec(summary_data.get("grp_pct"))
    fs.cobertura_pct = _dec(summary_data.get("cobertura_pct"))
    fs.frequencia_eficaz = _dec(summary_data.get("frequencia_eficaz"))
    fs.save()

    # MediaEfficiency — replace all
    MediaEfficiency.objects.filter(campaign=campaign).delete()
    eff_objs = []
    for row in eff_rows:
        eff_objs.append(MediaEfficiency(
            campaign=campaign,
            channel_type=row.get("channel_type", ""),
            veiculo=row.get("veiculo") or "",
            programa=row.get("programa") or "",
            praca=row.get("praca") or "",
            insercoes=row.get("insercoes") or 0,
            trp=_dec(row.get("trp")),
            cpp=_dec(row.get("cpp")),
            custo_tabela=_dec(row.get("custo_tabela")),
            custo_negociado=_dec(row.get("custo_negociado")),
            impactos=row.get("impactos"),
            cpm=_dec(row.get("cpm")),
            ia_pct=_dec(row.get("ia_pct")),
            formato=row.get("formato") or "",
            circulacao=row.get("circulacao"),
            valor=_dec(row.get("valor")),
        ))
    MediaEfficiency.objects.bulk_create(eff_objs)

    # PIControl — replace all
    PIControl.objects.filter(campaign=campaign).delete()
    pi_objs = []
    for row in pi_rows:
        pi_objs.append(PIControl(
            campaign=campaign,
            pi_type=row.get("pi_type", "tv_aberta"),
            pi_numero=row.get("pi_numero") or "",
            produto=row.get("produto") or "",
            rede=row.get("rede") or "",
            praca=row.get("praca") or "",
            veiculacao_start=row.get("veiculacao_start"),
            veiculacao_end=row.get("veiculacao_end"),
            vencimento=row.get("vencimento"),
            insercoes=row.get("insercoes") or 0,
            valor_liquido=_dec(row.get("valor_liquido")),
            status=PIControl.Status.PENDENTE,
        ))
    PIControl.objects.bulk_create(pi_objs)

    # RegionInvestment — create/update from praça-aggregated data
    REGION_COLORS = [
        "#6366f1", "#f59e0b", "#22c55e", "#ef4444", "#3b82f6",
        "#a855f7", "#14b8a6", "#ec4899", "#84cc16", "#f97316",
    ]
    region_rows = parsed.get("region_investments") or []
    if region_rows:
        # Delete existing and recreate with real data
        RegionInvestment.objects.filter(campaign=campaign).delete()
        for idx, rdata in enumerate(region_rows):
            rname = rdata.get("region_name") or ""
            if not rname:
                continue
            RegionInvestment.objects.create(
                campaign=campaign,
                region_name=rname,
                valor=_dec(rdata.get("valor")),
                percentage=_dec(rdata.get("percentage")) or 0,
                order=idx,
                color=REGION_COLORS[idx % len(REGION_COLORS)],
            )

    return {
        "ok": True,
        "efficiencies_imported": len(eff_objs),
        "pi_controls_imported": len(pi_objs),
        "regions_imported": len(region_rows),
    }
