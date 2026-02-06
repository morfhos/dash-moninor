from accounts.models import AuditLog, Cliente

from campaigns.models import Campaign, ContractUpload, CreativeAsset, MediaPlanUpload, Piece, PlacementCreative, PlacementDay, PlacementLine, RegionInvestment
from campaigns.services import import_media_plan_xlsx, attach_assets_to_campaign, parse_media_plan_xlsx
from datetime import datetime, timedelta
from django.contrib.auth import get_user_model
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.db import models
from django.db.models import Count, Max, Min, Sum
from django.db.models.functions import TruncDate, TruncHour
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
import json

from .authz import effective_cliente_id, effective_role, is_admin, require_admin, require_true_admin
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
                # Log de login falho
                AuditLog.log(
                    AuditLog.EventType.LOGIN_FAILED,
                    request=request,
                    details={"login": login_value},
                )
            else:
                auth_login(request, user)
                if not remember:
                    request.session.set_expiry(0)
                # Log de login bem-sucedido
                AuditLog.log(
                    AuditLog.EventType.LOGIN,
                    request=request,
                    user=user,
                    cliente=user.cliente,
                    details={"login": login_value},
                )
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
    # Log de logout antes de deslogar
    if request.user.is_authenticated:
        AuditLog.log(
            AuditLog.EventType.LOGOUT,
            request=request,
            user=request.user,
            cliente=getattr(request.user, "cliente", None),
        )
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
@require_true_admin
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
    role = effective_role(request)

    # Filtrar campanhas baseado no role
    if role == "cliente":
        cliente_id = effective_cliente_id(request)
        campaigns_qs = Campaign.objects.filter(cliente_id=cliente_id, status="active")
        cliente = Cliente.objects.filter(id=cliente_id).first()
    else:
        campaigns_qs = Campaign.objects.filter(status="active")
        cliente = None

    # Contadores
    total_campaigns = campaigns_qs.count()

    # Contar linhas ativas (data final >= hoje) vs inativas (data final < hoje)
    today = timezone.localdate()
    on_count = PlacementLine.objects.filter(
        campaign__in=campaigns_qs
    ).annotate(
        max_day=Max("days__date")
    ).filter(max_day__gte=today).count()

    off_count = PlacementLine.objects.filter(
        campaign__in=campaigns_qs
    ).annotate(
        max_day=Max("days__date")
    ).filter(max_day__lt=today).count()

    # Totais consolidados
    totals = PlacementDay.objects.filter(placement_line__campaign__in=campaigns_qs).aggregate(
        insertions=Sum("insertions"),
        impressions=Sum("impressions"),
        clicks=Sum("clicks"),
        cost=Sum("cost"),
    )

    # Investimento total (budget das campanhas)
    investment = campaigns_qs.aggregate(total=Sum("total_budget"))["total"] or 0

    return render(
        request,
        "web/dashboard.html",
        {
            "active": "dashboard",
            "page_title": "Dashboard",
            "role": role,
            "cliente": cliente,
            "stats": {
                "investment": investment,
                "on_count": on_count,
                "off_count": off_count,
                "cost": totals.get("cost") or 0,
                "insertions": totals.get("insertions") or 0,
                "total_campaigns": total_campaigns,
            },
        },
    )


@login_required
def timeline_campanhas(request: HttpRequest) -> HttpResponse:
    return _render_module(request, active="timeline_campanhas", title="Timeline Campanhas")


@login_required
def grupo_campanhas(request: HttpRequest) -> HttpResponse:
    """Lista os clientes em boxes para acessar suas campanhas."""
    role = effective_role(request)

    # Se for cliente, redireciona direto para suas campanhas
    if role == "cliente":
        cliente_id = effective_cliente_id(request)
        return redirect("web:campanhas_cliente", cliente_id=cliente_id)

    # Para admins, lista todos os clientes que têm campanhas
    clientes_com_campanhas = (
        Cliente.objects.filter(campaigns__isnull=False)
        .distinct()
        .annotate(
            total_campaigns=Count("campaigns"),
            total_investment=Sum("campaigns__total_budget"),
        )
        .order_by("nome")
    )

    return render(
        request,
        "web/grupo_campanhas.html",
        {
            "active": "campanhas",
            "page_title": "Campanhas",
            "clientes": clientes_com_campanhas,
        },
    )


@login_required
def campanhas_cliente(request: HttpRequest, cliente_id: int) -> HttpResponse:
    """Lista as campanhas de um cliente específico."""
    role = effective_role(request)

    # Verificar acesso
    if role == "cliente":
        user_cliente_id = effective_cliente_id(request)
        if int(user_cliente_id) != int(cliente_id):
            return redirect("web:campanhas_cliente", cliente_id=user_cliente_id)

    cliente = Cliente.objects.filter(id=cliente_id).first()
    if cliente is None:
        return redirect("web:grupo_campanhas")

    campaigns = Campaign.objects.filter(cliente_id=cliente_id).select_related("cliente").order_by("-created_at")

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
            "page_title": f"Campanhas - {cliente.nome}",
            "cliente": cliente,
            "campaigns_with_stats": campaigns_with_stats,
            "show_back": role != "cliente",
        },
    )


@login_required
def campanhas(request: HttpRequest) -> HttpResponse:
    """Redireciona para grupo_campanhas (mantém compatibilidade)."""
    return redirect("web:grupo_campanhas")


@login_required
def pecas_criativos(request: HttpRequest) -> HttpResponse:
    """Lista os clientes em boxes para acessar suas peças."""
    role = effective_role(request)

    # Se for cliente, redireciona direto para suas campanhas (peças)
    if role == "cliente":
        cliente_id = effective_cliente_id(request)
        return redirect("web:pecas_campanhas", cliente_id=cliente_id)

    # Para admins, lista todos os clientes que têm campanhas
    clientes_com_campanhas = (
        Cliente.objects.filter(campaigns__isnull=False)
        .distinct()
        .annotate(
            total_campaigns=Count("campaigns"),
        )
        .order_by("nome")
    )

    return render(
        request,
        "web/pecas_clientes.html",
        {
            "active": "pecas_criativos",
            "page_title": "Peças & Criativos",
            "clientes": clientes_com_campanhas,
        },
    )


@login_required
def pecas_campanhas(request: HttpRequest, cliente_id: int) -> HttpResponse:
    """Lista as campanhas de um cliente para ver/editar peças."""
    role = effective_role(request)

    # Verificar acesso
    if role == "cliente":
        user_cliente_id = effective_cliente_id(request)
        if int(user_cliente_id) != int(cliente_id):
            return redirect("web:pecas_campanhas", cliente_id=user_cliente_id)

    cliente = Cliente.objects.filter(id=cliente_id).first()
    if cliente is None:
        return redirect("web:pecas_criativos")

    campaigns = Campaign.objects.filter(cliente_id=cliente_id).select_related("cliente").order_by("-created_at")

    campaigns_with_stats = []
    for c in campaigns:
        # Contar peças e peças com mídia
        total_pieces = c.pieces.count()
        pieces_with_media = c.pieces.filter(assets__isnull=False).distinct().count()
        pct = round((pieces_with_media / total_pieces * 100) if total_pieces > 0 else 0)

        campaigns_with_stats.append({
            "campaign": c,
            "total_pieces": total_pieces,
            "pieces_with_media": pieces_with_media,
            "pct": pct,
            "start": c.start_date,
            "end": c.end_date,
        })

    return render(
        request,
        "web/pecas_campanhas.html",
        {
            "active": "pecas_criativos",
            "page_title": f"Peças & Criativos - {cliente.nome}",
            "cliente": cliente,
            "campaigns_with_stats": campaigns_with_stats,
            "show_back": role != "cliente",
        },
    )


@login_required
def veiculacao(request: HttpRequest) -> HttpResponse:
    return _render_module(request, active="veiculacao", title="Veiculação")


@login_required
def relatorios(request: HttpRequest) -> HttpResponse:
    """Redireciona para lista de clientes para relatórios."""
    return redirect("web:relatorios_clientes")


@login_required
def integracoes(request: HttpRequest) -> HttpResponse:
    return _render_module(request, active="integracoes", title="Integrações")


@login_required
def uploads_planilhas(request: HttpRequest) -> HttpResponse:
    """Redireciona para upload de mídia."""
    return redirect("web:uploads_midia_clientes")


@login_required
@require_true_admin
def usuarios_permissoes(request: HttpRequest) -> HttpResponse:
    """Lista e gerencia usuários do sistema."""
    from accounts.models import User

    # Listar usuários admin e colaborador (não clientes)
    users = User.objects.filter(
        role__in=["admin", "colaborador"]
    ).order_by("-date_joined")

    return render(
        request,
        "web/usuarios_permissoes.html",
        {
            "active": "usuarios_permissoes",
            "page_title": "Usuários & Permissões",
            "users": users,
        },
    )


@login_required
def clientes(request: HttpRequest) -> HttpResponse:
    return _render_module(request, active="clientes", title="Clientes")


@login_required
@require_true_admin
def configuracoes(request: HttpRequest) -> HttpResponse:
    return _render_module(request, active="configuracoes", title="Configurações")


@login_required
@require_true_admin
def logs_auditoria(request: HttpRequest) -> HttpResponse:
    role = effective_role(request)
    if role == "cliente":
        return redirect("web:dashboard")

    # Filtros de data - padrão: último dia
    hoje = timezone.now().date()
    ontem = hoje - timedelta(days=1)

    data_de = request.GET.get("data_de", ontem.isoformat())
    data_ate = request.GET.get("data_ate", hoje.isoformat())

    try:
        data_de_parsed = datetime.strptime(data_de, "%Y-%m-%d").date()
        data_ate_parsed = datetime.strptime(data_ate, "%Y-%m-%d").date()
    except ValueError:
        data_de_parsed = ontem
        data_ate_parsed = hoje

    # Garante que data_ate inclui o dia inteiro
    data_ate_dt = timezone.make_aware(datetime.combine(data_ate_parsed, datetime.max.time()))
    data_de_dt = timezone.make_aware(datetime.combine(data_de_parsed, datetime.min.time()))

    # Queryset base filtrado por data
    logs_qs = AuditLog.objects.filter(
        created_at__gte=data_de_dt,
        created_at__lte=data_ate_dt,
    )

    # Stats gerais
    total_logs = logs_qs.count()
    total_logins = logs_qs.filter(event_type=AuditLog.EventType.LOGIN).count()
    total_login_failed = logs_qs.filter(event_type=AuditLog.EventType.LOGIN_FAILED).count()
    total_pieces_deleted = logs_qs.filter(event_type=AuditLog.EventType.PIECE_DELETED).count()
    total_campaigns_created = logs_qs.filter(event_type=AuditLog.EventType.CAMPAIGN_CREATED).count()
    total_assets_uploaded = logs_qs.filter(event_type=AuditLog.EventType.ASSET_UPLOADED).count()

    # Contagem por tipo de evento para gráfico de pizza
    events_by_type = list(
        logs_qs.values("event_type")
        .annotate(count=Count("id"))
        .order_by("-count")
    )

    # Mapear labels dos eventos
    event_labels = dict(AuditLog.EventType.choices)
    for item in events_by_type:
        item["label"] = event_labels.get(item["event_type"], item["event_type"])

    # Logins por hora (para gráfico de linha)
    logins_by_hour = list(
        logs_qs.filter(event_type__in=[AuditLog.EventType.LOGIN, AuditLog.EventType.LOGIN_FAILED])
        .annotate(hora=TruncHour("created_at"))
        .values("hora", "event_type")
        .annotate(count=Count("id"))
        .order_by("hora")
    )

    # Processar para Chart.js
    horas_labels = []
    logins_success = []
    logins_failed = []

    horas_dict = {}
    for item in logins_by_hour:
        hora_str = item["hora"].strftime("%d/%m %H:00")
        if hora_str not in horas_dict:
            horas_dict[hora_str] = {"success": 0, "failed": 0}
        if item["event_type"] == AuditLog.EventType.LOGIN:
            horas_dict[hora_str]["success"] = item["count"]
        else:
            horas_dict[hora_str]["failed"] = item["count"]

    for hora, counts in sorted(horas_dict.items()):
        horas_labels.append(hora)
        logins_success.append(counts["success"])
        logins_failed.append(counts["failed"])

    # Eventos por dia (para gráfico de barras)
    events_by_day = list(
        logs_qs.annotate(dia=TruncDate("created_at"))
        .values("dia")
        .annotate(count=Count("id"))
        .order_by("dia")
    )

    dias_labels = [item["dia"].strftime("%d/%m") for item in events_by_day]
    dias_counts = [item["count"] for item in events_by_day]

    # Top usuários mais ativos
    top_users = list(
        logs_qs.filter(user__isnull=False)
        .values("user__username", "user__first_name", "user__last_name")
        .annotate(count=Count("id"))
        .order_by("-count")[:10]
    )

    # Últimos 50 logs para tabela
    recent_logs = logs_qs.select_related("user", "cliente")[:50]

    context = {
        "active": "logs_auditoria",
        "page_title": "Logs & Auditoria",
        "data_de": data_de,
        "data_ate": data_ate,
        "total_logs": total_logs,
        "total_logins": total_logins,
        "total_login_failed": total_login_failed,
        "total_pieces_deleted": total_pieces_deleted,
        "total_campaigns_created": total_campaigns_created,
        "total_assets_uploaded": total_assets_uploaded,
        "events_by_type": json.dumps(events_by_type, default=str),
        "horas_labels": json.dumps(horas_labels),
        "logins_success": json.dumps(logins_success),
        "logins_failed": json.dumps(logins_failed),
        "dias_labels": json.dumps(dias_labels),
        "dias_counts": json.dumps(dias_counts),
        "top_users": top_users,
        "recent_logs": recent_logs,
        "event_labels": event_labels,
    }

    return render(request, "web/logs_auditoria.html", context)


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
            # Log de cliente criado
            AuditLog.log(
                AuditLog.EventType.CLIENTE_CREATED,
                request=request,
                cliente=cliente,
                details={"cliente_nome": cliente.nome},
            )
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
        campaign_name = campaign.name
        # Log de campanha deletada
        AuditLog.log(
            AuditLog.EventType.CAMPAIGN_DELETED,
            request=request,
            cliente=campaign.cliente,
            details={"campaign_id": campaign_id, "campaign_name": campaign_name},
        )
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
            # Log de campanha criada
            AuditLog.log(
                AuditLog.EventType.CAMPAIGN_CREATED,
                request=request,
                cliente=cliente,
                details={"campaign_id": campaign.id, "campaign_name": campaign.name},
            )
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
def contract_done(request: HttpRequest, campaign_id: int) -> HttpResponse:
    campaign = Campaign.objects.filter(id=campaign_id).select_related("cliente").first()
    if campaign is None:
        return redirect("web:dashboard")

    # Verificar acesso: admins podem ver todas, clientes só as suas
    role = effective_role(request)
    if role == "cliente":
        cliente_id = effective_cliente_id(request)
        if not cliente_id or int(cliente_id) != int(campaign.cliente_id):
            return redirect("web:dashboard")
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

    # Verificar se há investimentos por região manuais
    manual_region_investments = list(campaign.region_investments.all().order_by("order", "region_name"))

    if manual_region_investments:
        # Usar valores manuais
        markets_data = []
        for inv in manual_region_investments:
            markets_data.append({
                "name": inv.region_name,
                "cost": 0,
                "pct": int(inv.percentage),
                "color": inv.color,
            })
    else:
        # Calcular automaticamente a partir dos dados
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

    # Conjuntos para coletar valores únicos dos filtros
    unique_piece_titles: set = set()
    unique_channels: set = set()
    unique_markets: set = set()

    grouped_by_channel: dict = {}
    for line in lines_with_pieces:
        channel = (line.channel or line.program or line.media_channel or "Outros").strip()
        if not channel:
            channel = "Outros"
        if channel not in grouped_by_channel:
            grouped_by_channel[channel] = {"media_channel": line.media_channel, "items": []}

        # Coletar channel para o filtro
        if channel:
            unique_channels.add(channel)

        # Coletar market para o filtro de praças
        market = (line.market or "").strip()
        if market:
            unique_markets.add(market)

        # Buscar peças vinculadas a esta linha
        linked_pieces = list(line.placement_creatives.select_related("piece").all())

        # Apenas exibir itens que têm peças vinculadas
        if linked_pieces:
            for pc in linked_pieces:
                piece = pc.piece
                duration_str = f'{piece.duration_sec}"' if piece.duration_sec else ""
                title = f"{piece.title} {duration_str}".strip()
                unique_piece_titles.add(title)
                grouped_by_channel[channel]["items"].append({
                    "title": title,
                    "piece_id": piece.id,
                    "piece_code": piece.code,
                    "channel": line.media_channel,
                    "channel_name": channel,
                    "market": market,
                    "program": line.channel or line.program or "",
                    "start": line.min_day,
                    "end": line.max_day,
                    "insertions": line.total_insertions or 0,
                    "color": get_piece_color(piece.code),
                })
        # Linhas sem peças vinculadas não são exibidas na timeline

    for channel_name, data in grouped_by_channel.items():
        # Só adicionar se tiver itens (peças vinculadas)
        if not data["items"]:
            continue
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
    # Contar linhas ativas (data final >= hoje) vs inativas (data final < hoje)
    today = timezone.localdate()
    active_lines = PlacementLine.objects.filter(
        campaign=campaign
    ).annotate(
        max_day=Max("days__date")
    ).filter(max_day__gte=today).count()

    inactive_lines = PlacementLine.objects.filter(
        campaign=campaign
    ).annotate(
        max_day=Max("days__date")
    ).filter(max_day__lt=today).count()

    on_count = active_lines
    off_count = inactive_lines

    # Gerar lista de meses do período
    from datetime import date
    from dateutil.relativedelta import relativedelta

    months_list = []
    month_names_pt = {
        1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
        5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
        9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
    }
    month_abbrev_pt = {
        1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr",
        5: "Mai", 6: "Jun", 7: "Jul", 8: "Ago",
        9: "Set", 10: "Out", 11: "Nov", 12: "Dez"
    }

    # Usar as datas configuradas na campanha (não as datas dos dados importados)
    start_date = campaign.start_date
    end_date = campaign.end_date

    if start_date and end_date:
        if hasattr(start_date, 'date'):
            start_date = start_date.date()
        if hasattr(end_date, 'date'):
            end_date = end_date.date()

        current = date(start_date.year, start_date.month, 1)
        end_month = date(end_date.year, end_date.month, 1)

        while current <= end_month:
            months_list.append({
                "year": current.year,
                "month": current.month,
                "name": month_names_pt[current.month],
                "abbrev": month_abbrev_pt[current.month],
                "key": f"{current.year}-{current.month:02d}",
            })
            current = current + relativedelta(months=1)

    return render(
        request,
        "web/contract_done.html",
        {
            "active": "timeline_campanhas",
            "page_title": "Timeline - Campanhas",
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
            "months_list": months_list,
            "filter_pieces": sorted(unique_piece_titles),
            "filter_channels": sorted(unique_channels),
            "filter_markets": sorted(unique_markets),
            "role": role,
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
                    # Log de plano de mídia importado
                    AuditLog.log(
                        AuditLog.EventType.MEDIA_PLAN_UPLOADED,
                        request=request,
                        cliente=campaign.cliente,
                        details={"campaign_id": campaign.id, "campaign_name": campaign.name},
                    )
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


@csrf_exempt
@login_required
@require_true_admin
def api_users(request: HttpRequest) -> HttpResponse:
    """API para criar usuários (POST)."""
    from accounts.models import User

    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Método não permitido"}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "JSON inválido"}, status=400)

    username = data.get("username", "").strip()
    email = data.get("email", "").strip()
    password = data.get("password", "").strip()
    first_name = data.get("first_name", "").strip()
    last_name = data.get("last_name", "").strip()
    role = data.get("role", "colaborador")
    is_active = data.get("is_active", True)

    if not username or not email or not password:
        return JsonResponse({"success": False, "error": "Usuário, e-mail e senha são obrigatórios"}, status=400)

    if role not in ("admin", "colaborador"):
        return JsonResponse({"success": False, "error": "Papel inválido"}, status=400)

    if User.objects.filter(username=username).exists():
        return JsonResponse({"success": False, "error": "Nome de usuário já existe"}, status=400)

    if User.objects.filter(email=email).exists():
        return JsonResponse({"success": False, "error": "E-mail já cadastrado"}, status=400)

    user = User.objects.create_user(
        username=username,
        email=email,
        password=password,
        first_name=first_name,
        last_name=last_name,
        role=role,
        is_active=is_active,
    )

    return JsonResponse({
        "success": True,
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
        }
    })


@csrf_exempt
@login_required
@require_true_admin
def api_user_detail(request: HttpRequest, user_id: int) -> HttpResponse:
    """API para editar (PUT) ou excluir (DELETE) usuário."""
    from accounts.models import User

    user = User.objects.filter(id=user_id).first()
    if user is None:
        return JsonResponse({"success": False, "error": "Usuário não encontrado"}, status=404)

    # Não permitir excluir/editar superusuários
    if user.is_superuser and request.user.id != user.id:
        return JsonResponse({"success": False, "error": "Não é possível modificar um superusuário"}, status=403)

    if request.method == "PUT":
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"success": False, "error": "JSON inválido"}, status=400)

        username = data.get("username", "").strip()
        email = data.get("email", "").strip()
        first_name = data.get("first_name", "").strip()
        last_name = data.get("last_name", "").strip()
        role = data.get("role", user.role)
        is_active = data.get("is_active", user.is_active)
        password = data.get("password", "").strip()

        if not username or not email:
            return JsonResponse({"success": False, "error": "Usuário e e-mail são obrigatórios"}, status=400)

        if role not in ("admin", "colaborador"):
            return JsonResponse({"success": False, "error": "Papel inválido"}, status=400)

        # Verificar duplicatas
        if User.objects.filter(username=username).exclude(id=user_id).exists():
            return JsonResponse({"success": False, "error": "Nome de usuário já existe"}, status=400)

        if User.objects.filter(email=email).exclude(id=user_id).exists():
            return JsonResponse({"success": False, "error": "E-mail já cadastrado"}, status=400)

        user.username = username
        user.email = email
        user.first_name = first_name
        user.last_name = last_name
        user.role = role
        user.is_active = is_active

        if password:
            user.set_password(password)

        user.save()

        return JsonResponse({
            "success": True,
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "role": user.role,
            }
        })

    elif request.method == "DELETE":
        # Não permitir auto-exclusão
        if user.id == request.user.id:
            return JsonResponse({"success": False, "error": "Não é possível excluir seu próprio usuário"}, status=400)

        user.delete()
        return JsonResponse({"success": True})

    return JsonResponse({"success": False, "error": "Método não permitido"}, status=405)


@login_required
def relatorios_clientes(request: HttpRequest) -> HttpResponse:
    """Lista os clientes para seleção de relatórios."""
    role = effective_role(request)

    if role == "cliente":
        cliente_id = effective_cliente_id(request)
        return redirect("web:relatorios_campanhas", cliente_id=cliente_id)

    clientes_com_campanhas = (
        Cliente.objects.filter(campaigns__isnull=False)
        .distinct()
        .annotate(
            total_campaigns=Count("campaigns"),
            total_investment=Sum("campaigns__total_budget"),
        )
        .order_by("nome")
    )

    return render(
        request,
        "web/relatorios_clientes.html",
        {
            "active": "relatorios",
            "page_title": "Relatórios",
            "clientes": clientes_com_campanhas,
        },
    )


@login_required
def relatorios_campanhas(request: HttpRequest, cliente_id: int) -> HttpResponse:
    """Lista campanhas de um cliente com checkboxes para seleção."""
    role = effective_role(request)

    if role == "cliente":
        user_cliente_id = effective_cliente_id(request)
        if int(user_cliente_id) != int(cliente_id):
            return redirect("web:relatorios_campanhas", cliente_id=user_cliente_id)

    cliente = Cliente.objects.filter(id=cliente_id).first()
    if cliente is None:
        return redirect("web:relatorios_clientes")

    campaigns = Campaign.objects.filter(cliente_id=cliente_id).select_related("cliente").order_by("-created_at")

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
            "investment": c.total_budget or totals.get("cost") or 0,
            "insertions": totals.get("insertions") or 0,
            "on_count": on_count,
            "off_count": off_count,
            "start": totals.get("min_date") or c.start_date,
            "end": totals.get("max_date") or c.end_date,
        })

    return render(
        request,
        "web/relatorios_campanhas.html",
        {
            "active": "relatorios",
            "page_title": f"Relatórios - {cliente.nome}",
            "cliente": cliente,
            "campaigns_with_stats": campaigns_with_stats,
            "show_back": role != "cliente",
        },
    )


@login_required
def relatorios_consolidado(request: HttpRequest) -> HttpResponse:
    """Exibe relatório consolidado das campanhas selecionadas."""
    role = effective_role(request)
    campaign_ids = request.GET.getlist("campaigns") or request.POST.getlist("campaigns")

    if not campaign_ids:
        return redirect("web:relatorios_clientes")

    campaign_ids = [int(cid) for cid in campaign_ids if cid.isdigit()]

    if role == "cliente":
        cliente_id = effective_cliente_id(request)
        campaigns = Campaign.objects.filter(id__in=campaign_ids, cliente_id=cliente_id).select_related("cliente")
    else:
        campaigns = Campaign.objects.filter(id__in=campaign_ids).select_related("cliente")

    if not campaigns.exists():
        return redirect("web:relatorios_clientes")

    first_campaign = campaigns.first()
    cliente = first_campaign.cliente if first_campaign else None

    # Totais consolidados
    totals = PlacementDay.objects.filter(placement_line__campaign__in=campaigns).aggregate(
        insertions=Sum("insertions"),
        impressions=Sum("impressions"),
        clicks=Sum("clicks"),
        cost=Sum("cost"),
        min_date=Min("date"),
        max_date=Max("date"),
    )

    investment = campaigns.aggregate(total=Sum("total_budget"))["total"] or 0

    # Contar linhas ativas (data final >= hoje) vs inativas (data final < hoje)
    today = timezone.localdate()
    on_count = PlacementLine.objects.filter(
        campaign__in=campaigns
    ).annotate(
        max_day=Max("days__date")
    ).filter(max_day__gte=today).count()

    off_count = PlacementLine.objects.filter(
        campaign__in=campaigns
    ).annotate(
        max_day=Max("days__date")
    ).filter(max_day__lt=today).count()

    # Investimento por região
    investment_by_market = (
        PlacementDay.objects.filter(placement_line__campaign__in=campaigns)
        .values("placement_line__market")
        .annotate(total_cost=Sum("cost"), total_insertions=Sum("insertions"))
        .order_by("-total_insertions")
    )

    markets_data = []
    total_insertions = sum(int(m["total_insertions"] or 0) for m in investment_by_market)
    colors = ["#6366f1", "#f59e0b", "#3b82f6", "#10b981", "#ef4444", "#8b5cf6", "#ec4899", "#14b8a6"]
    for i, m in enumerate(investment_by_market[:8]):
        market_name = (m["placement_line__market"] or "Outros").strip()
        if not market_name:
            market_name = "Outros"
        insertions = int(m["total_insertions"] or 0)
        pct = round((insertions / total_insertions * 100) if total_insertions > 0 else 0)
        markets_data.append({
            "name": market_name,
            "insertions": insertions,
            "cost": float(m["total_cost"] or 0),
            "pct": pct,
            "color": colors[i % len(colors)],
        })

    # Dados por canal
    by_channel = (
        PlacementDay.objects.filter(placement_line__campaign__in=campaigns)
        .values("placement_line__media_channel")
        .annotate(
            total_insertions=Sum("insertions"),
            total_cost=Sum("cost"),
            count_lines=Count("placement_line", distinct=True),
        )
        .order_by("-total_insertions")
    )

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

    channels_data = []
    for ch in by_channel:
        channel_key = ch["placement_line__media_channel"] or "other"
        channels_data.append({
            "name": channel_names.get(channel_key, channel_key.title()),
            "key": channel_key,
            "insertions": int(ch["total_insertions"] or 0),
            "cost": float(ch["total_cost"] or 0),
            "lines": ch["count_lines"],
        })

    # Timeline consolidada
    timeline_data = []
    lines_with_pieces = (
        PlacementLine.objects.filter(campaign__in=campaigns)
        .prefetch_related("placement_creatives__piece")
        .annotate(
            min_day=Min("days__date"),
            max_day=Max("days__date"),
            total_insertions=Sum("days__insertions"),
        )
        .filter(min_day__isnull=False)
        .order_by("market", "media_channel")
    )

    piece_colors = [
        "#fde047", "#86efac", "#93c5fd", "#fca5a5", "#c4b5fd",
        "#fdba74", "#67e8f9", "#f9a8d4", "#a3e635", "#fcd34d",
    ]
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

        linked_pieces = list(line.placement_creatives.select_related("piece").all())
        market = (line.market or "").strip()

        if linked_pieces:
            for pc in linked_pieces:
                piece = pc.piece
                duration_str = f'{piece.duration_sec}"' if piece.duration_sec else ""
                title = f"{piece.title} {duration_str}".strip()
                grouped_by_channel[channel]["items"].append({
                    "title": title,
                    "piece_code": piece.code,
                    "market": market,
                    "start": line.min_day,
                    "end": line.max_day,
                    "insertions": line.total_insertions or 0,
                    "color": get_piece_color(piece.code),
                })

    for channel_name, data in grouped_by_channel.items():
        if not data["items"]:
            continue
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

    # Gerar lista de meses
    from datetime import date as date_type
    from dateutil.relativedelta import relativedelta

    months_list = []
    month_names_pt = {
        1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
        5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
        9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
    }

    start_date = totals.get("min_date")
    end_date = totals.get("max_date")

    if start_date and end_date:
        current = date_type(start_date.year, start_date.month, 1)
        end_month = date_type(end_date.year, end_date.month, 1)

        while current <= end_month:
            months_list.append({
                "year": current.year,
                "month": current.month,
                "name": month_names_pt[current.month],
                "key": f"{current.year}-{current.month:02d}",
            })
            current = current + relativedelta(months=1)

    return render(
        request,
        "web/relatorios_consolidado.html",
        {
            "active": "relatorios",
            "page_title": "Relatório Consolidado",
            "cliente": cliente,
            "campaigns": campaigns,
            "campaign_ids": campaign_ids,
            "totals": {
                "investment": investment,
                "insertions": totals.get("insertions") or 0,
                "impressions": totals.get("impressions") or 0,
                "cost": totals.get("cost") or 0,
                "start": totals.get("min_date"),
                "end": totals.get("max_date"),
            },
            "stats": {
                "on_count": on_count,
                "off_count": off_count,
                "total_campaigns": campaigns.count(),
            },
            "markets_data": markets_data,
            "channels_data": channels_data,
            "timeline_data": timeline_data,
            "months_list": months_list,
        },
    )


@login_required
@require_admin
def uploads_midia_clientes(request: HttpRequest) -> HttpResponse:
    """Lista os clientes para upload de mídia."""
    clientes_com_campanhas = (
        Cliente.objects.filter(campaigns__isnull=False)
        .distinct()
        .annotate(
            total_campaigns=Count("campaigns"),
            active_campaigns=Count("campaigns", filter=models.Q(campaigns__status="active")),
        )
        .order_by("nome")
    )

    return render(
        request,
        "web/uploads_midia_clientes.html",
        {
            "active": "uploads_planilhas",
            "page_title": "Upload de Mídia",
            "clientes": clientes_com_campanhas,
        },
    )


@login_required
@require_admin
def uploads_midia_campanhas(request: HttpRequest, cliente_id: int) -> HttpResponse:
    """Lista campanhas de um cliente para upload de mídia."""
    cliente = Cliente.objects.filter(id=cliente_id).first()
    if cliente is None:
        return redirect("web:uploads_midia_clientes")

    campaigns = Campaign.objects.filter(cliente_id=cliente_id).order_by("-created_at")

    campaigns_with_stats = []
    today = timezone.localdate()
    for c in campaigns:
        totals = PlacementDay.objects.filter(placement_line__campaign=c).aggregate(
            min_date=Min("date"),
            max_date=Max("date"),
        )
        pieces_count = c.pieces.count()
        pieces_with_assets = c.pieces.filter(assets__isnull=False).distinct().count()

        campaigns_with_stats.append({
            "campaign": c,
            "pieces_count": pieces_count,
            "pieces_with_assets": pieces_with_assets,
            "start": totals.get("min_date") or c.start_date,
            "end": totals.get("max_date") or c.end_date,
            "is_active": c.status == "active",
        })

    return render(
        request,
        "web/uploads_midia_campanhas.html",
        {
            "active": "uploads_planilhas",
            "page_title": f"Upload de Mídia - {cliente.nome}",
            "cliente": cliente,
            "campaigns_with_stats": campaigns_with_stats,
        },
    )


@login_required
@require_admin
def uploads_midia_pecas(request: HttpRequest, campaign_id: int) -> HttpResponse:
    """Exibe peças da campanha para upload de mídia via drag-and-drop."""
    campaign = Campaign.objects.filter(id=campaign_id).select_related("cliente").first()
    if campaign is None:
        return redirect("web:uploads_midia_clientes")

    pieces = campaign.pieces.prefetch_related("assets").order_by("code")

    pieces_data = []
    for piece in pieces:
        assets = list(piece.assets.order_by("-created_at")[:5])
        last_asset = assets[0] if assets else None

        # Determinar tipo de mídia baseado nos assets
        media_types = set()
        for asset in assets:
            meta = asset.metadata or {}
            content_type = meta.get("content_type", "")
            if "video" in content_type:
                media_types.add("video")
            elif "audio" in content_type:
                media_types.add("audio")
            elif "image" in content_type:
                media_types.add("image")

        pieces_data.append({
            "piece": piece,
            "assets": assets,
            "assets_count": piece.assets.count(),
            "last_asset": last_asset,
            "media_types": list(media_types),
            "has_video": "video" in media_types,
            "has_audio": "audio" in media_types,
            "has_image": "image" in media_types,
        })

    return render(
        request,
        "web/uploads_midia_pecas.html",
        {
            "active": "uploads_planilhas",
            "page_title": f"Peças - {campaign.name}",
            "campaign": campaign,
            "cliente": campaign.cliente,
            "pieces_data": pieces_data,
        },
    )


@csrf_exempt
@login_required
@require_admin
def api_upload_piece_asset(request: HttpRequest, piece_id: int) -> HttpResponse:
    """API para upload de arquivo de mídia para uma peça."""
    if request.method != "POST":
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    piece = Piece.objects.filter(id=piece_id).select_related("campaign").first()
    if piece is None:
        return JsonResponse({"error": "piece_not_found"}, status=404)

    files = request.FILES.getlist("file") or request.FILES.getlist("files")
    if not files:
        return JsonResponse({"error": "no_file"}, status=400)

    from campaigns.services import compute_sha256, infer_piece_type_from_filename, try_ffprobe, extract_duration_sec_from_ffprobe
    from campaigns.models import CreativeAsset

    created_assets = []
    for f in files:
        checksum = compute_sha256(f)
        if checksum and CreativeAsset.objects.filter(piece=piece, checksum=checksum).exists():
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

        # Tentar extrair duração com ffprobe
        try:
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
        except Exception:
            pass

        created_assets.append({
            "id": asset.id,
            "url": asset.file.url if asset.file else None,
            "name": getattr(f, "name", ""),
            "content_type": getattr(f, "content_type", ""),
        })

    # Log de assets enviados
    if created_assets:
        AuditLog.log(
            AuditLog.EventType.ASSET_UPLOADED,
            request=request,
            cliente=piece.campaign.cliente if piece.campaign else None,
            details={
                "piece_id": piece.id,
                "piece_code": piece.code,
                "assets_count": len(created_assets),
            },
        )

    return JsonResponse({
        "ok": True,
        "created": len(created_assets),
        "assets": created_assets,
    })


@login_required
def campanha_detalhe(request: HttpRequest, campaign_id: int) -> HttpResponse:
    """Exibe detalhes da campanha com abas e cards de peças."""
    from django.db.models import Sum, Min, Max
    from django.utils import timezone as tz

    campaign = Campaign.objects.filter(id=campaign_id).select_related("cliente").first()
    if campaign is None:
        return redirect("web:campanhas")

    today = tz.now().date()
    pieces = campaign.pieces.prefetch_related("assets", "placement_creatives__placement_line__days").order_by("code")

    # Calcular estatísticas da campanha
    total_insertions = PlacementDay.objects.filter(
        placement_line__campaign=campaign
    ).aggregate(total=Sum("insertions"))["total"] or 0

    total_cost = PlacementDay.objects.filter(
        placement_line__campaign=campaign
    ).aggregate(total=Sum("cost"))["total"] or 0

    # Preparar dados das peças
    pieces_data = []
    pieces_on = 0
    pieces_off = 0

    for piece in pieces:
        assets = list(piece.assets.order_by("-created_at")[:1])
        first_asset = assets[0] if assets else None

        # Pegar canais/meios das linhas vinculadas
        channels = set()
        markets = set()
        piece_insertions = 0
        piece_start = None
        piece_end = None

        for pc in piece.placement_creatives.all():
            line = pc.placement_line
            if line.media_channel:
                channel_display = line.get_media_channel_display() if hasattr(line, 'get_media_channel_display') else line.media_channel
                channels.add(channel_display.replace("_", " ").title())
            if line.market:
                markets.add(line.market)

            # Somar inserções dos dias desta linha
            for day in line.days.all():
                piece_insertions += day.insertions or 0
                if piece_start is None or day.date < piece_start:
                    piece_start = day.date
                if piece_end is None or day.date > piece_end:
                    piece_end = day.date

        # Determinar se está ON ou OFF baseado nas datas
        is_on = False
        if piece_end and piece_end >= today:
            is_on = True
            pieces_on += 1
        else:
            pieces_off += 1

        # Determinar tipo de mídia baseado nos assets
        media_type = None
        thumb_url = None
        if first_asset:
            meta = first_asset.metadata or {}
            content_type = meta.get("content_type", "")
            if "video" in content_type:
                media_type = "video"
            elif "audio" in content_type:
                media_type = "audio"
            elif "image" in content_type:
                media_type = "image"
            if first_asset.file:
                thumb_url = first_asset.file.url

        # Formato baseado no tipo e duração
        format_text = ""
        if piece.type == "video":
            format_text = f"Vídeo {piece.duration_sec}s" if piece.duration_sec else "Vídeo"
        elif piece.type == "audio":
            format_text = f"Áudio {piece.duration_sec}s" if piece.duration_sec else "Áudio"
        elif piece.type == "image":
            format_text = "Imagem"
        else:
            format_text = f"{piece.duration_sec}s" if piece.duration_sec else "N/A"

        pieces_data.append({
            "piece": piece,
            "is_on": is_on,
            "channels": list(channels)[:3],
            "channels_text": " + ".join(list(channels)[:3]) if channels else "N/A",
            "markets": list(markets),
            "markets_text": " + ".join(list(markets)[:2]) if markets else "N/A",
            "insertions": piece_insertions,
            "start_date": piece_start,
            "end_date": piece_end,
            "format_text": format_text,
            "media_type": media_type,
            "thumb_url": thumb_url,
            "has_asset": first_asset is not None,
        })

    # Calcular há quanto tempo foi atualizado
    updated_diff = tz.now() - campaign.updated_at
    if updated_diff.days > 0:
        updated_text = f"há {updated_diff.days} dia{'s' if updated_diff.days > 1 else ''}"
    elif updated_diff.seconds >= 3600:
        hours = updated_diff.seconds // 3600
        updated_text = f"há {hours} hora{'s' if hours > 1 else ''}"
    else:
        minutes = max(1, updated_diff.seconds // 60)
        updated_text = f"há {minutes} min"

    # Obter praças e meios únicos da campanha
    lines = PlacementLine.objects.filter(campaign=campaign)
    all_markets = set(lines.values_list("market", flat=True))
    all_channels = set()
    for line in lines:
        if line.media_channel:
            ch = line.get_media_channel_display() if hasattr(line, 'get_media_channel_display') else line.media_channel
            all_channels.add(ch.replace("_", " ").title())

    return render(
        request,
        "web/campanha_detalhe.html",
        {
            "active": "pecas_criativos",
            "page_title": f"{campaign.cliente.nome} • {campaign.name}",
            "campaign": campaign,
            "cliente": campaign.cliente,
            "pieces_data": pieces_data,
            "stats": {
                "budget": campaign.total_budget or 0,
                "cost": total_cost,
                "pieces_total": pieces.count(),
                "pieces_on": pieces_on,
                "pieces_off": pieces_off,
                "insertions": total_insertions,
                "updated_text": updated_text,
            },
            "campaign_markets": " + ".join(list(all_markets)[:4]) if all_markets else "N/A",
            "campaign_channels": " + ".join(list(all_channels)[:4]) if all_channels else "N/A",
            "tab": request.GET.get("tab", "pecas"),
        },
    )


@login_required
def peca_detalhe(request: HttpRequest, piece_id: int) -> HttpResponse:
    """Exibe detalhes completos de uma peça/comercial."""
    from django.db.models import Sum, Min, Max
    from django.utils import timezone as tz

    piece = Piece.objects.filter(id=piece_id).select_related("campaign__cliente").first()
    if piece is None:
        return redirect("web:campanhas")

    campaign = piece.campaign
    cliente = campaign.cliente
    today = tz.now().date()

    # Buscar todos os assets da peça
    assets = list(piece.assets.order_by("-created_at"))
    primary_asset = assets[0] if assets else None

    # Determinar tipo de mídia
    media_type = None
    media_url = None
    if primary_asset:
        meta = primary_asset.metadata or {}
        content_type = meta.get("content_type", "")
        if "video" in content_type:
            media_type = "video"
        elif "audio" in content_type:
            media_type = "audio"
        elif "image" in content_type:
            media_type = "image"
        if primary_asset.file:
            media_url = primary_asset.file.url

    # Buscar informações das linhas de veiculação vinculadas
    placement_creatives = piece.placement_creatives.select_related("placement_line").prefetch_related("placement_line__days")

    channels = set()
    markets = set()
    programs = []
    total_insertions = 0
    total_cost = 0
    piece_start = None
    piece_end = None
    veiculacao_data = []

    for pc in placement_creatives:
        line = pc.placement_line
        if line.media_channel:
            channel_display = line.get_media_channel_display() if hasattr(line, 'get_media_channel_display') else line.media_channel
            channels.add(channel_display.replace("_", " ").title())
        if line.market:
            markets.add(line.market)
        if line.channel:
            programs.append(line.channel)

        # Agregar dados dos dias
        line_insertions = 0
        line_cost = 0
        line_start = None
        line_end = None

        for day in line.days.all():
            line_insertions += day.insertions or 0
            line_cost += float(day.cost or 0)
            if line_start is None or day.date < line_start:
                line_start = day.date
            if line_end is None or day.date > line_end:
                line_end = day.date

        total_insertions += line_insertions
        total_cost += line_cost

        if piece_start is None or (line_start and line_start < piece_start):
            piece_start = line_start
        if piece_end is None or (line_end and line_end > piece_end):
            piece_end = line_end

        veiculacao_data.append({
            "channel": line.channel or line.get_media_channel_display() if hasattr(line, 'get_media_channel_display') else line.media_channel,
            "market": line.market,
            "program": line.program,
            "insertions": line_insertions,
            "cost": line_cost,
            "start": line_start,
            "end": line_end,
        })

    # Determinar se está ON ou OFF
    is_on = piece_end and piece_end >= today

    # Formato da peça
    format_parts = []
    if piece.type == "video":
        format_parts.append("Vídeo")
    elif piece.type == "audio":
        format_parts.append("Áudio")
    elif piece.type == "image":
        format_parts.append("Imagem")
    if piece.duration_sec:
        format_parts.append(f"{piece.duration_sec}s")
    format_text = " ".join(format_parts) if format_parts else "N/A"

    return render(
        request,
        "web/peca_detalhe.html",
        {
            "active": "campanhas",
            "page_title": piece.title,
            "piece": piece,
            "campaign": campaign,
            "cliente": cliente,
            "is_on": is_on,
            "media_type": media_type,
            "media_url": media_url,
            "assets": assets,
            "primary_asset": primary_asset,
            "channels": list(channels),
            "channels_text": " + ".join(list(channels)) if channels else "N/A",
            "markets": list(markets),
            "markets_text": " + ".join(list(markets)) if markets else "N/A",
            "programs": programs[:5],
            "total_insertions": total_insertions,
            "total_cost": total_cost,
            "piece_start": piece_start,
            "piece_end": piece_end,
            "format_text": format_text,
            "veiculacao_data": veiculacao_data,
        },
    )


@csrf_exempt
@login_required
@require_admin
def api_piece_update(request: HttpRequest, piece_id: int) -> HttpResponse:
    """API para atualizar dados de uma peça."""
    if request.method != "POST":
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    piece = Piece.objects.filter(id=piece_id).first()
    if piece is None:
        return JsonResponse({"error": "piece_not_found"}, status=404)

    import json
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid_json"}, status=400)

    # Atualizar campos permitidos
    if "title" in data:
        piece.title = data["title"]
    if "code" in data:
        piece.code = data["code"]
    if "duration_sec" in data:
        try:
            piece.duration_sec = int(data["duration_sec"])
        except (ValueError, TypeError):
            pass
    if "type" in data and data["type"] in ["video", "audio", "image"]:
        piece.type = data["type"]
    if "status" in data and data["status"] in ["pending", "approved", "archived"]:
        piece.status = data["status"]
    if "notes" in data:
        piece.notes = data["notes"]

    piece.save()

    return JsonResponse({
        "ok": True,
        "piece": {
            "id": piece.id,
            "title": piece.title,
            "code": piece.code,
            "duration_sec": piece.duration_sec,
            "type": piece.type,
            "status": piece.status,
            "notes": piece.notes,
        }
    })


@csrf_exempt
@login_required
@require_admin
def api_region_investments(request: HttpRequest, campaign_id: int) -> HttpResponse:
    """API para gerenciar investimentos por região de uma campanha."""
    campaign = Campaign.objects.filter(id=campaign_id).first()
    if campaign is None:
        return JsonResponse({"error": "campaign_not_found"}, status=404)

    if request.method == "GET":
        # Retorna os investimentos por região
        investments = campaign.region_investments.all().order_by("order", "region_name")
        data = [
            {
                "id": inv.id,
                "region_name": inv.region_name,
                "percentage": float(inv.percentage),
                "color": inv.color,
                "order": inv.order,
            }
            for inv in investments
        ]
        return JsonResponse({"ok": True, "investments": data})

    elif request.method == "POST":
        # Atualiza os investimentos por região
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "invalid_json"}, status=400)

        investments = data.get("investments", [])
        colors = ["#6366f1", "#f59e0b", "#3b82f6", "#10b981", "#ef4444", "#8b5cf6", "#ec4899", "#14b8a6"]

        # Remove investimentos existentes e recria
        campaign.region_investments.all().delete()

        created = []
        for i, inv in enumerate(investments):
            region_name = inv.get("region_name", "").strip()
            if not region_name:
                continue
            percentage = float(inv.get("percentage", 0))
            color = inv.get("color") or colors[i % len(colors)]

            region_inv = RegionInvestment.objects.create(
                campaign=campaign,
                region_name=region_name,
                percentage=percentage,
                color=color,
                order=i,
            )
            created.append({
                "id": region_inv.id,
                "region_name": region_inv.region_name,
                "percentage": float(region_inv.percentage),
                "color": region_inv.color,
                "order": region_inv.order,
            })

        return JsonResponse({"ok": True, "investments": created})

    return JsonResponse({"error": "method_not_allowed"}, status=405)
