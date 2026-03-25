"""
AI-powered analytics service.

Builds a rich data briefing from the database, calls Anthropic's Claude API,
and returns structured JSON with insights, alerts, recommendations,
and executive summary. The LLM receives a pre-computed briefing, never raw SQL.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import date
from typing import Any, Optional

from django.core.cache import cache

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = "claude-sonnet-4-20250514"
CACHE_TTL = 3600  # 1 hour


def check_ai_status() -> dict:
    """
    Check if the AI service is active and reachable.
    Returns dict with: active (bool), status (str), model (str), has_key (bool)
    Cached for 5 minutes.
    """
    cached = cache.get("ai:status")
    if cached:
        return cached

    result = {
        "has_key": bool(ANTHROPIC_API_KEY),
        "active": False,
        "status": "inactive",
        "model": MODEL,
    }

    if not ANTHROPIC_API_KEY:
        result["status"] = "no_key"
        cache.set("ai:status", result, timeout=60)
        return result

    try:
        client = _get_client()
        # Minimal API call to verify connectivity
        msg = client.messages.create(
            model=MODEL,
            max_tokens=10,
            messages=[{"role": "user", "content": "ping"}],
        )
        result["active"] = True
        result["status"] = "active"
        cache.set("ai:status", result, timeout=300)  # 5 min
    except Exception as e:
        result["status"] = f"error: {str(e)[:80]}"
        cache.set("ai:status", result, timeout=60)

    return result


def _get_client():
    """Lazy-load the Anthropic client."""
    import anthropic
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def _build_cache_key(prefix: str, cliente_id: int, date_from: str, date_to: str, data_hash: str) -> str:
    return f"ai:{prefix}:{cliente_id}:{date_from}:{date_to}:{data_hash}"


def _data_fingerprint(context: dict) -> str:
    """Short hash of numeric values to detect when data changed."""
    key_fields = ["total_imp", "total_clk", "total_cost", "global_ctr", "cpm"]
    raw = "|".join(str(context.get(k, "")) for k in key_fields)
    return hashlib.md5(raw.encode()).hexdigest()[:8]


def build_deep_briefing(cliente_id: int, date_from: str = "", date_to: str = "") -> dict:
    """
    Query the database to build a comprehensive data briefing for the AI.
    Returns a dict with all relevant metrics, campaign details, trends,
    financial data, and region investments — ready for the LLM prompt.
    """
    from collections import defaultdict
    from datetime import timedelta
    from django.db.models import Sum, Count, Min, Max, Avg, F, Q
    from campaigns.models import (
        Campaign, PlacementLine, PlacementDay, RegionInvestment,
        FinancialSummary, MediaEfficiency, PIControl,
    )
    from accounts.models import Cliente

    cliente = Cliente.objects.filter(id=cliente_id).first()
    if not cliente:
        return {}

    briefing: dict[str, Any] = {
        "cliente": cliente.nome,
        "date_from": date_from,
        "date_to": date_to,
    }

    # ── All campaigns for this client ─────────────────────────────
    campaigns = Campaign.objects.filter(cliente_id=cliente_id)
    campaign_list = []
    for c in campaigns.select_related("cliente")[:20]:
        campaign_list.append({
            "id": c.id,
            "name": c.name,
            "status": c.status,
            "media_type": c.media_type,
            "start": str(c.start_date.date()) if c.start_date else "",
            "end": str(c.end_date.date()) if c.end_date else "",
            "budget": float(c.total_budget or 0),
        })
    briefing["campaigns"] = campaign_list
    briefing["total_campaigns"] = campaigns.count()
    briefing["active_campaigns"] = campaigns.filter(status="active").count()

    # ── Digital performance (PlacementDay) ────────────────────────
    google_channels = ["google", "youtube", "display", "search"]
    meta_channels = ["meta"]
    all_digital = google_channels + meta_channels

    lines = PlacementLine.objects.filter(
        campaign__cliente_id=cliente_id,
        media_channel__in=all_digital,
    )
    line_ids = list(lines.values_list("id", flat=True))

    days_qs = PlacementDay.objects.filter(placement_line_id__in=line_ids)
    if date_from:
        days_qs = days_qs.filter(date__gte=date_from)
    if date_to:
        days_qs = days_qs.filter(date__lte=date_to)

    totals = days_qs.aggregate(
        imp=Sum("impressions"), clk=Sum("clicks"), cost=Sum("cost"),
    )
    total_imp = totals["imp"] or 0
    total_clk = totals["clk"] or 0
    total_cost = float(totals["cost"] or 0)

    briefing["digital"] = {
        "impressions": total_imp,
        "clicks": total_clk,
        "cost": round(total_cost, 2),
        "ctr": round((total_clk / total_imp * 100), 2) if total_imp > 0 else 0,
        "cpc": round((total_cost / total_clk), 2) if total_clk > 0 else 0,
        "cpm": round((total_cost / total_imp * 1000), 2) if total_imp > 0 else 0,
    }

    # Per-platform breakdown
    for label, channels in [("google", google_channels), ("meta", meta_channels)]:
        ch_ids = list(lines.filter(media_channel__in=channels).values_list("id", flat=True))
        if ch_ids:
            ch = days_qs.filter(placement_line_id__in=ch_ids).aggregate(
                imp=Sum("impressions"), clk=Sum("clicks"), cost=Sum("cost"),
            )
            ch_imp = ch["imp"] or 0
            ch_clk = ch["clk"] or 0
            ch_cost = float(ch["cost"] or 0)
            briefing[f"platform_{label}"] = {
                "impressions": ch_imp,
                "clicks": ch_clk,
                "cost": round(ch_cost, 2),
                "ctr": round((ch_clk / ch_imp * 100), 2) if ch_imp > 0 else 0,
                "cpc": round((ch_cost / ch_clk), 2) if ch_clk > 0 else 0,
            }

    # ── Daily trend (last 30 days) ────────────────────────────────
    daily = list(
        days_qs.values("date")
        .annotate(imp=Sum("impressions"), clk=Sum("clicks"), cost=Sum("cost"))
        .order_by("-date")[:30]
    )
    if daily:
        briefing["daily_trend"] = [
            {"date": str(d["date"]), "imp": d["imp"] or 0, "clk": d["clk"] or 0, "cost": float(d["cost"] or 0)}
            for d in reversed(daily)
        ]

    # ── Per-campaign performance ──────────────────────────────────
    camp_perf = []
    for camp in campaigns[:15]:
        camp_lines = list(PlacementLine.objects.filter(
            campaign=camp, media_channel__in=all_digital,
        ).values_list("id", flat=True))
        if not camp_lines:
            continue
        cp = days_qs.filter(placement_line_id__in=camp_lines).aggregate(
            imp=Sum("impressions"), clk=Sum("clicks"), cost=Sum("cost"),
        )
        cp_imp = cp["imp"] or 0
        cp_clk = cp["clk"] or 0
        cp_cost = float(cp["cost"] or 0)
        if cp_imp == 0 and cp_clk == 0:
            continue
        camp_perf.append({
            "name": camp.name,
            "impressions": cp_imp,
            "clicks": cp_clk,
            "cost": round(cp_cost, 2),
            "ctr": round((cp_clk / cp_imp * 100), 2) if cp_imp > 0 else 0,
            "cpc": round((cp_cost / cp_clk), 2) if cp_clk > 0 else 0,
        })
    if camp_perf:
        briefing["campaign_performance"] = camp_perf

    # ── Offline media (PlacementLine without digital channels) ────
    offline_lines = PlacementLine.objects.filter(
        campaign__cliente_id=cliente_id,
    ).exclude(media_channel__in=all_digital)

    offline_agg = offline_lines.aggregate(
        total_lines=Count("id"),
        total_insertions=Sum("days__insertions"),
    )
    if offline_agg["total_lines"]:
        # Group by channel
        by_channel = list(
            offline_lines.values("media_channel")
            .annotate(
                lines=Count("id"),
                insertions=Sum("days__insertions"),
            )
            .order_by("-insertions")[:10]
        )
        briefing["offline_media"] = {
            "total_lines": offline_agg["total_lines"],
            "total_insertions": offline_agg["total_insertions"] or 0,
            "by_channel": [
                {"channel": c["media_channel"], "lines": c["lines"], "insertions": c["insertions"] or 0}
                for c in by_channel
            ],
        }

    # ── Financial data ────────────────────────────────────────────
    financial_data = []
    for camp in campaigns[:10]:
        try:
            fs = camp.financial_summary
            financial_data.append({
                "campaign": camp.name,
                "valor_tabela": float(fs.total_valor_tabela or 0),
                "valor_negociado": float(fs.total_valor_negociado or 0),
                "desembolso": float(fs.total_desembolso or 0),
                "desconto_pct": float(fs.desconto_pct or 0),
            })
        except Exception:
            pass
    if financial_data:
        briefing["financial"] = financial_data

    # ── Region investments ────────────────────────────────────────
    regions = list(
        RegionInvestment.objects.filter(campaign__cliente_id=cliente_id)
        .values("region_name")
        .annotate(total_pct=Sum("percentage"), total_valor=Sum("valor"))
        .order_by("-total_pct")[:10]
    )
    if regions:
        briefing["regions"] = [
            {"name": r["region_name"], "pct": float(r["total_pct"] or 0), "valor": float(r["total_valor"] or 0)}
            for r in regions
        ]

    # ── PI Control (upcoming due dates) ───────────────────────────
    from datetime import date as date_cls
    today = date_cls.today()
    pis_pending = PIControl.objects.filter(
        campaign__cliente_id=cliente_id,
        status="pendente",
    ).order_by("vencimento")[:10]
    if pis_pending.exists():
        briefing["pis_pending"] = [
            {
                "pi": pi.pi_numero, "rede": pi.rede, "praca": pi.praca,
                "vencimento": str(pi.vencimento) if pi.vencimento else "",
                "valor": float(pi.valor_liquido or 0),
                "days_until": (pi.vencimento - today).days if pi.vencimento else None,
            }
            for pi in pis_pending
        ]

    return briefing


def _safe_json_parse(text: str) -> Optional[dict]:
    """Extract JSON from LLM response, handling markdown fences."""
    text = text.strip()
    if text.startswith("```"):
        # Remove ```json ... ```
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Failed to parse AI response as JSON: %s...", text[:200])
        return None


# ── Generate Insights ─────────────────────────────────────────────────────────

INSIGHTS_PROMPT = """Você é um analista sênior de mídia digital em uma agência brasileira.
Analise os dados abaixo do período de campanhas digitais e retorne APENAS JSON válido (sem markdown, sem texto extra) com a seguinte estrutura:

{{
  "executive_summary": "Resumo executivo de 2-3 frases sobre o período",
  "insights": [
    {{
      "title": "Título curto",
      "text": "Explicação com números reais dos dados",
      "type": "positive|negative|warning|info",
      "icon": "trending-up|trending-down|bar-chart|dollar-sign|alert-triangle|pie-chart"
    }}
  ],
  "alerts": [
    {{
      "title": "Título do alerta",
      "text": "Descrição detalhada",
      "severity": "critical|warning|info",
      "impact_pct": 15,
      "icon": "trending-down|alert-triangle|clock"
    }}
  ],
  "recommendations": [
    {{
      "title": "Ação recomendada",
      "text": "Descrição da ação",
      "priority": "high|medium|low",
      "impact": 20,
      "confidence": 85,
      "action": "Texto do botão de ação",
      "icon": "refresh-cw|pause-circle|zap|image|maximize"
    }}
  ]
}}

DADOS DO PERÍODO:
{data}

BENCHMARKS DE MERCADO:
CTR: {bench_ctr}%
CPC: R$ {bench_cpc}
CPM: R$ {bench_cpm}

Os dados podem incluir:
- digital: métricas globais (impressões, cliques, CTR, CPC, CPM, custo)
- platform_google / platform_meta: breakdown por plataforma
- campaign_performance: métricas por campanha individual
- daily_trend: tendência diária dos últimos 30 dias
- offline_media: mídia offline (TV, rádio, jornal) com inserções
- financial: dados financeiros (valor tabela, negociado, desembolso, desconto)
- regions: investimento por praça/região
- pis_pending: PIs pendentes com datas de vencimento
- historical: comparação com período anterior

Regras importantes:
- Gere entre 4-8 insights, 2-5 alertas, 3-5 recomendações
- Seja específico: cite valores reais, nomes de campanhas, praças
- NÃO invente dados. Use apenas o que foi fornecido
- Cruze informações: se uma campanha tem CTR alto mas custo alto, mencione
- Se houver PIs vencendo, alerte sobre vencimentos próximos
- Se houver dados financeiros, compare tabela vs negociado
- Se houver tendência diária, identifique padrões (queda, pico, estabilidade)
- Priorize ações concretas e mensuráveis nas recomendações
- Para impact_pct e impact, use números realistas (5-30)
- Para confidence, use 60-95
- Responda APENAS com JSON válido, sem nenhum texto adicional"""


def generate_analytics_insights(context: dict, cliente_id: int = 0) -> Optional[dict]:
    """
    Generate AI-powered insights from pre-computed analytics data.

    Args:
        context: dict with total_imp, total_clk, global_ctr, cpc, cpm,
                 total_cost, benchmarks, efficiency_matrix, historical, etc.
        cliente_id: for cache key

    Returns:
        dict with insights, alerts, recommendations, executive_summary
        or None on failure
    """
    if not ANTHROPIC_API_KEY:
        logger.info("ANTHROPIC_API_KEY not set, skipping AI insights")
        return None

    date_from = context.get("date_from", "")
    date_to = context.get("date_to", "")
    fingerprint = _data_fingerprint(context)
    cache_key = _build_cache_key("insights", cliente_id, date_from, date_to, fingerprint)

    cached = cache.get(cache_key)
    if cached:
        logger.debug("AI insights cache hit: %s", cache_key)
        return cached

    # Build comprehensive briefing from DB when cliente_id is available
    if cliente_id:
        try:
            deep = build_deep_briefing(cliente_id, date_from, date_to)
            # Merge view-computed data that the deep briefing may not have
            for k in ["benchmarks", "efficiency_matrix", "historical", "perf_score"]:
                if k in context and k not in deep:
                    deep[k] = context[k]
            safe_context = deep
        except Exception:
            logger.exception("build_deep_briefing failed, using view context")
            safe_context = {}
    else:
        safe_context = {}

    # Fallback: use view-provided context for fields not in deep briefing
    if not safe_context:
        for k in ["total_imp", "total_clk", "global_ctr", "cpc", "cpm", "total_cost",
                   "date_from", "date_to", "benchmarks", "active_campaigns"]:
            if k in context:
                safe_context[k] = context[k]

    # Always ensure benchmarks + efficiency matrix from view
    if "efficiency_matrix" in context and "efficiency_matrix" not in safe_context:
        safe_context["efficiency_matrix"] = [
            {k: v for k, v in ch.items() if k in
             ("channel", "impressions", "clicks", "ctr", "cpc", "cpm", "roi", "score")}
            for ch in context["efficiency_matrix"]
        ]

    if "historical" in context and "historical" not in safe_context:
        hist = context["historical"]
        if isinstance(hist, dict) and hist.get("has_prev"):
            safe_context["historical"] = {
                k: hist[k] for k in ("ctr", "cpc", "impressions", "clicks", "investment")
                if k in hist
            }

    for platform in ("google", "meta"):
        key = f"platform_{platform}"
        if key not in safe_context and platform in context and isinstance(context[platform], dict):
            safe_context[key] = context[platform]

    benchmarks = safe_context.get("benchmarks", context.get("benchmarks", {}))

    prompt = INSIGHTS_PROMPT.format(
        data=json.dumps(safe_context, ensure_ascii=False, default=str),
        bench_ctr=benchmarks.get("ctr", 2.0),
        bench_cpc=benchmarks.get("cpc", 1.50),
        bench_cpm=benchmarks.get("cpm", 15.00),
    )

    try:
        client = _get_client()
        message = client.messages.create(
            model=MODEL,
            max_tokens=2500,
            messages=[{"role": "user", "content": prompt}],
        )
        result = _safe_json_parse(message.content[0].text)
        if result:
            cache.set(cache_key, result, timeout=CACHE_TTL)
            logger.info("AI insights generated and cached for cliente=%s", cliente_id)
        return result
    except Exception:
        logger.exception("Failed to generate AI insights")
        return None


# ── Persist Insights to DB ────────────────────────────────────────────────────

def persist_ai_insights(cliente_id: int, date_from: str, date_to: str, ai_result: dict) -> int:
    """
    Save AI-generated insights to the AIInsight model.
    Returns count of records created.
    """
    from accounts.models import AIInsight

    try:
        d_from = date.fromisoformat(date_from) if date_from else date.today()
        d_to = date.fromisoformat(date_to) if date_to else date.today()
    except ValueError:
        d_from = d_to = date.today()

    # Clear old AI insights for this period
    AIInsight.objects.filter(
        cliente_id=cliente_id, date_from=d_from, date_to=d_to
    ).delete()

    records = []

    # Insights
    for item in ai_result.get("insights", []):
        records.append(AIInsight(
            cliente_id=cliente_id,
            date_from=d_from,
            date_to=d_to,
            insight_type=AIInsight.InsightType.INSIGHT,
            severity=item.get("type", "info"),
            title=item.get("title", "")[:300],
            text=item.get("text", ""),
            metadata={"icon": item.get("icon", ""), "type": item.get("type", "info")},
        ))

    # Alerts
    for item in ai_result.get("alerts", []):
        records.append(AIInsight(
            cliente_id=cliente_id,
            date_from=d_from,
            date_to=d_to,
            insight_type=AIInsight.InsightType.ALERT,
            severity=item.get("severity", "info"),
            title=item.get("title", "")[:300],
            text=item.get("text", ""),
            metadata={
                "icon": item.get("icon", ""),
                "impact_pct": item.get("impact_pct"),
                "impact_window": item.get("impact_window", "7"),
            },
        ))

    # Recommendations
    for item in ai_result.get("recommendations", []):
        records.append(AIInsight(
            cliente_id=cliente_id,
            date_from=d_from,
            date_to=d_to,
            insight_type=AIInsight.InsightType.RECOMMENDATION,
            severity=item.get("priority", "medium"),
            title=item.get("title", "")[:300],
            text=item.get("text", ""),
            metadata={
                "icon": item.get("icon", ""),
                "priority": item.get("priority", "medium"),
                "impact": item.get("impact"),
                "confidence": item.get("confidence"),
                "action": item.get("action", ""),
            },
        ))

    # Executive summary
    summary = ai_result.get("executive_summary", "")
    if summary:
        records.append(AIInsight(
            cliente_id=cliente_id,
            date_from=d_from,
            date_to=d_to,
            insight_type=AIInsight.InsightType.SUMMARY,
            title="Resumo Executivo",
            text=summary,
        ))

    if records:
        AIInsight.objects.bulk_create(records)

    return len(records)


# ── Executive Report ──────────────────────────────────────────────────────────

REPORT_PROMPT = """Gere um relatório executivo de performance de mídia digital em português brasileiro.

DADOS DO PERÍODO:
{data}

BENCHMARKS DE MERCADO:
CTR: {bench_ctr}% | CPC: R$ {bench_cpc} | CPM: R$ {bench_cpm}

Formato do relatório (use markdown):

## Resumo Executivo
3 frases objetivas sobre o desempenho geral.

## Destaques Positivos
- Liste os pontos fortes com números

## Pontos de Atenção
- Liste riscos e métricas abaixo do benchmark

## Recomendações Priorizadas
1. Alta prioridade: ...
2. Média prioridade: ...
3. ...

## Próximos Passos
- Ações imediatas (próximos 7 dias)
- Ações de médio prazo (próximos 30 dias)

Tom: profissional, direto, orientado a ação. Cite números reais dos dados."""


def generate_executive_report(context: dict, cliente_id: int = 0) -> Optional[str]:
    """Generate a markdown executive report from analytics data."""
    if not ANTHROPIC_API_KEY:
        return None

    fingerprint = _data_fingerprint(context)
    cache_key = _build_cache_key("report", cliente_id,
                                  context.get("date_from", ""), context.get("date_to", ""),
                                  fingerprint)

    cached = cache.get(cache_key)
    if cached:
        return cached

    # Use deep briefing from DB when possible
    date_from = context.get("date_from", "")
    date_to = context.get("date_to", "")
    if cliente_id:
        try:
            safe_context = build_deep_briefing(cliente_id, date_from, date_to)
        except Exception:
            safe_context = {}
    else:
        safe_context = {}

    if not safe_context:
        for k in ["total_imp", "total_clk", "global_ctr", "cpc", "cpm", "total_cost",
                   "date_from", "date_to", "active_campaigns"]:
            if k in context:
                safe_context[k] = context[k]
        for platform in ("google", "meta"):
            if platform in context and isinstance(context[platform], dict):
                safe_context[platform] = context[platform]

    benchmarks = context.get("benchmarks", safe_context.get("benchmarks", {}))

    prompt = REPORT_PROMPT.format(
        data=json.dumps(safe_context, ensure_ascii=False, default=str),
        bench_ctr=benchmarks.get("ctr", 2.0),
        bench_cpc=benchmarks.get("cpc", 1.50),
        bench_cpm=benchmarks.get("cpm", 15.00),
    )

    try:
        client = _get_client()
        message = client.messages.create(
            model=MODEL,
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}],
        )
        report = message.content[0].text
        cache.set(cache_key, report, timeout=CACHE_TTL)
        return report
    except Exception:
        logger.exception("Failed to generate executive report")
        return None
