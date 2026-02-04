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

from .models import Campaign, CreativeAsset, Piece, PlacementCreative, PlacementDay, PlacementLine


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
        }
    finally:
        if source_path is None and temp_path:
            try:
                os.unlink(temp_path)
            except Exception:
                pass


def import_media_plan_xlsx(*, campaign: Campaign, uploaded_file: UploadedFile, replace_existing: bool) -> dict[str, Any]:
    parsed = parse_media_plan_xlsx(uploaded_file)
    if not parsed.get("ok"):
        return {"ok": False, "errors": parsed.get("errors", ["Falha ao ler planilha."])}

    parsed_rows: list[ParsedPlacementRow] = parsed.get("parsed_rows", [])

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

            for d, ins in row.days:
                PlacementDay.objects.create(placement_line=line, date=d, insertions=ins)
                created_days += 1

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

    return {
        "ok": True,
        "created": {
            "placement_lines": created_lines,
            "placement_days": created_days,
            "pieces": created_pieces,
            "placement_creatives": created_links,
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
