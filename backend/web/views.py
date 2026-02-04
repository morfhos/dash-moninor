from accounts.models import Cliente

from campaigns.models import Campaign, ContractUpload, MediaPlanUpload, PlacementCreative, PlacementDay, PlacementLine
from campaigns.services import import_media_plan_xlsx, attach_assets_to_campaign, parse_media_plan_xlsx
from django.contrib.auth import get_user_model
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.db import models
from django.db.models import Count, Max, Min, Sum
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
import json

from .authz import effective_cliente_id, effective_role, is_admin, require_admin
from .forms import (
    CampaignEditForm,
    CampaignWizardForm,
    ClienteForm,
    ClienteUserCreateForm,
    ContractUploadForm,
    LoginForm,
    MediaPlanUploadForm,
)


def root(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        if effective_role(request) == "cliente":
            return redirect("web:dashboard")
        return redirect("web:administracao")
    return redirect("web:login")


def login_view(request: HttpRequest) -> HttpResponse:
    next_url = request.GET.get("next") or request.POST.get("next") or ""
    if request.user.is_authenticated:
        return redirect(next_url or ("web:dashboard" if effective_role(request) == "cliente" else "web:administracao"))

    form_errors = ""
    login_value = ""
    remember = True

    if request.method == "POST":
        form = LoginForm(request.POST)
        if form.is_valid():
            login_value = form.cleaned_data["login"]
            password = form.cleaned_data["password"]
            remember = bool(form.cleaned_data.get("remember"))

            user = authenticate(request, username=login_value, password=password)
            if user is None:
                User = get_user_model()
                by_email = User.objects.filter(email__iexact=login_value).only("username").first()
                if by_email is not None:
                    user = authenticate(request, username=by_email.username, password=password)
            if user is None:
                form_errors = "Login/e-mail ou senha inválidos."
            else:
                auth_login(request, user)
                if not remember:
                    request.session.set_expiry(0)
                if effective_role(request) == "cliente":
                    return redirect(next_url or "web:dashboard")
                return redirect(next_url or "web:administracao")
        else:
            login_value = request.POST.get("login", "")
            remember = bool(request.POST.get("remember"))
            form_errors = "Preencha os campos corretamente."

    return render(
        request,
        "web/login.html",
        {
            "page_title": "Login",
            "form_errors": form_errors,
            "next": next_url,
            "login_value": login_value,
            "remember": remember,
        },
    )


def logout_view(request: HttpRequest) -> HttpResponse:
    request.session.pop("impersonate_cliente_id", None)
    auth_logout(request)
    return redirect("web:login")


def _render_module(request: HttpRequest, *, active: str, title: str) -> HttpResponse:
    role = effective_role(request)
    if role == "cliente":
        allowed = {"dashboard", "timeline_campanhas", "relatorios", "analytics"}
        if active not in allowed:
            return redirect("web:dashboard")
    return render(
        request,
        "web/module_page.html",
        {
            "active": active,
            "page_title": title,
        },
    )


@login_required
@require_admin
def administracao(request: HttpRequest) -> HttpResponse:
    now = timezone.localtime()
    cards = [
        {
            "key": "clientes",
            "class": "purple",
            "value": "128",
            "label": "Clientes ativos",
            "href": reverse("web:clientes"),
        },
        {
            "key": "campanhas",
            "class": "blue",
            "value": "12",
            "label": "Campanhas ativas",
            "href": reverse("web:campanhas"),
        },
        {
            "key": "pecas_criativos",
            "class": "teal",
            "value": "42 / 7",
            "label": "Peças ON / OFF",
            "href": reverse("web:pecas_criativos"),
        },
        {
            "key": "integracoes_meta",
            "class": "cyan",
            "value": now.strftime("%d/%m %H:%M"),
            "label": "Último sync Meta",
            "href": reverse("web:integracoes"),
        },
        {
            "key": "integracoes_google",
            "class": "blue",
            "value": now.strftime("%d/%m %H:%M"),
            "label": "Último sync Google",
            "href": reverse("web:integracoes"),
        },
        {
            "key": "uploads_planilhas",
            "class": "purple",
            "value": now.strftime("%d/%m %H:%M"),
            "label": "Última planilha processada",
            "href": reverse("web:uploads_planilhas"),
        },
    ]
    return render(
        request,
        "web/admin_home.html",
        {
            "active": "administracao",
            "page_title": "Administração",
            "cards": cards,
        },
    )


@login_required
def dashboard(request: HttpRequest) -> HttpResponse:
    return _render_module(request, active="dashboard", title="Dashboard")


@login_required
def timeline_campanhas(request: HttpRequest) -> HttpResponse:
    return _render_module(request, active="timeline_campanhas", title="Timeline Campanhas")


@login_required
def campanhas(request: HttpRequest) -> HttpResponse:
    role = effective_role(request)
    if role == "cliente":
        cliente_id = effective_cliente_id(request)
        campaigns = Campaign.objects.filter(cliente_id=cliente_id).select_related("cliente").order_by("-created_at")
    else:
        campaigns = Campaign.objects.all().select_related("cliente").order_by("-created_at")

    campaigns_with_stats = []
    for c in campaigns:
        totals = PlacementDay.objects.filter(placement_line__campaign=c).aggregate(
            insertions=Sum("insertions"),
            cost=Sum("cost"),
            min_date=Min("date"),
            max_date=Max("date"),
        )
        on_count = PlacementLine.objects.filter(campaign=c, media_type="online").count()
        off_count = PlacementLine.objects.filter(campaign=c, media_type="offline").count()
        campaigns_with_stats.append({
            "campaign": c,
            "cliente": c.cliente,
            "investment": c.total_budget or totals.get("cost") or 0,
            "insertions": totals.get("insertions") or 0,
            "on_count": on_count,
            "off_count": off_count,
            "start": totals.get("min_date") or c.start_date,
            "end": totals.get("max_date") or c.end_date,
        })

    return render(
        request,
        "web/campanhas.html",
        {
            "active": "campanhas",
            "page_title": "Campanhas",
            "campaigns_with_stats": campaigns_with_stats,
        },
    )


@login_required
def pecas_criativos(request: HttpRequest) -> HttpResponse:
    return _render_module(request, active="pecas_criativos", title="Peças & Criativos")


@login_required
def veiculacao(request: HttpRequest) -> HttpResponse:
    return _render_module(request, active="veiculacao", title="Veiculação")


@login_required
def relatorios(request: HttpRequest) -> HttpResponse:
    return _render_module(request, active="relatorios", title="Relatórios")


@login_required
def integracoes(request: HttpRequest) -> HttpResponse:
    return _render_module(request, active="integracoes", title="Integrações")


@login_required
def uploads_planilhas(request: HttpRequest) -> HttpResponse:
    return _render_module(request, active="uploads_planilhas", title="Uploads / Planilhas")


@login_required
def usuarios_permissoes(request: HttpRequest) -> HttpResponse:
    return _render_module(request, active="usuarios_permissoes", title="Usuários & Permissões")


@login_required
def clientes(request: HttpRequest) -> HttpResponse:
    return _render_module(request, active="clientes", title="Clientes")


@login_required
def configuracoes(request: HttpRequest) -> HttpResponse:
    return _render_module(request, active="configuracoes", title="Configurações")


@login_required
def logs_auditoria(request: HttpRequest) -> HttpResponse:
    return _render_module(request, active="logs_auditoria", title="Logs & Auditoria")


@login_required
def analytics(request: HttpRequest) -> HttpResponse:
    return _render_module(request, active="analytics", title="Analytics")


@login_required
@require_admin
def clientes_list(request: HttpRequest) -> HttpResponse:
    clientes = Cliente.objects.all().order_by("nome")
    return render(
        request,
        "web/clientes_list.html",
        {
            "active": "clientes",
            "page_title": "Clientes",
            "clientes": clientes,
        },
    )


@login_required
@require_admin
def clientes_create(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = ClienteForm(request.POST, request.FILES)
        if form.is_valid():
            cliente = form.save()
            return redirect("web:clientes_detail", cliente_id=cliente.id)
    else:
        form = ClienteForm()
    return render(
        request,
        "web/clientes_form.html",
        {
            "active": "clientes",
            "page_title": "Novo Cliente",
            "form": form,
        },
    )


@login_required
@require_admin
def clientes_edit(request: HttpRequest, cliente_id: int) -> HttpResponse:
    cliente = Cliente.objects.get(id=cliente_id)
    if request.method == "POST":
        form = ClienteForm(request.POST, request.FILES, instance=cliente)
        if form.is_valid():
            form.save()
            return redirect("web:clientes_detail", cliente_id=cliente.id)
    else:
        form = ClienteForm(instance=cliente)
    return render(
        request,
        "web/clientes_form.html",
        {
            "active": "clientes",
            "page_title": "Editar Cliente",
            "form": form,
            "cliente": cliente,
        },
    )


@login_required
@require_admin
def clientes_detail(request: HttpRequest, cliente_id: int) -> HttpResponse:
    cliente = Cliente.objects.get(id=cliente_id)
    User = get_user_model()
    usuarios = User.objects.filter(cliente_id=cliente.id).order_by("username")

    user_form_errors = ""
    if request.method == "POST" and request.POST.get("_action") == "create_user":
        user_form = ClienteUserCreateForm(request.POST)
        if user_form.is_valid():
            nome = user_form.cleaned_data["nome"]
            login = user_form.cleaned_data["login"]
            email = user_form.cleaned_data["email"]
            senha = user_form.cleaned_data["senha"]

            if User.objects.filter(username__iexact=login).exists():
                user_form_errors = "Login já existe."
            elif User.objects.filter(email__iexact=email).exists():
                user_form_errors = "E-mail já existe."
            else:
                user = User(
                    username=login,
                    email=email,
                    first_name=nome,
                    role=getattr(User, "Role").CLIENTE,
                    cliente_id=cliente.id,
                    funcao=getattr(User, "Funcao").VIEWER,
                    is_active=True,
                )
                user.set_password(senha)
                user.save()
                return redirect("web:clientes_detail", cliente_id=cliente.id)
        else:
            user_form_errors = "Preencha os campos do usuário corretamente."
    else:
        user_form = ClienteUserCreateForm()

    return render(
        request,
        "web/clientes_detail.html",
        {
            "active": "clientes",
            "page_title": "Cliente",
            "cliente": cliente,
            "usuarios": usuarios,
            "user_form": user_form,
            "user_form_errors": user_form_errors,
        },
    )


@login_required
@require_admin
def cliente_campaigns(request: HttpRequest, cliente_id: int) -> HttpResponse:
    cliente = Cliente.objects.get(id=cliente_id)
    campaigns = Campaign.objects.filter(cliente_id=cliente.id).order_by("-created_at")
    return render(
        request,
        "web/cliente_campaigns.html",
        {
            "active": "clientes",
            "page_title": "Campanhas",
            "cliente": cliente,
            "campaigns": campaigns,
        },
    )


@login_required
@require_admin
def campaign_edit(request: HttpRequest, campaign_id: int) -> HttpResponse:
    campaign = Campaign.objects.filter(id=campaign_id).select_related("cliente").first()
    if campaign is None:
        return redirect("web:clientes")

    form_errors = ""
    if request.method == "POST":
        form = CampaignEditForm(request.POST, instance=campaign)
        if form.is_valid():
            form.save()
            return redirect("web:cliente_campaigns", cliente_id=campaign.cliente_id)
        form_errors = "Preencha os campos corretamente."
    else:
        form = CampaignEditForm(instance=campaign)

    return render(
        request,
        "web/campaign_edit.html",
        {
            "active": "clientes",
            "page_title": "Editar Campanha",
            "campaign": campaign,
            "cliente": campaign.cliente,
            "form": form,
            "form_errors": form_errors,
        },
    )


@login_required
@require_admin
def campaign_delete(request: HttpRequest, campaign_id: int) -> HttpResponse:
    campaign = Campaign.objects.filter(id=campaign_id).select_related("cliente").first()
    if campaign is None:
        return redirect("web:clientes")
    if request.method == "POST":
        cliente_id = campaign.cliente_id
        campaign.delete()
        return redirect("web:cliente_campaigns", cliente_id=cliente_id)
    return render(
        request,
        "web/campaign_delete.html",
        {
            "active": "clientes",
            "page_title": "Excluir Campanha",
            "campaign": campaign,
            "cliente": campaign.cliente,
        },
    )


@login_required
@require_admin
def clientes_enter(request: HttpRequest, cliente_id: int) -> HttpResponse:
    if not is_admin(request.user):
        return redirect("web:dashboard")
    request.session["impersonate_cliente_id"] = int(cliente_id)
    return redirect("web:dashboard")


@login_required
def sair_visao_cliente(request: HttpRequest) -> HttpResponse:
    request.session.pop("impersonate_cliente_id", None)
    if is_admin(request.user):
        return redirect("web:clientes")
    return redirect("web:dashboard")


@login_required
@require_admin
def clientes_upload(request: HttpRequest, cliente_id: int) -> HttpResponse:
    return redirect("web:contract_wizard_step1", cliente_id=int(cliente_id))


@login_required
@require_admin
def contract_wizard_entry(request: HttpRequest) -> HttpResponse:
    return redirect("web:clientes")


@login_required
@require_admin
def contract_wizard_step1(request: HttpRequest, cliente_id: int) -> HttpResponse:
    cliente = Cliente.objects.get(id=cliente_id)

    if request.method == "POST":
        form = CampaignWizardForm(request.POST)
        if form.is_valid():
            campaign = form.save(commit=False)
            campaign.cliente_id = cliente.id
            campaign.status = getattr(Campaign, "Status").DRAFT
            campaign.created_by = request.user
            campaign.save()
            return redirect("web:contract_wizard_step2", campaign_id=campaign.id)
    else:
        form = CampaignWizardForm(
            initial={
                "timezone": "America/Sao_Paulo",
                "media_type": getattr(Campaign, "MediaType").ONLINE,
            }
        )

    return render(
        request,
        "web/contract_wizard_step1.html",
        {
            "active": "dashboard",
            "page_title": "Contrato de Upload",
            "cliente": cliente,
            "form": form,
            "today_text": timezone.localtime().strftime("%d/%m/%Y %H:%M"),
        },
    )


@login_required
@require_admin
def contract_wizard_step2(request: HttpRequest, campaign_id: int) -> HttpResponse:
    campaign = Campaign.objects.filter(id=campaign_id).select_related("cliente").first()
    if campaign is None:
        return redirect("web:clientes")

    form_errors = ""
    if request.method == "POST":
        form = ContractUploadForm(request.POST, request.FILES)
        if form.is_valid():
            contract_file = form.cleaned_data["contract_file"]
            ContractUpload.objects.create(campaign=campaign, file=contract_file)
            return redirect("web:contract_done", campaign_id=campaign.id)
        form_errors = "Selecione um arquivo para upload."
    else:
        form = ContractUploadForm()

    return render(
        request,
        "web/contract_wizard_step2.html",
        {
            "active": "dashboard",
            "page_title": "Contrato de Upload",
            "cliente": campaign.cliente,
            "campaign": campaign,
            "form": form,
            "form_errors": form_errors,
        },
    )


@login_required
@require_admin
def contract_done(request: HttpRequest, campaign_id: int) -> HttpResponse:
    campaign = Campaign.objects.filter(id=campaign_id).select_related("cliente").first()
    if campaign is None:
        return redirect("web:clientes")
    last_upload = campaign.contract_uploads.order_by("-created_at").first()

    lines = list(PlacementLine.objects.filter(campaign=campaign).only("id", "market", "media_type", "media_channel"))

    totals = PlacementDay.objects.filter(placement_line__campaign=campaign).aggregate(
        insertions=Sum("insertions"),
        impressions=Sum("impressions"),
        clicks=Sum("clicks"),
        cost=Sum("cost"),
        min_date=Min("date"),
        max_date=Max("date"),
    )

    investment_by_market = (
        PlacementDay.objects.filter(placement_line__campaign=campaign)
        .values("placement_line__market")
        .annotate(total_cost=Sum("cost"))
        .order_by("-total_cost")
    )

    markets_data = []
    total_cost = sum(float(m["total_cost"] or 0) for m in investment_by_market)
    colors = ["#6366f1", "#f59e0b", "#3b82f6", "#10b981", "#ef4444", "#8b5cf6"]
    for i, m in enumerate(investment_by_market[:6]):
        market_name = (m["placement_line__market"] or "Outros").strip()
        if not market_name:
            market_name = "Outros"
        cost = float(m["total_cost"] or 0)
        pct = round((cost / total_cost * 100) if total_cost > 0 else 0)
        markets_data.append({
            "name": market_name,
            "cost": cost,
            "pct": pct,
            "color": colors[i % len(colors)],
        })

    timeline_data = []

    # Buscar linhas com peças vinculadas
    lines_with_pieces = (
        PlacementLine.objects.filter(campaign=campaign)
        .prefetch_related("placement_creatives__piece")
        .annotate(
            min_day=Min("days__date"),
            max_day=Max("days__date"),
            total_insertions=Sum("days__insertions"),
        )
        .filter(min_day__isnull=False)
        .order_by("market", "media_channel")
    )

    # Cores vibrantes para as barras da timeline (por código de peça)
    piece_colors = [
        "#fde047",  # Amarelo
        "#86efac",  # Verde claro
        "#93c5fd",  # Azul claro
        "#fca5a5",  # Vermelho claro
        "#c4b5fd",  # Roxo claro
        "#fdba74",  # Laranja
        "#67e8f9",  # Ciano
        "#f9a8d4",  # Rosa
        "#a3e635",  # Lima
        "#fcd34d",  # Âmbar
    ]

    # Mapeamento de código de peça para cor
    piece_color_map: dict = {}
    color_index = 0

    def get_piece_color(code: str) -> str:
        nonlocal color_index
        if not code:
            return "#d1d5db"
        code_upper = code.upper()
        if code_upper not in piece_color_map:
            piece_color_map[code_upper] = piece_colors[color_index % len(piece_colors)]
            color_index += 1
        return piece_color_map[code_upper]

    grouped_by_channel: dict = {}
    for line in lines_with_pieces:
        channel = (line.channel or line.program or line.media_channel or "Outros").strip()
        if not channel:
            channel = "Outros"
        if channel not in grouped_by_channel:
            grouped_by_channel[channel] = {"media_channel": line.media_channel, "items": []}

        # Buscar peças vinculadas a esta linha
        linked_pieces = list(line.placement_creatives.select_related("piece").all())

        if linked_pieces:
            for pc in linked_pieces:
                piece = pc.piece
                duration_str = f'{piece.duration_sec}"' if piece.duration_sec else ""
                title = f"{piece.title} {duration_str}".strip()
                grouped_by_channel[channel]["items"].append({
                    "title": title,
                    "piece_code": piece.code,
                    "channel": line.media_channel,
                    "program": line.channel or line.program or "",
                    "start": line.min_day,
                    "end": line.max_day,
                    "insertions": line.total_insertions or 0,
                    "color": get_piece_color(piece.code),
                })
        else:
            # Sem peça vinculada, usar programa/canal
            title = line.program or line.channel or line.media_channel
            grouped_by_channel[channel]["items"].append({
                "title": title,
                "piece_code": "",
                "channel": line.media_channel,
                "program": line.channel or line.program or "",
                "start": line.min_day,
                "end": line.max_day,
                "insertions": line.total_insertions or 0,
                "color": "#d1d5db",
            })

    for channel_name, data in grouped_by_channel.items():
        timeline_data.append({
            "channel": channel_name,
            "media_channel": data["media_channel"],
            "items": [
                {
                    **item,
                    "start_str": item["start"].strftime("%d/%m") if item["start"] else "",
                    "end_str": item["end"].strftime("%d/%m") if item["end"] else "",
                }
                for item in data["items"]
            ],
        })

    pieces = list(campaign.pieces.all().order_by("-created_at")[:5])
    recent_activities = []
    for p in pieces:
        recent_activities.append({
            "title": p.title,
            "code": p.code,
            "type": p.type,
            "created_at": p.created_at,
        })

    pieces_stats = campaign.pieces.aggregate(
        total=models.Count("id"),
    )
    on_count = PlacementLine.objects.filter(campaign=campaign, media_type="online").count()
    off_count = PlacementLine.objects.filter(campaign=campaign, media_type="offline").count()

    return render(
        request,
        "web/contract_done.html",
        {
            "active": "dashboard",
            "page_title": "Dashboard Campanha",
            "campaign": campaign,
            "cliente": campaign.cliente,
            "last_upload": last_upload,
            "totals": {
                "investment": campaign.total_budget or totals.get("cost") or 0,
                "insertions": totals.get("insertions") or 0,
                "impressions": totals.get("impressions") or 0,
                "cost": totals.get("cost") or 0,
                "start": totals.get("min_date"),
                "end": totals.get("max_date"),
            },
            "pieces_stats": {
                "total": pieces_stats.get("total") or 0,
                "on": on_count,
                "off": off_count,
            },
            "markets_data": markets_data,
            "timeline_data": timeline_data,
            "recent_activities": recent_activities,
        },
    )


@login_required
@require_admin
def campaign_media_plan_upload(request: HttpRequest, campaign_id: int) -> HttpResponse:
    campaign = Campaign.objects.filter(id=campaign_id).select_related("cliente").first()
    if campaign is None:
        return redirect("web:clientes")
    form_errors = ""
    result = None
    form = MediaPlanUploadForm()
    if request.method == "POST":
        action = request.POST.get("_action") or "validate"
        if action == "import":
            upload_id = request.POST.get("upload_id")
            replace = bool(request.POST.get("replace_existing"))
            upload = MediaPlanUpload.objects.filter(id=upload_id, campaign=campaign).first()
            if upload is None:
                form_errors = "Upload não encontrado."
            else:
                parsed = import_media_plan_xlsx(campaign=campaign, uploaded_file=upload.file, replace_existing=replace)
                if parsed.get("ok"):
                    upload.summary = parsed
                    upload.save(update_fields=["summary"])
                    result = parsed
                else:
                    form_errors = "; ".join(parsed.get("errors", ["Falha ao importar."]))
        else:
            form = MediaPlanUploadForm(request.POST, request.FILES)
            if form.is_valid():
                xlsx = form.cleaned_data["xlsx_file"]
                upload = MediaPlanUpload.objects.create(campaign=campaign, file=xlsx, summary={})
                parsed = parse_media_plan_xlsx(upload.file)
                upload.summary = {
                    "ok": bool(parsed.get("ok")),
                    "errors": parsed.get("errors", []),
                    "sheets": parsed.get("sheets", []),
                    "total_rows": parsed.get("total_rows", 0),
                    "valid_rows": len(parsed.get("parsed_rows", []) or []),
                    "detected": parsed.get("detected", {}),
                }
                upload.save(update_fields=["summary"])
                result = dict(upload.summary)
                result["upload_id"] = upload.id
            else:
                form_errors = "Selecione um arquivo .xlsx válido."

    return render(
        request,
        "web/campaign_media_plan_upload.html",
        {
            "active": "campanhas",
            "page_title": "Upload Plano de Mídia",
            "campaign": campaign,
            "cliente": campaign.cliente,
            "form": form,
            "form_errors": form_errors,
            "result": result,
        },
    )


@login_required
@require_admin
def campaign_assets_upload(request: HttpRequest, campaign_id: int) -> HttpResponse:
    campaign = Campaign.objects.filter(id=campaign_id).select_related("cliente").first()
    if campaign is None:
        return redirect("web:clientes")
    form_errors = ""
    result = None
    if request.method == "POST":
        files = request.FILES.getlist("files")
        if not files:
            form_errors = "Selecione um ou mais arquivos."
        else:
            result = attach_assets_to_campaign(campaign=campaign, files=files)

    return render(
        request,
        "web/campaign_assets_upload.html",
        {
            "active": "campanhas",
            "page_title": "Upload de Peças",
            "campaign": campaign,
            "cliente": campaign.cliente,
            "form_errors": form_errors,
            "result": result,
        },
    )


@login_required
@require_admin
def campaign_link_matrix(request: HttpRequest, campaign_id: int) -> HttpResponse:
    campaign = Campaign.objects.filter(id=campaign_id).first()
    if campaign is None:
        return redirect("web:clientes")

    lines = list(PlacementLine.objects.filter(campaign=campaign).order_by("id"))
    pieces = list(campaign.pieces.order_by("code"))
    current_pairs = list(
        PlacementCreative.objects.filter(placement_line__campaign=campaign).values_list("placement_line_id", "piece_id")
    )
    links_by_line: dict[int, set[int]] = {}
    for lid, pid in current_pairs:
        links_by_line.setdefault(int(lid), set()).add(int(pid))
    saved = False
    if request.method == "POST":
        desired = set()
        for line in lines:
            for piece in pieces:
                key = f"link_{line.id}_{piece.id}"
                if request.POST.get(key):
                    desired.add((line.id, piece.id))
        current_set = set(current_pairs)
        added = desired - current_set
        removed = current_set - desired
        for lid, pid in added:
            PlacementCreative.objects.get_or_create(placement_line_id=lid, piece_id=pid)
        for lid, pid in removed:
            PlacementCreative.objects.filter(placement_line_id=lid, piece_id=pid).delete()
        saved = True
        links_by_line = {}
        for lid, pid in desired:
            links_by_line.setdefault(int(lid), set()).add(int(pid))

    matrix_rows = []
    for line in lines:
        selected = links_by_line.get(line.id, set())
        matrix_rows.append(
            {
                "line": line,
                "cells": [{"piece": p, "checked": p.id in selected} for p in pieces],
            }
        )

    return render(
        request,
        "web/campaign_link_matrix.html",
        {
            "active": "campanhas",
            "page_title": "Vinculação Linhas ↔ Peças",
            "campaign": campaign,
            "pieces": pieces,
            "matrix_rows": matrix_rows,
            "saved": saved,
        },
    )


@login_required
@require_admin
def campaign_set_status(request: HttpRequest, campaign_id: int) -> HttpResponse:
    campaign = Campaign.objects.filter(id=campaign_id).first()
    if campaign is None:
        return redirect("web:clientes")
    status = request.POST.get("status") or ""
    valid = {Campaign.Status.DRAFT, Campaign.Status.ACTIVE, Campaign.Status.PAUSED, Campaign.Status.FINISHED, Campaign.Status.ARCHIVED}
    if status in valid:
        campaign.status = status
        campaign.save(update_fields=["status"])
    return redirect("web:clientes_detail", cliente_id=campaign.cliente_id)


def api_campaign_detail(request: HttpRequest, campaign_id: int) -> HttpResponse:
    if not request.user.is_authenticated:
        return JsonResponse({"error": "unauthorized"}, status=401)
    campaign = (
        Campaign.objects.filter(id=campaign_id)
        .select_related("cliente")
        .prefetch_related("pieces__assets")
        .first()
    )
    if campaign is None:
        return JsonResponse({"error": "not_found"}, status=404)

    if not is_admin(request.user):
        cliente_id = effective_cliente_id(request)
        if not cliente_id or int(cliente_id) != int(campaign.cliente_id):
            return JsonResponse({"error": "forbidden"}, status=403)

    lines = list(PlacementLine.objects.filter(campaign=campaign).only("id", "market", "media_type", "media_channel"))
    markets = sorted({(l.market or "").strip() for l in lines if (l.market or "").strip()})
    channels = sorted({l.media_channel for l in lines if l.media_channel})
    media_types = sorted({l.media_type for l in lines if l.media_type})

    pretty_media_channel = {
        "tv_aberta": "TV Aberta",
        "paytv": "PayTV",
        "radio": "Rádio",
        "ooh": "OOH",
        "jornal": "Jornal",
        "meta": "Meta",
        "google": "Google",
        "youtube": "YouTube",
        "display": "Display",
        "search": "Search",
        "social": "Social",
        "other": "Outro",
    }
    pretty_media_type = {"online": "ON", "offline": "OFF"}

    day_by_line = {
        row["placement_line_id"]: row
        for row in PlacementDay.objects.filter(placement_line__campaign=campaign)
        .values("placement_line_id")
        .annotate(
            min_date=Min("date"),
            max_date=Max("date"),
            insertions=Sum("insertions"),
            impressions=Sum("impressions"),
            clicks=Sum("clicks"),
            cost=Sum("cost"),
        )
    }
    totals = PlacementDay.objects.filter(placement_line__campaign=campaign).aggregate(
        insertions=Sum("insertions"),
        impressions=Sum("impressions"),
        clicks=Sum("clicks"),
        cost=Sum("cost"),
        min_date=Min("date"),
        max_date=Max("date"),
    )

    links = list(
        PlacementCreative.objects.filter(placement_line__campaign=campaign)
        .select_related("placement_line", "piece")
        .only("placement_line_id", "piece_id", "placement_line__market", "placement_line__media_type", "placement_line__media_channel")
    )
    links_by_piece: dict[int, list[PlacementLine]] = {}
    for link in links:
        links_by_piece.setdefault(int(link.piece_id), []).append(link.placement_line)

    pieces_payload = []
    for piece in campaign.pieces.all().order_by("code"):
        linked_lines = links_by_piece.get(int(piece.id), [])
        line_ids = [int(l.id) for l in linked_lines]

        piece_markets = sorted({(l.market or "").strip() for l in linked_lines if (l.market or "").strip()})
        piece_channels = sorted({l.media_channel for l in linked_lines if l.media_channel})
        piece_media_types = sorted({l.media_type for l in linked_lines if l.media_type})

        min_d = None
        max_d = None
        insertions = 0
        impressions = 0
        clicks = 0
        cost = None
        for lid in line_ids:
            info = day_by_line.get(lid)
            if not info:
                continue
            if info.get("min_date") and (min_d is None or info["min_date"] < min_d):
                min_d = info["min_date"]
            if info.get("max_date") and (max_d is None or info["max_date"] > max_d):
                max_d = info["max_date"]
            insertions += int(info.get("insertions") or 0)
            impressions += int(info.get("impressions") or 0)
            clicks += int(info.get("clicks") or 0)
            cst = info.get("cost")
            if cst is not None:
                cost = (cost or 0) + cst

        badge = ""
        if "online" in piece_media_types and "offline" in piece_media_types:
            badge = "MIX"
        elif "online" in piece_media_types:
            badge = "ON"
        elif "offline" in piece_media_types:
            badge = "OFF"

        subtitle = " + ".join([pretty_media_channel.get(ch, ch) for ch in piece_channels]) if piece_channels else ""
        last_asset = piece.assets.order_by("-created_at").first()
        image_url = ""
        if last_asset and getattr(last_asset.file, "url", ""):
            image_url = request.build_absolute_uri(last_asset.file.url)

        pieces_payload.append(
            {
                "id": piece.id,
                "code": piece.code,
                "title": piece.title,
                "duration_sec": piece.duration_sec,
                "type": piece.type,
                "status": piece.status,
                "badge": badge,
                "subtitle": subtitle,
                "markets": piece_markets,
                "period": {"start": min_d.isoformat() if min_d else None, "end": max_d.isoformat() if max_d else None},
                "metrics": {
                    "insertions": insertions,
                    "impressions": impressions or None,
                    "clicks": clicks or None,
                    "cost": str(cost) if cost is not None else None,
                },
                "image_url": image_url,
            }
        )

    on_count = 0
    off_count = 0
    for p in pieces_payload:
        if p["badge"] == "ON":
            on_count += 1
        if p["badge"] == "OFF":
            off_count += 1

    payload = {
        "id": campaign.id,
        "cliente": {"id": campaign.cliente_id, "nome": campaign.cliente.nome},
        "name": campaign.name,
        "timezone": campaign.timezone,
        "status": campaign.status,
        "media_type": campaign.media_type,
        "period": {
            "start": campaign.start_date.isoformat() if campaign.start_date else None,
            "end": campaign.end_date.isoformat() if campaign.end_date else None,
        },
        "markets": markets,
        "media": {
            "types": [pretty_media_type.get(t, t) for t in media_types],
            "channels": [pretty_media_channel.get(c, c) for c in channels],
        },
        "budget_total": str(campaign.total_budget) if campaign.total_budget is not None else None,
        "metrics": {
            "insertions": int(totals.get("insertions") or 0),
            "impressions": int(totals.get("impressions") or 0) or None,
            "clicks": int(totals.get("clicks") or 0) or None,
            "cost": str(totals.get("cost")) if totals.get("cost") is not None else None,
            "start": totals.get("min_date").isoformat() if totals.get("min_date") else None,
            "end": totals.get("max_date").isoformat() if totals.get("max_date") else None,
        },
        "pieces": pieces_payload,
        "pieces_stats": {"total": len(pieces_payload), "on": on_count, "off": off_count},
        "updated_at": campaign.updated_at.isoformat() if campaign.updated_at else None,
    }
    return JsonResponse(payload)


@csrf_exempt
def api_login(request: HttpRequest) -> HttpResponse:
    if request.method != "POST":
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    try:
        body = json.loads((request.body or b"{}").decode("utf-8"))
    except Exception:
        body = {}
    login_value = (body.get("login") or body.get("email") or "").strip()
    password = body.get("password") or ""
    remember = bool(body.get("remember", True))
    if not login_value or not password:
        return JsonResponse({"error": "invalid_payload"}, status=400)

    user = authenticate(request, username=login_value, password=password)
    if user is None:
        User = get_user_model()
        by_email = User.objects.filter(email__iexact=login_value).only("username").first()
        if by_email is not None:
            user = authenticate(request, username=by_email.username, password=password)
    if user is None:
        return JsonResponse({"error": "invalid_credentials"}, status=400)

    auth_login(request, user)
    if not remember:
        request.session.set_expiry(0)
    return JsonResponse(
        {
            "ok": True,
            "user": {
                "id": getattr(user, "id", None),
                "username": getattr(user, "username", ""),
                "email": getattr(user, "email", ""),
                "role": effective_role(request),
                "cliente_id": effective_cliente_id(request),
            },
        }
    )


@csrf_exempt
def api_logout(request: HttpRequest) -> HttpResponse:
    if request.method not in {"POST", "GET"}:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    request.session.pop("impersonate_cliente_id", None)
    auth_logout(request)
    return JsonResponse({"ok": True})


def api_me(request: HttpRequest) -> HttpResponse:
    if not request.user.is_authenticated:
        return JsonResponse({"authenticated": False}, status=401)
    return JsonResponse(
        {
            "authenticated": True,
            "user": {
                "id": getattr(request.user, "id", None),
                "username": getattr(request.user, "username", ""),
                "email": getattr(request.user, "email", ""),
                "role": effective_role(request),
                "cliente_id": effective_cliente_id(request),
            },
        }
    )
