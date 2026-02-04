from accounts.models import Cliente

from campaigns.models import Campaign, ContractUpload, MediaPlanUpload, PlacementCreative, PlacementLine
from campaigns.services import import_media_plan_xlsx, attach_assets_to_campaign, parse_media_plan_xlsx
from django.contrib.auth import get_user_model
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from .authz import effective_role, is_admin, require_admin
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
    return _render_module(request, active="campanhas", title="Campanhas")


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
    campaign = Campaign.objects.filter(id=campaign_id).first()
    if campaign is None:
        return redirect("web:clientes")
    last_upload = campaign.contract_uploads.order_by("-created_at").first()
    return render(
        request,
        "web/contract_done.html",
        {
            "active": "dashboard",
            "page_title": "Contrato de Upload",
            "campaign": campaign,
            "cliente": campaign.cliente,
            "last_upload": last_upload,
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
