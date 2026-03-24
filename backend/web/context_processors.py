import re

from accounts.models import Alert, Cliente

from .authz import effective_cliente_id, effective_role, is_admin


def _build_breadcrumbs(request):
    """Build breadcrumb trail from the current URL path + resolved view kwargs."""
    from django.urls import resolve, reverse, Resolver404
    from campaigns.models import Campaign

    path = request.path
    if not request.user.is_authenticated or path in ("/", "/login/", "/logout/"):
        return []

    crumbs = [{"label": "Home", "url": "/dashboard/"}]

    try:
        match = resolve(path)
    except Resolver404:
        return crumbs

    name = match.url_name or ""
    kwargs = match.kwargs or {}

    # ── Helper to get campaign + cliente ─────────────────────────
    campaign = None
    cliente = None
    campaign_id = kwargs.get("campaign_id")
    cliente_id = kwargs.get("cliente_id")
    piece_id = kwargs.get("piece_id")

    if campaign_id:
        campaign = Campaign.objects.filter(id=campaign_id).select_related("cliente").first()
        if campaign:
            cliente = campaign.cliente

    if not cliente and cliente_id:
        cliente = Cliente.objects.filter(id=cliente_id).first()

    if not campaign and piece_id:
        from campaigns.models import Piece
        piece = Piece.objects.filter(id=piece_id).select_related("campaign__cliente").first()
        if piece:
            campaign = piece.campaign
            cliente = campaign.cliente

    # ── Dashboard ────────────────────────────────────────────────
    if name == "dashboard":
        crumbs.append({"label": "Dashboard", "url": ""})
        return crumbs

    # ── Analytics ────────────────────────────────────────────────
    if name == "analytics":
        crumbs.append({"label": "Analytics", "url": ""})
        return crumbs

    if name == "dashon":
        crumbs.append({"label": "DashON", "url": ""})
        return crumbs

    # ── Timeline ─────────────────────────────────────────────────
    if name == "timeline_campanhas":
        crumbs.append({"label": "Timeline Campanhas", "url": ""})
        return crumbs

    # ── Campanhas ────────────────────────────────────────────────
    if name in ("grupo_campanhas", "campanhas"):
        crumbs.append({"label": "Campanhas", "url": ""})
        return crumbs

    if name == "campanhas_cliente":
        crumbs.append({"label": "Campanhas", "url": "/campanhas/"})
        if cliente:
            crumbs.append({"label": cliente.nome, "url": ""})
        return crumbs

    if name == "cliente_campaigns":
        crumbs.append({"label": "Clientes", "url": "/clientes/"})
        if cliente:
            crumbs.append({"label": cliente.nome, "url": ""})
        return crumbs

    # ── Contract wizard / done ──────────────────────────────────
    if name == "contract_wizard_step1":
        crumbs.append({"label": "Clientes", "url": "/clientes/"})
        if cliente:
            crumbs.append({"label": cliente.nome, "url": f"/clientes/{cliente.id}/"})
        crumbs.append({"label": "Nova Campanha", "url": ""})
        return crumbs

    if name == "contract_wizard_step2":
        crumbs.append({"label": "Campanhas", "url": "/campanhas/"})
        if cliente:
            crumbs.append({"label": cliente.nome, "url": f"/campanhas/{cliente.id}/"})
        if campaign:
            crumbs.append({"label": "Upload Plano", "url": ""})
        return crumbs

    if name == "contract_done":
        crumbs.append({"label": "Campanhas", "url": "/campanhas/"})
        if cliente:
            crumbs.append({"label": cliente.nome, "url": f"/campanhas/{cliente.id}/"})
        if campaign:
            crumbs.append({"label": campaign.name, "url": ""})
        return crumbs

    # ── Media plan upload ────────────────────────────────────────
    if name == "campaign_media_plan_upload":
        crumbs.append({"label": "Campanhas", "url": "/campanhas/"})
        if cliente:
            crumbs.append({"label": cliente.nome, "url": f"/campanhas/{cliente.id}/"})
        if campaign:
            crumbs.append({"label": campaign.name, "url": f"/contratos/upload/{campaign.id}/concluido/"})
            crumbs.append({"label": "Upload Mídia", "url": ""})
        return crumbs

    # ── Financeiro ───────────────────────────────────────────────
    if name in ("campaign_financeiro", "campaign_financial_upload", "campaign_financial_delete"):
        crumbs.append({"label": "Campanhas", "url": "/campanhas/"})
        if cliente:
            crumbs.append({"label": cliente.nome, "url": f"/campanhas/{cliente.id}/"})
        if campaign:
            crumbs.append({"label": campaign.name, "url": f"/contratos/upload/{campaign.id}/concluido/"})
            if name == "campaign_financeiro":
                crumbs.append({"label": "Financeiro", "url": ""})
            elif name == "campaign_financial_upload":
                crumbs.append({"label": "Financeiro", "url": f"/campanhas/{campaign.id}/financeiro/"})
                crumbs.append({"label": "Upload", "url": ""})
            else:
                crumbs.append({"label": "Financeiro", "url": f"/campanhas/{campaign.id}/financeiro/"})
                crumbs.append({"label": "Deletar", "url": ""})
        return crumbs

    # ── Campanha detalhe (peças) ─────────────────────────────────
    if name == "campanha_detalhe":
        crumbs.append({"label": "Peças & Criativos", "url": "/pecas-criativos/"})
        if cliente:
            crumbs.append({"label": cliente.nome, "url": f"/pecas-criativos/{cliente.id}/"})
        if campaign:
            crumbs.append({"label": campaign.name, "url": ""})
        return crumbs

    # ── Peça detalhe ─────────────────────────────────────────────
    if name == "peca_detalhe":
        crumbs.append({"label": "Peças & Criativos", "url": "/pecas-criativos/"})
        if cliente:
            crumbs.append({"label": cliente.nome, "url": f"/pecas-criativos/{cliente.id}/"})
        if campaign:
            crumbs.append({"label": campaign.name, "url": f"/campanhas/{campaign.id}/detalhe/"})
        if piece_id:
            from campaigns.models import Piece
            p = Piece.objects.filter(id=piece_id).only("title").first()
            if p:
                crumbs.append({"label": p.title, "url": ""})
        return crumbs

    # ── Vinculação ───────────────────────────────────────────────
    if name == "campaign_link_matrix":
        crumbs.append({"label": "Campanhas", "url": "/campanhas/"})
        if campaign:
            crumbs.append({"label": campaign.name, "url": f"/contratos/upload/{campaign.id}/concluido/"})
            crumbs.append({"label": "Vinculação", "url": ""})
        return crumbs

    # ── Clientes ─────────────────────────────────────────────────
    if name == "clientes":
        crumbs.append({"label": "Clientes", "url": ""})
        return crumbs

    if name == "clientes_detail":
        crumbs.append({"label": "Clientes", "url": "/clientes/"})
        if cliente:
            crumbs.append({"label": cliente.nome, "url": ""})
        return crumbs

    if name == "clientes_edit":
        crumbs.append({"label": "Clientes", "url": "/clientes/"})
        if cliente:
            crumbs.append({"label": cliente.nome, "url": f"/clientes/{cliente.id}/"})
        crumbs.append({"label": "Editar", "url": ""})
        return crumbs

    if name == "clientes_create":
        crumbs.append({"label": "Clientes", "url": "/clientes/"})
        crumbs.append({"label": "Novo Cliente", "url": ""})
        return crumbs

    # ── Peças & Criativos top-level ──────────────────────────────
    if name == "pecas_criativos":
        crumbs.append({"label": "Peças & Criativos", "url": ""})
        return crumbs

    if name == "pecas_campanhas":
        crumbs.append({"label": "Peças & Criativos", "url": "/pecas-criativos/"})
        if cliente:
            crumbs.append({"label": cliente.nome, "url": ""})
        return crumbs

    # ── Veiculação ───────────────────────────────────────────────
    if name in ("veiculacao", "veiculacao_google"):
        crumbs.append({"label": "Veiculação Digital", "url": ""})
        crumbs.append({"label": "Google Ads", "url": ""})
        return crumbs

    if name == "veiculacao_meta":
        crumbs.append({"label": "Veiculação Digital", "url": ""})
        crumbs.append({"label": "Meta Ads", "url": ""})
        return crumbs

    # ── Relatórios ───────────────────────────────────────────────
    if name in ("relatorios", "relatorios_clientes", "relatorios_campanhas", "relatorios_consolidado"):
        crumbs.append({"label": "Relatórios", "url": ""})
        return crumbs

    # ── Integrações ──────────────────────────────────────────────
    if name == "integracoes":
        crumbs.append({"label": "Integrações", "url": ""})
        return crumbs

    # ── Configurações ────────────────────────────────────────────
    if name == "configuracoes":
        crumbs.append({"label": "Configurações", "url": ""})
        tab = request.GET.get("tab")
        TAB_LABELS = {
            "empresa": "Empresa", "usuarios": "Usuários", "metricas": "Métricas",
            "alertas": "Alertas", "financeiro": "Financeiro", "estrutura": "Estrutura",
            "ia": "IA", "seguranca": "Segurança",
        }
        if tab and tab in TAB_LABELS:
            crumbs[-1]["url"] = "/configuracoes/"
            crumbs.append({"label": TAB_LABELS[tab], "url": ""})
        return crumbs

    # ── Logs ─────────────────────────────────────────────────────
    if name == "logs_auditoria":
        crumbs.append({"label": "Logs & Auditoria", "url": ""})
        return crumbs

    # ── Alertas ──────────────────────────────────────────────────
    if name == "administracao":
        crumbs.append({"label": "Alertas", "url": ""})
        return crumbs

    # ── Perfil ───────────────────────────────────────────────────
    if name == "user_profile":
        crumbs.append({"label": "Meu Perfil", "url": ""})
        return crumbs

    # ── Uploads ──────────────────────────────────────────────────
    if name in ("uploads_planilhas", "uploads_midia_clientes"):
        crumbs.append({"label": "Upload de Mídia", "url": ""})
        return crumbs

    if name == "uploads_midia_campanhas":
        crumbs.append({"label": "Upload de Mídia", "url": "/uploads-midia/"})
        if cliente:
            crumbs.append({"label": cliente.nome, "url": ""})
        return crumbs

    if name == "uploads_midia_pecas":
        crumbs.append({"label": "Upload de Mídia", "url": "/uploads-midia/"})
        if campaign:
            crumbs.append({"label": campaign.name, "url": ""})
        return crumbs

    # Fallback: just page_title if available
    return crumbs


def nav_context(request):
    cliente_id = effective_cliente_id(request)
    nav_cliente = None
    if cliente_id:
        nav_cliente = (
            Cliente.objects.filter(id=cliente_id)
            .only("id", "nome", "logo")
            .first()
        )
        if is_admin(request.user) and nav_cliente is None:
            request.session.pop("impersonate_cliente_id", None)
            cliente_id = effective_cliente_id(request)
            if cliente_id:
                nav_cliente = (
                    Cliente.objects.filter(id=cliente_id)
                    .only("id", "nome", "logo")
                    .first()
                )

    role = effective_role(request)
    nav_mode = "cliente" if role == "cliente" else "admin"
    impersonating_cliente = nav_cliente if is_admin(request.user) and request.session.get("impersonate_cliente_id") else None

    # Verificar se o usuário é realmente admin (não colaborador)
    user_role = getattr(request.user, "role", "") if request.user.is_authenticated else ""
    is_true_admin = request.user.is_authenticated and (request.user.is_superuser or user_role == "admin")

    # Contar alertas não lidos para o cliente
    alertas_nao_lidos = 0
    alertas_pendentes = []
    if cliente_id and request.user.is_authenticated:
        alertas_pendentes = list(
            Alert.objects.filter(cliente_id=cliente_id, lido=False)
            .order_by("-criado_em")
            .values("id", "titulo", "mensagem", "prioridade", "criado_em")[:10]
        )
        alertas_nao_lidos = len(alertas_pendentes)

    # Sidebar client selector (admin-only, not impersonating)
    sidebar_clientes = []
    sidebar_selected_cliente_id = None
    if (
        request.user.is_authenticated
        and is_admin(request.user)
        and not request.session.get("impersonate_cliente_id")
    ):
        sidebar_clientes = list(
            Cliente.objects.filter(ativo=True)
            .order_by("nome")
            .values("id", "nome")
        )
        sidebar_selected_cliente_id = request.session.get("selected_cliente_id")
        if sidebar_selected_cliente_id:
            if not any(c["id"] == sidebar_selected_cliente_id for c in sidebar_clientes):
                request.session.pop("selected_cliente_id", None)
                sidebar_selected_cliente_id = None

    # Site logo from SiteConfig
    site_logo_url = None
    try:
        from accounts.models import SiteConfig
        site_cfg = SiteConfig.objects.filter(pk=1).only("logo").first()
        if site_cfg and site_cfg.logo:
            site_logo_url = site_cfg.logo.url
    except Exception:
        pass

    # Breadcrumbs based on URL path
    breadcrumbs = _build_breadcrumbs(request)

    return {
        "nav_mode": nav_mode,
        "nav_cliente": nav_cliente,
        "impersonating_cliente": impersonating_cliente,
        "is_true_admin": is_true_admin,
        "alertas_nao_lidos": alertas_nao_lidos,
        "alertas_pendentes": alertas_pendentes,
        "sidebar_clientes": sidebar_clientes,
        "sidebar_selected_cliente_id": sidebar_selected_cliente_id,
        "site_logo_url": site_logo_url,
        "breadcrumbs": breadcrumbs,
    }
