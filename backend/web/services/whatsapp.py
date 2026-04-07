"""
WhatsApp Business API integration for sending periodic reports.

Supports multiple providers via WHATSAPP_PROVIDER env var:
  - "zapi"   → Z-API (Brazilian provider, cheapest)
  - "meta"   → Meta Cloud API (official)
  - "twilio" → Twilio
  - "log"    → Just log to console (dev/testing)

Required env vars per provider:
  Z-API:   ZAPI_INSTANCE_ID, ZAPI_TOKEN
  Meta:    META_WA_PHONE_ID, META_WA_TOKEN
  Twilio:  TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WA_FROM
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Optional
from urllib import request as urllib_request
from urllib.error import URLError

logger = logging.getLogger(__name__)

PROVIDER = os.environ.get("WHATSAPP_PROVIDER", "log").lower()


def _normalize_phone(phone: str) -> str:
    """Normalize phone to 55XXXXXXXXXXX format."""
    digits = re.sub(r"\D", "", phone)
    if not digits.startswith("55") and len(digits) <= 11:
        digits = "55" + digits
    return digits


def _send_zapi(phone: str, text: str) -> dict:
    instance = os.environ.get("ZAPI_INSTANCE_ID", "")
    token = os.environ.get("ZAPI_TOKEN", "")
    client_token = os.environ.get("ZAPI_CLIENT_TOKEN", token)
    if not instance or not token:
        return {"ok": False, "error": "ZAPI_INSTANCE_ID/ZAPI_TOKEN not set"}

    url = f"https://api.z-api.io/instances/{instance}/token/{token}/send-text"
    payload = json.dumps({"phone": phone, "message": text}).encode()
    req = urllib_request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Client-Token", client_token)
    try:
        with urllib_request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read())
            if body.get("error"):
                return {"ok": False, "error": body.get("message", body.get("error")), "response": body}
            return {"ok": True, "response": body, "provider": "zapi"}
    except URLError as e:
        error_body = ""
        if hasattr(e, "read"):
            try:
                error_body = e.read().decode()
            except Exception:
                pass
        return {"ok": False, "error": f"{e}: {error_body}"}


def _send_meta(phone: str, text: str) -> dict:
    phone_id = os.environ.get("META_WA_PHONE_ID", "")
    token = os.environ.get("META_WA_TOKEN", "")
    if not phone_id or not token:
        return {"ok": False, "error": "META_WA_PHONE_ID/META_WA_TOKEN not set"}

    url = f"https://graph.facebook.com/v22.0/{phone_id}/messages"
    payload = json.dumps({
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "text",
        "text": {"body": text},
    }).encode()
    req = urllib_request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib_request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read())
            return {"ok": True, "response": body}
    except URLError as e:
        return {"ok": False, "error": str(e)}


def _send_twilio(phone: str, text: str) -> dict:
    sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
    auth = os.environ.get("TWILIO_AUTH_TOKEN", "")
    from_num = os.environ.get("TWILIO_WA_FROM", "")
    if not sid or not auth or not from_num:
        return {"ok": False, "error": "TWILIO env vars not set"}

    import base64
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    data = f"To=whatsapp%3A%2B{phone}&From=whatsapp%3A%2B{from_num}&Body={urllib_request.quote(text)}".encode()
    req = urllib_request.Request(url, data=data, method="POST")
    cred = base64.b64encode(f"{sid}:{auth}".encode()).decode()
    req.add_header("Authorization", f"Basic {cred}")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib_request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read())
            return {"ok": True, "response": body}
    except URLError as e:
        return {"ok": False, "error": str(e)}


def send_whatsapp(phone: str, text: str) -> dict:
    """
    Send a WhatsApp message to the given phone number.
    Returns {"ok": True/False, ...}
    """
    normalized = _normalize_phone(phone)
    if len(normalized) < 12:
        return {"ok": False, "error": f"Invalid phone: {phone}"}

    logger.info("WhatsApp [%s] → %s (%d chars)", PROVIDER, normalized, len(text))

    if PROVIDER == "zapi":
        return _send_zapi(normalized, text)
    elif PROVIDER == "meta":
        return _send_meta(normalized, text)
    elif PROVIDER == "twilio":
        return _send_twilio(normalized, text)
    else:
        # Log mode (dev)
        logger.info("WhatsApp message to %s:\n%s", normalized, text)
        print(f"\n{'='*50}")
        print(f"📱 WhatsApp → {normalized}")
        print(f"{'='*50}")
        print(text)
        print(f"{'='*50}\n")
        return {"ok": True, "provider": "log"}


def build_report_message(
    cliente_nome: str,
    total_imp: int,
    total_clk: int,
    global_ctr: float,
    global_cpc: float,
    cpm: float,
    total_cost: float,
    ai_summary: str = "",
    ai_recommendation: str = "",
    bench_ctr: float = 2.0,
    bench_cpc: float = 3.50,
) -> str:
    """Build a compact WhatsApp report message (< 1024 chars)."""

    # CTR status
    ctr_emoji = "✅" if global_ctr >= bench_ctr else "⚠️"
    ctr_pct = round(((global_ctr - bench_ctr) / bench_ctr) * 100) if bench_ctr > 0 else 0
    ctr_dir = f"↑{abs(ctr_pct)}% do benchmark" if ctr_pct >= 0 else f"↓{abs(ctr_pct)}% do benchmark"

    # CPC status
    cpc_emoji = "✅" if global_cpc <= bench_cpc else "⚠️"
    cpc_pct = round(((bench_cpc - global_cpc) / bench_cpc) * 100) if bench_cpc > 0 else 0
    cpc_dir = f"↓{abs(cpc_pct)}% do mercado" if cpc_pct >= 0 else f"↑{abs(cpc_pct)}% acima"

    lines = [
        f"📊 *Relatório {cliente_nome}*",
        "",
        f"{ctr_emoji} CTR {global_ctr}% ({ctr_dir})",
        f"{cpc_emoji} CPC R$ {global_cpc:.2f} ({cpc_dir})",
        f"📈 CPM R$ {cpm:.2f}",
        "",
        f"💰 Investido: R$ {total_cost:,.2f}".replace(",", "."),
        f"👁 {total_imp:,} impressões · {total_clk:,} cliques".replace(",", "."),
    ]

    if ai_summary:
        # Truncate to keep under limit
        summary = ai_summary[:200].rstrip()
        if len(ai_summary) > 200:
            summary += "..."
        lines.append("")
        lines.append(f"🤖 {summary}")

    if ai_recommendation:
        rec = ai_recommendation[:150].rstrip()
        if len(ai_recommendation) > 150:
            rec += "..."
        lines.append("")
        lines.append(f"🎯 {rec}")

    lines.append("")
    lines.append("— _Oracli AI · BBRO &co._")

    return "\n".join(lines)
