from accounts.models import AuditLog, Cliente

from campaigns.models import Campaign, ContractUpload, CreativeAsset, FinancialUpload, MediaPlanUpload, Piece, PlacementCreative, PlacementDay, PlacementLine, RegionInvestment
from campaigns.services import import_financial_data, import_media_plan_xlsx, attach_assets_to_campaign, parse_financial_xlsx, parse_media_plan_xlsx
from datetime import datetime, timedelta
from django.contrib.auth import get_user_model
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.db import models
from django.db.models.functions import TruncMonth
from django.db.models import Count, Max, Min, Sum
from django.db.models.functions import TruncDate, TruncHour
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.views.decorators.csrf import csrf_exempt
import json

from .authz import effective_cliente_id, effective_role, is_admin, require_admin, require_true_admin, selected_cliente_id
from .forms import (
    CampaignEditForm,
    CampaignWizardForm,
    ClienteForm,
    ClienteUserCreateForm,
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


def login_cliente_view(request: HttpRequest, cliente_slug: str) -> HttpResponse:
    """Login personalizado para cliente com logo próprio."""
    cliente = Cliente.objects.filter(slug__iexact=cliente_slug, ativo=True).first()
    if cliente is None:
        return redirect("web:login")

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
                AuditLog.log(
                    AuditLog.EventType.LOGIN_FAILED,
                    request=request,
                    details={"login": login_value, "cliente_slug": cliente_slug},
                )
            else:
                auth_login(request, user)
                if not remember:
                    request.session.set_expiry(0)
                # Salvar o slug do cliente na sessão para redirecionamento no logout
                request.session["login_cliente_slug"] = cliente_slug
                AuditLog.log(
                    AuditLog.EventType.LOGIN,
                    request=request,
                    user=user,
                    cliente=user.cliente or cliente,
                    details={"login": login_value, "cliente_slug": cliente_slug},
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
        "web/login_cliente.html",
        {
            "page_title": f"Login - {cliente.nome}",
            "form_errors": form_errors,
            "next": next_url,
            "login_value": login_value,
            "remember": remember,
            "cliente": cliente,
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
    # Capturar o slug do cliente antes de limpar a sessão
    cliente_slug = request.session.get("login_cliente_slug")
    request.session.pop("impersonate_cliente_id", None)
    request.session.pop("login_cliente_slug", None)
    auth_logout(request)
    # Redirecionar para a tela de login personalizada se existir
    if cliente_slug:
        return redirect("web:login_cliente", cliente_slug=cliente_slug)
    return redirect("web:login")


# ---------------------------------------------------------------------------
# Recuperação de senha
# ---------------------------------------------------------------------------

def _send_password_reset_email(request: HttpRequest, user, cliente=None) -> None:
    """Gera token e envia e-mail de recuperação de senha."""
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    reset_url = request.build_absolute_uri(
        reverse("web:password_reset_confirm", kwargs={"uidb64": uid, "token": token})
    )
    context = {
        "user": user,
        "reset_url": reset_url,
        "cliente": cliente,
        "expiry_hours": 24,
    }
    subject = render_to_string("web/email/password_reset_subject.txt", context).strip()
    body_html = render_to_string("web/email/password_reset_body.html", context)
    send_mail(
        subject=subject,
        message="",
        from_email=None,  # usa DEFAULT_FROM_EMAIL
        recipient_list=[user.email],
        html_message=body_html,
        fail_silently=False,
    )


def password_reset_request(request: HttpRequest) -> HttpResponse:
    """Solicitar recuperação de senha (página geral)."""
    if request.user.is_authenticated:
        return redirect("web:root")

    sent = False
    error = ""

    if request.method == "POST":
        email = request.POST.get("email", "").strip()
        if not email:
            error = "Informe um endereço de e-mail."
        else:
            User = get_user_model()
            user = User.objects.filter(email__iexact=email, is_active=True).first()
            if user and user.email:
                try:
                    _send_password_reset_email(request, user)
                    AuditLog.log(
                        AuditLog.EventType.PASSWORD_RESET_REQUESTED,
                        request=request,
                        user=user,
                        cliente=getattr(user, "cliente", None),
                        details={"email": email},
                    )
                except Exception:
                    pass  # Não revelar falhas de envio
            # Sempre mostrar mensagem de sucesso (não revelar se e-mail existe)
            sent = True

    return render(request, "web/password_reset_request.html", {
        "page_title": "Recuperar Senha",
        "sent": sent,
        "error": error,
    })


def password_reset_request_cliente(request: HttpRequest, cliente_slug: str) -> HttpResponse:
    """Solicitar recuperação de senha com identidade visual do cliente."""
    if request.user.is_authenticated:
        return redirect("web:root")

    cliente = Cliente.objects.filter(slug__iexact=cliente_slug, ativo=True).first()
    if cliente is None:
        return redirect("web:password_reset_request")

    sent = False
    error = ""

    if request.method == "POST":
        email = request.POST.get("email", "").strip()
        if not email:
            error = "Informe um endereço de e-mail."
        else:
            User = get_user_model()
            user = User.objects.filter(email__iexact=email, is_active=True).first()
            if user and user.email:
                try:
                    _send_password_reset_email(request, user, cliente=cliente)
                    AuditLog.log(
                        AuditLog.EventType.PASSWORD_RESET_REQUESTED,
                        request=request,
                        user=user,
                        cliente=getattr(user, "cliente", None) or cliente,
                        details={"email": email, "cliente_slug": cliente_slug},
                    )
                except Exception:
                    pass
            sent = True

    return render(request, "web/password_reset_request_cliente.html", {
        "page_title": f"Recuperar Senha — {cliente.nome}",
        "sent": sent,
        "error": error,
        "cliente": cliente,
    })


def password_reset_confirm(request: HttpRequest, uidb64: str, token: str) -> HttpResponse:
    """Validar token e permitir nova senha."""
    if request.user.is_authenticated:
        return redirect("web:root")

    User = get_user_model()
    user = None
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (User.DoesNotExist, ValueError, TypeError, OverflowError):
        pass

    token_valid = user is not None and default_token_generator.check_token(user, token)

    error = ""
    if request.method == "POST" and token_valid:
        senha1 = request.POST.get("password1", "")
        senha2 = request.POST.get("password2", "")
        if not senha1:
            error = "Informe a nova senha."
        elif len(senha1) < 8:
            error = "A senha deve ter pelo menos 8 caracteres."
        elif senha1 != senha2:
            error = "As senhas não coincidem."
        else:
            user.set_password(senha1)
            user.save()
            AuditLog.log(
                AuditLog.EventType.PASSWORD_RESET_COMPLETED,
                request=request,
                user=user,
                cliente=getattr(user, "cliente", None),
                details={"method": "email_token"},
            )
            return redirect("web:password_reset_complete")

    return render(request, "web/password_reset_confirm.html", {
        "page_title": "Redefinir Senha",
        "token_valid": token_valid,
        "error": error,
        "uidb64": uidb64,
        "token": token,
    })


def password_reset_complete(request: HttpRequest) -> HttpResponse:
    """Confirmação de senha redefinida com sucesso."""
    return render(request, "web/password_reset_complete.html", {
        "page_title": "Senha Redefinida",
    })


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
    """Tela de Alertas - envio de mensagens para clientes."""
    from accounts.models import Alert
    from datetime import datetime, timedelta

    # Listar clientes ativos para o select
    clientes = Cliente.objects.filter(ativo=True).order_by("nome")

    # Filtros de data - padrão: últimos 30 dias
    hoje = timezone.now().date()
    trinta_dias_atras = hoje - timedelta(days=30)

    data_de = request.GET.get("data_de", trinta_dias_atras.isoformat())
    data_ate = request.GET.get("data_ate", hoje.isoformat())
    filtro_cliente = request.GET.get("filtro_cliente", "")

    try:
        data_de_parsed = datetime.strptime(data_de, "%Y-%m-%d").date()
        data_ate_parsed = datetime.strptime(data_ate, "%Y-%m-%d").date()
    except ValueError:
        data_de_parsed = trinta_dias_atras
        data_ate_parsed = hoje

    # Converter para datetime com timezone
    data_ate_dt = timezone.make_aware(datetime.combine(data_ate_parsed, datetime.max.time()))
    data_de_dt = timezone.make_aware(datetime.combine(data_de_parsed, datetime.min.time()))

    # Processar envio de alerta
    success_message = ""
    error_message = ""
    if request.method == "POST":
        cliente_id = request.POST.get("cliente_id")
        titulo = request.POST.get("titulo", "").strip()
        mensagem = request.POST.get("mensagem", "").strip()
        prioridade = request.POST.get("prioridade", "normal")

        if not cliente_id:
            error_message = "Selecione um cliente."
        elif not titulo:
            error_message = "Informe o título do alerta."
        elif not mensagem:
            error_message = "Informe a mensagem do alerta."
        else:
            cliente = Cliente.objects.filter(id=cliente_id).first()
            if cliente:
                Alert.objects.create(
                    cliente=cliente,
                    titulo=titulo,
                    mensagem=mensagem,
                    prioridade=prioridade,
                    enviado_por=request.user,
                )
                success_message = f"Alerta enviado para {cliente.nome} com sucesso!"
            else:
                error_message = "Cliente não encontrado."

    # Listar alertas com filtros
    alertas_qs = Alert.objects.select_related("cliente", "enviado_por", "lido_por").filter(
        criado_em__gte=data_de_dt,
        criado_em__lte=data_ate_dt,
    )

    if filtro_cliente:
        alertas_qs = alertas_qs.filter(cliente_id=filtro_cliente)

    alertas = alertas_qs.order_by("-criado_em")[:100]

    return render(
        request,
        "web/alertas.html",
        {
            "active": "administracao",
            "page_title": "Alertas",
            "clientes": clientes,
            "alertas": alertas,
            "success_message": success_message,
            "error_message": error_message,
            "data_de": data_de,
            "data_ate": data_ate,
            "filtro_cliente": filtro_cliente,
        },
    )


@login_required
def dashboard(request: HttpRequest) -> HttpResponse:
    role = effective_role(request)
    today = timezone.localdate()
    now = timezone.now()

    # Para admin/colaborador: prioridade sessão (sidebar) > query param
    qp_cliente = request.GET.get("cliente_id")
    sel_cliente = selected_cliente_id(request)
    active_cliente_filter = None
    clientes_list = []

    # Filtrar campanhas baseado no role
    if role == "cliente":
        cliente_id = effective_cliente_id(request)
        campaigns_qs = Campaign.objects.filter(cliente_id=cliente_id, status="active")
        cliente = Cliente.objects.filter(id=cliente_id).first()
        active_cliente_filter = cliente_id
    else:
        # Admin/Colaborador - listar clientes com campanhas
        clientes_list = list(
            Cliente.objects.filter(campaigns__isnull=False)
            .distinct()
            .annotate(
                total_campaigns=Count("campaigns", filter=models.Q(campaigns__status="active")),
            )
            .filter(total_campaigns__gt=0)
            .order_by("nome")
        )

        # Prioridade: sidebar selection > query param > mostrar tudo
        active_cliente_filter = sel_cliente or (int(qp_cliente) if qp_cliente else None)
        if active_cliente_filter:
            try:
                active_cliente_filter = int(active_cliente_filter)
                campaigns_qs = Campaign.objects.filter(cliente_id=active_cliente_filter, status="active")
                cliente = Cliente.objects.filter(id=active_cliente_filter).first()
            except (ValueError, TypeError):
                active_cliente_filter = None
                campaigns_qs = Campaign.objects.filter(status="active")
                cliente = None
        else:
            campaigns_qs = Campaign.objects.filter(status="active")
            cliente = None

    # Contadores
    total_campaigns = campaigns_qs.count()

    # Campanhas em andamento (now between start_date and end_date)
    campaigns_live = campaigns_qs.filter(start_date__lte=now, end_date__gte=now).count()

    # Praças ativas agora (markets distintos com inserções hoje ou no período atual)
    pracas_ativas = PlacementLine.objects.filter(
        campaign__in=campaigns_qs,
        days__date=today,
        days__insertions__gt=0,
    ).values("market").distinct().count()

    # Contar linhas ativas vs inativas
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

    # Totais consolidados (inserções planejadas = todas as inserções)
    totals = PlacementDay.objects.filter(placement_line__campaign__in=campaigns_qs).aggregate(
        insertions=Sum("insertions"),
        impressions=Sum("impressions"),
        clicks=Sum("clicks"),
        cost=Sum("cost"),
    )
    total_insertions_planned = totals.get("insertions") or 0

    # Inserções realizadas (até hoje)
    insertions_done = PlacementDay.objects.filter(
        placement_line__campaign__in=campaigns_qs,
        date__lte=today,
    ).aggregate(total=Sum("insertions"))["total"] or 0

    # Percentual de execução
    exec_percent = round((insertions_done / total_insertions_planned * 100), 1) if total_insertions_planned > 0 else 0

    # Investimento total (budget das campanhas)
    investment = campaigns_qs.aggregate(total=Sum("total_budget"))["total"] or 0

    # ========== DADOS PARA GRÁFICOS ==========

    # 1. Evolução de Inserções por Dia (seleção customizada ou últimos 30 dias)
    from datetime import datetime as _dt
    cmp_from_param = request.GET.get("cmp_from", "")
    cmp_to_param = request.GET.get("cmp_to", "")
    try:
        cmp_from = _dt.strptime(cmp_from_param, "%Y-%m-%d").date() if cmp_from_param else None
    except ValueError:
        cmp_from = None
    try:
        cmp_to = _dt.strptime(cmp_to_param, "%Y-%m-%d").date() if cmp_to_param else None
    except ValueError:
        cmp_to = None

    if not cmp_from or not cmp_to or cmp_from > cmp_to:
        cmp_to = today
        cmp_from = today - timedelta(days=30)

    # Current period series
    cur_days = []
    d = cmp_from
    while d <= cmp_to:
        cur_days.append(d)
        d += timedelta(days=1)
    cur_qs = (
        PlacementDay.objects.filter(
            placement_line__campaign__in=campaigns_qs,
            date__gte=cmp_from,
            date__lte=cmp_to,
        )
        .values("date")
        .annotate(total=Sum("insertions"))
    )
    cur_map = {row["date"]: int(row["total"] or 0) for row in cur_qs}
    days_labels = [d.strftime("%d/%m") for d in cur_days]
    days_insertions = [cur_map.get(d, 0) for d in cur_days]

    # Previous period series (mesmo tamanho imediatamente anterior)
    period_len = (cmp_to - cmp_from).days + 1
    prev_to = cmp_from - timedelta(days=1)
    prev_from = prev_to - timedelta(days=period_len - 1)
    prev_days = []
    d2 = prev_from
    while d2 <= prev_to:
        prev_days.append(d2)
        d2 += timedelta(days=1)
    prev_qs = (
        PlacementDay.objects.filter(
            placement_line__campaign__in=campaigns_qs,
            date__gte=prev_from,
            date__lte=prev_to,
        )
        .values("date")
        .annotate(total=Sum("insertions"))
    )
    prev_map = {row["date"]: int(row["total"] or 0) for row in prev_qs}
    cmp_previous = [prev_map.get(d, 0) for d in prev_days]

    # Resumo de comparação
    cur_total = sum(days_insertions)
    prev_total = sum(cmp_previous)
    if prev_total > 0:
        cmp_pct = round(((cur_total - prev_total) / prev_total) * 100, 1)
    else:
        cmp_pct = 0
    cmp_summary = {
        "from": cmp_from.strftime("%Y-%m-%d"),
        "to": cmp_to.strftime("%Y-%m-%d"),
        "cur_total": cur_total,
        "prev_total": prev_total,
        "pct": cmp_pct,
        "dir": "up" if cmp_pct > 0 else ("down" if cmp_pct < 0 else "neutral"),
    }

    # 1b. Evolução Mensal de Inserções (últimos 12 meses)
    from datetime import date
    def _month_shift(base: date, months: int) -> date:
        y = base.year + (base.month - 1 + months) // 12
        m = (base.month - 1 + months) % 12 + 1
        return date(y, m, 1)

    start_month = _month_shift(today.replace(day=1), -11)
    months_qs = (
        PlacementDay.objects.filter(
            placement_line__campaign__in=campaigns_qs,
            date__gte=start_month,
            date__lte=today,
        )
        .annotate(month=TruncMonth("date"))
        .values("month")
        .annotate(total=Sum("insertions"))
        .order_by("month")
    )
    months_map = {row["month"].strftime("%m/%y"): int(row["total"] or 0) for row in months_qs}
    months_labels = []
    months_insertions = []
    for i in range(12):
        m_date = _month_shift(start_month, i)
        label = m_date.strftime("%m/%y")
        months_labels.append(label)
        months_insertions.append(months_map.get(label, 0))

    # Comparativo mês atual vs anterior
    months_compare = {
        "cur_label": months_labels[-1] if months_labels else "",
        "prev_label": months_labels[-2] if len(months_labels) >= 2 else "",
        "cur": months_insertions[-1] if months_insertions else 0,
        "prev": months_insertions[-2] if len(months_insertions) >= 2 else 0,
        "delta": 0,
        "pct": 0,
        "dir": "neutral",
    }
    try:
        months_compare["delta"] = months_compare["cur"] - months_compare["prev"]
        if months_compare["prev"] > 0:
            pct = (months_compare["delta"] / months_compare["prev"]) * 100
            months_compare["pct"] = round(pct, 1)
            months_compare["dir"] = "up" if pct > 0 else ("down" if pct < 0 else "neutral")
        else:
            months_compare["pct"] = 0
            months_compare["dir"] = "neutral"
    except Exception:
        pass

    # 2. Investimento por Região (donut)
    region_investments = list(
        RegionInvestment.objects.filter(campaign__in=campaigns_qs)
        .values("region_name")
        .annotate(total_pct=Sum("percentage"))
        .order_by("-total_pct")[:8]
    )
    region_labels = [r["region_name"] for r in region_investments]
    region_values = [float(r["total_pct"]) for r in region_investments]

    # 3. Top 5 Praças por Inserção (barra horizontal)
    top_pracas = list(
        PlacementDay.objects.filter(placement_line__campaign__in=campaigns_qs)
        .values("placement_line__market")
        .annotate(total=Sum("insertions"))
        .order_by("-total")[:5]
    )
    pracas_labels = [p["placement_line__market"] for p in top_pracas]
    pracas_values = [p["total"] for p in top_pracas]

    # 4. Distribuição por Canal (media_channel)
    channel_dist = list(
        PlacementDay.objects.filter(placement_line__campaign__in=campaigns_qs)
        .values("placement_line__media_channel")
        .annotate(total=Sum("insertions"))
        .order_by("-total")
    )
    channel_labels_map = dict(PlacementLine.MediaChannel.choices)
    channel_labels = [channel_labels_map.get(c["placement_line__media_channel"], c["placement_line__media_channel"]) for c in channel_dist]
    channel_values = [c["total"] for c in channel_dist]

    # 5. Inserções por Peça - Top 5 criativos
    top_pieces = list(
        PlacementDay.objects.filter(
            placement_line__campaign__in=campaigns_qs,
            placement_line__placement_creatives__isnull=False,
        )
        .values(
            "placement_line__placement_creatives__piece__code",
            "placement_line__placement_creatives__piece__title",
        )
        .annotate(total=Sum("insertions"))
        .order_by("-total")[:5]
    )
    pieces_labels = [f"{p['placement_line__placement_creatives__piece__code']}" for p in top_pieces if p['placement_line__placement_creatives__piece__code']]
    pieces_values = [p["total"] for p in top_pieces if p['placement_line__placement_creatives__piece__code']]

    # 6. Heatmap - últimas 4 semanas (7 dias × 4 semanas)
    heatmap_weeks = []
    for week_offset in range(4):
        week_start = today - timedelta(days=today.weekday() + 7 * (3 - week_offset))
        week_data = []
        for day_offset in range(7):
            day_date = week_start + timedelta(days=day_offset)
            day_total = PlacementDay.objects.filter(
                placement_line__campaign__in=campaigns_qs,
                date=day_date,
            ).aggregate(total=Sum("insertions"))["total"] or 0
            week_data.append({"date": day_date.strftime("%d/%m"), "value": day_total})
        heatmap_weeks.append(week_data)

    return render(
        request,
        "web/dashboard.html",
        {
            "active": "dashboard",
            "page_title": "Dashboard",
            "role": role,
            "cliente": cliente,
            "clientes_list": clientes_list,
            "selected_cliente_id": active_cliente_filter,
            "stats": {
                "investment": investment,
                "on_count": on_count,
                "off_count": off_count,
                "cost": totals.get("cost") or 0,
                "insertions": total_insertions_planned,
                "insertions_done": insertions_done,
                "exec_percent": exec_percent,
                "total_campaigns": total_campaigns,
                "campaigns_live": campaigns_live,
                "pracas_ativas": pracas_ativas,
            },
            # Dados para gráficos
            "days_labels": json.dumps(days_labels),
            "days_insertions": json.dumps(days_insertions),
            "cmp_previous": json.dumps(cmp_previous),
            "cmp_summary": cmp_summary,
            "cmp_from": cmp_from.strftime("%Y-%m-%d"),
            "cmp_to": cmp_to.strftime("%Y-%m-%d"),
            "months_labels": json.dumps(months_labels),
            "months_insertions": json.dumps(months_insertions),
            "months_compare": months_compare,
            "region_labels": json.dumps(region_labels),
            "region_values": json.dumps(region_values),
            "pracas_labels": json.dumps(pracas_labels),
            "pracas_values": json.dumps(pracas_values),
            "channel_labels": json.dumps(channel_labels),
            "channel_values": json.dumps(channel_values),
            "pieces_labels": json.dumps(pieces_labels),
            "pieces_values": json.dumps(pieces_values),
            "heatmap_weeks": json.dumps(heatmap_weeks),
        },
    )


@login_required
def timeline_campanhas(request: HttpRequest) -> HttpResponse:
    role = effective_role(request)

    # Filtrar campanhas baseado no role
    if role == "cliente":
        cliente_id = effective_cliente_id(request)
        campaigns_qs = Campaign.objects.filter(cliente_id=cliente_id, status="active")
    else:
        sel_cliente = selected_cliente_id(request)
        if sel_cliente:
            campaigns_qs = Campaign.objects.filter(cliente_id=sel_cliente, status="active")
        else:
            campaigns_qs = Campaign.objects.filter(status="active")

    total_campaigns = campaigns_qs.count()

    return render(
        request,
        "web/timeline_campanhas.html",
        {
            "active": "timeline_campanhas",
            "page_title": "Timeline Campanhas",
            "stats": {
                "total_campaigns": total_campaigns,
            },
        },
    )


@login_required
def grupo_campanhas(request: HttpRequest) -> HttpResponse:
    """Lista os clientes em boxes para acessar suas campanhas."""
    role = effective_role(request)

    # Se for cliente, redireciona direto para suas campanhas
    if role == "cliente":
        cliente_id = effective_cliente_id(request)
        return redirect("web:campanhas_cliente", cliente_id=cliente_id)

    # Se admin selecionou cliente no sidebar, pula a página intermediária
    sel_cliente = selected_cliente_id(request)
    if sel_cliente:
        return redirect("web:campanhas_cliente", cliente_id=sel_cliente)

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

    campaigns = (
        Campaign.objects.filter(cliente_id=cliente_id, status=Campaign.Status.ACTIVE)
        .select_related("cliente", "financial_summary")
        .order_by("-created_at")
    )

    campaigns_with_stats = []
    for c in campaigns:
        totals = PlacementDay.objects.filter(placement_line__campaign=c).aggregate(
            insertions=Sum("insertions"),
            cost=Sum("cost"),
            min_date=Min("date"),
            max_date=Max("date"),
        )
        # Fallback de Investimento: budget cadastrado → custo de placement days →
        # total da planilha financeira (FinancialSummary.total_valor_tabela)
        investment_value = c.total_budget or totals.get("cost") or 0
        if not investment_value:
            fin_summary = getattr(c, "financial_summary", None)
            if fin_summary and fin_summary.total_valor_tabela:
                investment_value = fin_summary.total_valor_tabela
        on_count = PlacementLine.objects.filter(campaign=c, media_type="online").count()
        off_count = PlacementLine.objects.filter(campaign=c, media_type="offline").count()

        # Google/Meta Ads campaigns come from API sync and may not have PlacementLine
        # rows attached — they're inherently online, so force the classification.
        is_google_meta = c.name.startswith("Google Ads - ") or c.name.startswith("Meta Ads - ")

        # Classify campaign as ON / OFF / MIXED based on placement line counts
        if is_google_meta:
            media_kind = "on"
        elif on_count > 0 and off_count == 0:
            media_kind = "on"
        elif off_count > 0 and on_count == 0:
            media_kind = "off"
        elif on_count > 0 and off_count > 0:
            media_kind = "mixed"
        else:
            media_kind = "none"

        # Determine link: Google/Meta Ads campaigns → veiculação pages
        if c.name.startswith("Google Ads - "):
            link_url = reverse("web:veiculacao_google")
        elif c.name.startswith("Meta Ads - "):
            link_url = reverse("web:veiculacao_meta")
        else:
            link_url = reverse("web:contract_done", args=[c.id])

        campaigns_with_stats.append({
            "campaign": c,
            "cliente": c.cliente,
            "investment": investment_value,
            "insertions": totals.get("insertions") or 0,
            "on_count": on_count,
            "off_count": off_count,
            "media_kind": media_kind,
            "start": totals.get("min_date") or c.start_date,
            "end": totals.get("max_date") or c.end_date,
            "link_url": link_url,
        })

    # Counts per media kind for the filter pills
    media_counts = {
        "all": len(campaigns_with_stats),
        "on": sum(1 for c in campaigns_with_stats if c["media_kind"] == "on"),
        "off": sum(1 for c in campaigns_with_stats if c["media_kind"] == "off"),
        "mixed": sum(1 for c in campaigns_with_stats if c["media_kind"] == "mixed"),
    }

    return render(
        request,
        "web/campanhas.html",
        {
            "active": "campanhas",
            "page_title": f"Campanhas - {cliente.nome}",
            "cliente": cliente,
            "campaigns_with_stats": campaigns_with_stats,
            "media_counts": media_counts,
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

    # Se admin selecionou cliente no sidebar, pula a página intermediária
    sel_cliente = selected_cliente_id(request)
    if sel_cliente:
        return redirect("web:pecas_campanhas", cliente_id=sel_cliente)

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

        # Classify campaign as ON / OFF / MIXED based on placement line counts.
        # Google/Meta Ads campaigns come from API sync without PlacementLine rows
        # attached, so force them to "on".
        on_count = PlacementLine.objects.filter(campaign=c, media_type="online").count()
        off_count = PlacementLine.objects.filter(campaign=c, media_type="offline").count()
        is_google_meta = c.name.startswith("Google Ads - ") or c.name.startswith("Meta Ads - ")
        if is_google_meta:
            media_kind = "on"
        elif on_count > 0 and off_count == 0:
            media_kind = "on"
        elif off_count > 0 and on_count == 0:
            media_kind = "off"
        elif on_count > 0 and off_count > 0:
            media_kind = "mixed"
        else:
            media_kind = "none"

        campaigns_with_stats.append({
            "campaign": c,
            "total_pieces": total_pieces,
            "pieces_with_media": pieces_with_media,
            "pct": pct,
            "start": c.start_date,
            "end": c.end_date,
            "media_kind": media_kind,
        })

    media_counts = {
        "all": len(campaigns_with_stats),
        "on": sum(1 for c in campaigns_with_stats if c["media_kind"] == "on"),
        "off": sum(1 for c in campaigns_with_stats if c["media_kind"] == "off"),
        "mixed": sum(1 for c in campaigns_with_stats if c["media_kind"] == "mixed"),
    }

    return render(
        request,
        "web/pecas_campanhas.html",
        {
            "active": "pecas_criativos",
            "page_title": f"Peças & Criativos - {cliente.nome}",
            "cliente": cliente,
            "campaigns_with_stats": campaigns_with_stats,
            "media_counts": media_counts,
            "show_back": role != "cliente",
        },
    )


@login_required
def veiculacao(request: HttpRequest, platform: str = "all") -> HttpResponse:
    from integrations.models import GoogleAdsAccount, MetaAdsAccount

    role = effective_role(request)

    # Determine which client to filter by
    cliente_id = effective_cliente_id(request)
    if not cliente_id and is_admin(request.user):
        cliente_id = selected_cliente_id(request)

    # Platform-specific configuration
    google_channels = ["google", "youtube", "display", "search"]
    meta_channels = ["meta"]

    # Map of platform slug → (channels, page_title, table_title)
    platform_config = {
        "google": (google_channels, "Google Ads", "Campanhas Google Ads"),
        "meta": (meta_channels, "Meta Ads", "Campanhas Meta Ads"),
        "tiktok": (["tiktok"], "TikTok Ads", "Campanhas TikTok"),
        "linkedin": (["linkedin"], "LinkedIn Ads", "Campanhas LinkedIn"),
        "dv360": (["dv360"], "DV360", "Campanhas DV360"),
        "dv360_youtube": (["dv360_youtube"], "DV360 YouTube", "Campanhas DV360 YouTube"),
        "dv360_spotify": (["dv360_spotify"], "DV360 Spotify", "Campanhas DV360 Spotify"),
        "dv360_eletromidia": (["dv360_eletromid"], "DV360 Eletromidia", "Campanhas DV360 Eletromidia"),
        "dv360_netflix": (["dv360_netflix"], "DV360 Netflix", "Campanhas DV360 Netflix"),
        "dv360_globoplay": (["dv360_globoplay"], "DV360 Globoplay", "Campanhas DV360 Globoplay"),
        "dv360_admooh": (["dv360_admooh"], "DV360 AdMooh", "Campanhas DV360 AdMooh"),
    }

    if platform in platform_config:
        channels, page_title, table_title = platform_config[platform]
        active_key = f"veiculacao_{platform}"
        empty_msg = f"Nenhum dado de {page_title} encontrado. Importe dados ou conecte uma conta."
    else:
        channels = google_channels + meta_channels + ["tiktok", "linkedin", "dv360", "dv360_youtube", "dv360_spotify", "dv360_eletromid", "dv360_netflix", "dv360_globoplay", "dv360_admooh"]
        page_title = "Veiculacao"
        active_key = "veiculacao"
        table_title = "Campanhas Digitais"
        empty_msg = "Conecte suas contas ou importe dados para visualizar campanhas."

    # Platform-specific pages require a client to be selected
    require_cliente = (platform != "all") and not cliente_id
    if require_cliente:
        return render(
            request,
            "web/veiculacao.html",
            {
                "active": active_key,
                "page_title": page_title,
                "require_cliente": True,
            },
        )

    # Check if there are any connected accounts
    gads_qs = GoogleAdsAccount.objects.filter(is_active=True)
    mads_qs = MetaAdsAccount.objects.filter(is_active=True)
    if cliente_id:
        gads_qs = gads_qs.filter(cliente_id=cliente_id)
        mads_qs = mads_qs.filter(cliente_id=cliente_id)

    # For API-connected platforms, check accounts; for imported data, check if lines exist
    if platform == "google":
        has_accounts = gads_qs.exists()
    elif platform == "meta":
        has_accounts = mads_qs.exists()
    else:
        has_accounts = gads_qs.exists() or mads_qs.exists()

    # Also check if there are placement lines with data (for imported channels)
    if not has_accounts:
        imported_lines = PlacementLine.objects.filter(media_channel__in=channels)
        if cliente_id:
            imported_lines = imported_lines.filter(campaign__cliente_id=cliente_id)
        has_accounts = imported_lines.exists()

    # Fetch placement data
    lines_qs = PlacementLine.objects.filter(media_channel__in=channels)
    if cliente_id:
        lines_qs = lines_qs.filter(campaign__cliente_id=cliente_id)

    line_ids = list(lines_qs.values_list("id", flat=True))

    # Date filter
    date_from = request.GET.get("date_from", "")
    date_to = request.GET.get("date_to", "")
    days_qs = PlacementDay.objects.filter(placement_line_id__in=line_ids)
    if date_from:
        days_qs = days_qs.filter(date__gte=date_from)
    if date_to:
        days_qs = days_qs.filter(date__lte=date_to)

    # Aggregate stats
    stats = days_qs.aggregate(
        total_impressions=Sum("impressions"),
        total_clicks=Sum("clicks"),
        total_cost=Sum("cost"),
    )
    total_impressions = stats["total_impressions"] or 0
    total_clicks = stats["total_clicks"] or 0
    total_cost = stats["total_cost"] or 0
    ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0
    cpm = (float(total_cost) / total_impressions * 1000) if total_impressions > 0 else 0
    # Alcance estimado: unique reach ~ impressions / avg frequency (est. 3.5)
    alcance = int(total_impressions / 3.5) if total_impressions > 0 else 0

    # Campaigns table: per-PlacementLine aggregation
    # Pre-fetch piece counts per campaign to avoid N+1 queries
    campaign_ids_in_lines = lines_qs.values_list("campaign_id", flat=True).distinct()
    from django.db.models import Count as DjCount
    pieces_by_campaign = dict(
        Piece.objects.filter(campaign_id__in=campaign_ids_in_lines)
        .values_list("campaign_id")
        .annotate(cnt=DjCount("id"))
        .values_list("campaign_id", "cnt")
    )

    campaigns_data = []
    for line in lines_qs.select_related("campaign", "campaign__cliente"):
        line_days = days_qs.filter(placement_line=line)
        agg = line_days.aggregate(
            imp=Sum("impressions"),
            clk=Sum("clicks"),
            cst=Sum("cost"),
        )
        imp = agg["imp"] or 0
        clk = agg["clk"] or 0
        cst = float(agg["cst"] or 0)
        line_ctr = (clk / imp * 100) if imp > 0 else 0
        cpc = (cst / clk) if clk > 0 else 0
        plat_label = "Meta Ads" if line.media_channel in meta_channels else "Google Ads"
        camp_id = line.campaign_id
        campaigns_data.append({
            "id": line.id,
            "name": line.channel or line.property_text or f"Campaign #{line.external_ref}",
            "client": line.campaign.cliente.nome if line.campaign else "",
            "channel": line.get_media_channel_display(),
            "platform": plat_label,
            "impressions": imp,
            "clicks": clk,
            "ctr": round(line_ctr, 2),
            "cost": round(cst, 2),
            "cpc": round(cpc, 2),
            "external_ref": line.external_ref,
            "campaign_id": camp_id,
            "pieces_count": pieces_by_campaign.get(camp_id, 0),
        })

    # Daily metrics for chart
    daily_metrics = list(
        days_qs.values("date")
        .annotate(
            imp=Sum("impressions"),
            clk=Sum("clicks"),
            cst=Sum("cost"),
        )
        .order_by("date")
    )

    # Serialize for Chart.js
    chart_labels = [str(d["date"]) for d in daily_metrics]
    chart_impressions = [d["imp"] or 0 for d in daily_metrics]
    chart_clicks = [d["clk"] or 0 for d in daily_metrics]
    chart_cost = [float(d["cst"] or 0) for d in daily_metrics]

    # Cost per campaign for pie chart
    pie_labels = [c["name"] for c in campaigns_data if c["cost"] > 0]
    pie_values = [c["cost"] for c in campaigns_data if c["cost"] > 0]

    # Show platform column only when viewing all platforms
    show_platform_col = (platform == "all")

    # Find parent campaign for "Peças & Criativos" button
    parent_campaign_id = None
    if platform == "google" and cliente_id:
        pc = Campaign.objects.filter(
            cliente_id=cliente_id, name__startswith="Google Ads - "
        ).values_list("id", flat=True).first()
        parent_campaign_id = pc
    elif platform == "meta" and cliente_id:
        pc = Campaign.objects.filter(
            cliente_id=cliente_id, name__startswith="Meta Ads - "
        ).values_list("id", flat=True).first()
        parent_campaign_id = pc

    return render(
        request,
        "web/veiculacao.html",
        {
            "active": active_key,
            "page_title": page_title,
            "table_title": table_title,
            "empty_msg": empty_msg,
            "show_platform_col": show_platform_col,
            "has_accounts": has_accounts,
            "parent_campaign_id": parent_campaign_id,
            "user_is_admin": effective_role(request) != "cliente",
            "total_impressions": total_impressions,
            "total_clicks": total_clicks,
            "total_cost": total_cost,
            "ctr": round(ctr, 2),
            "cpm": round(cpm, 2),
            "alcance": alcance,
            "campaigns_data": campaigns_data,
            "chart_labels_json": json.dumps(chart_labels),
            "chart_impressions_json": json.dumps(chart_impressions),
            "chart_clicks_json": json.dumps(chart_clicks),
            "chart_cost_json": json.dumps(chart_cost),
            "pie_labels_json": json.dumps(pie_labels),
            "pie_values_json": json.dumps(pie_values),
            "date_from": date_from,
            "date_to": date_to,
        },
    )


@login_required
def dashon(request: HttpRequest) -> HttpResponse:
    """DashON – KPI overview dashboard for all digital platforms."""
    from collections import defaultdict
    from integrations.models import GoogleAdsAccount, MetaAdsAccount

    role = effective_role(request)
    cliente_id = effective_cliente_id(request)
    if not cliente_id and is_admin(request.user):
        cliente_id = selected_cliente_id(request)

    # Require a client to be selected
    if not cliente_id:
        return render(
            request,
            "web/dashon.html",
            {
                "active": "dashon",
                "page_title": "DashON",
                "require_cliente": True,
            },
        )

    # Check connected accounts
    gads_qs = GoogleAdsAccount.objects.filter(is_active=True)
    mads_qs = MetaAdsAccount.objects.filter(is_active=True)
    if cliente_id:
        gads_qs = gads_qs.filter(cliente_id=cliente_id)
        mads_qs = mads_qs.filter(cliente_id=cliente_id)
    has_accounts = gads_qs.exists() or mads_qs.exists()

    # Per-client module visibility
    from accounts.models import Cliente as _Cliente
    _cliente_obj = _Cliente.objects.filter(id=cliente_id).only("id", "dashon_hidden_modules").first()
    hidden_modules = list(_cliente_obj.dashon_hidden_modules or []) if _cliente_obj else []
    can_manage_modules = is_admin(request.user)

    # Digital channels
    google_channels = ["google", "youtube", "display", "search"]
    meta_channels = ["meta"]
    other_digital = ["tiktok", "linkedin", "dv360", "dv360_youtube", "dv360_spotify", "dv360_eletromid", "dv360_netflix", "dv360_globoplay", "dv360_admooh"]
    all_channels = google_channels + meta_channels + other_digital

    lines_qs = PlacementLine.objects.filter(media_channel__in=all_channels)
    if cliente_id:
        lines_qs = lines_qs.filter(campaign__cliente_id=cliente_id)

    line_ids = list(lines_qs.values_list("id", flat=True))

    # Date filter — no default range so all synced data is shown
    date_from = request.GET.get("date_from", "")
    date_to = request.GET.get("date_to", "")

    days_qs = PlacementDay.objects.filter(placement_line_id__in=line_ids)
    if date_from:
        days_qs = days_qs.filter(date__gte=date_from)
    if date_to:
        days_qs = days_qs.filter(date__lte=date_to)

    # ── Global stats ──
    stats = days_qs.aggregate(
        total_impressions=Sum("impressions"),
        total_clicks=Sum("clicks"),
        total_cost=Sum("cost"),
    )
    total_impressions = stats["total_impressions"] or 0
    total_clicks = stats["total_clicks"] or 0
    total_cost = float(stats["total_cost"] or 0)
    ctr = round((total_clicks / total_impressions * 100), 2) if total_impressions > 0 else 0
    cpc = round((total_cost / total_clicks), 2) if total_clicks > 0 else 0
    dashon_cpm = round((total_cost / total_impressions * 1000), 2) if total_impressions > 0 else 0
    dashon_alcance = int(total_impressions / 3.5) if total_impressions > 0 else 0
    active_campaigns = lines_qs.filter(
        id__in=days_qs.values_list("placement_line_id", flat=True).distinct()
    ).count()

    # ── Period comparison ──
    # compare=on  → user toggled the comparison switch
    # compare_from / compare_to → optional custom comparison dates
    compare_on = request.GET.get("compare", "") == "on"
    compare_from = request.GET.get("compare_from", "")
    compare_to = request.GET.get("compare_to", "")

    dashon_comparison = None
    def _pct(curr, prev):
        return round(((curr - prev) / prev) * 100, 1) if prev else None

    if compare_on:
        try:
            # Custom comparison range takes priority
            if compare_from and compare_to:
                prev_start = datetime.strptime(compare_from, "%Y-%m-%d").date()
                prev_end = datetime.strptime(compare_to, "%Y-%m-%d").date()
            elif date_from and date_to:
                # Auto: same-length period right before the selected range
                p_start = datetime.strptime(date_from, "%Y-%m-%d").date()
                p_end = datetime.strptime(date_to, "%Y-%m-%d").date()
                p_len = (p_end - p_start).days + 1
                prev_end = p_start - timedelta(days=1)
                prev_start = prev_end - timedelta(days=p_len - 1)
            else:
                # No date filter: last 30 days vs prior 30
                from datetime import date as _d
                p_end = _d.today()
                p_start = p_end - timedelta(days=29)
                p_len = 30
                prev_end = p_start - timedelta(days=1)
                prev_start = prev_end - timedelta(days=p_len - 1)

            prev_qs = PlacementDay.objects.filter(
                placement_line_id__in=line_ids, date__gte=prev_start, date__lte=prev_end,
            )
            prev_stats = prev_qs.aggregate(imp=Sum("impressions"), clk=Sum("clicks"), cst=Sum("cost"))
            prev_imp = prev_stats["imp"] or 0
            prev_clk = prev_stats["clk"] or 0
            prev_cost = float(prev_stats["cst"] or 0)
            prev_ctr = round((prev_clk / prev_imp * 100), 2) if prev_imp > 0 else 0
            prev_cpc = round((prev_cost / prev_clk), 2) if prev_clk > 0 else 0
            dashon_comparison = {
                "imp_change": _pct(total_impressions, prev_imp),
                "clk_change": _pct(total_clicks, prev_clk),
                "ctr_change": _pct(ctr, prev_ctr),
                "cost_change": _pct(total_cost, prev_cost),
                "cpc_change": _pct(cpc, prev_cpc),
                "prev_start": prev_start.strftime("%d/%m"),
                "prev_end": prev_end.strftime("%d/%m"),
                "period_label": f"{prev_start.strftime('%d/%m')} - {prev_end.strftime('%d/%m')}",
                # Raw dates for re-populating the form
                "prev_start_iso": prev_start.strftime("%Y-%m-%d"),
                "prev_end_iso": prev_end.strftime("%Y-%m-%d"),
                # Previous totals for the summary bar
                "prev_impressions": prev_imp,
                "prev_clicks": prev_clk,
                "prev_cost": round(prev_cost, 2),
                "prev_ctr": prev_ctr,
                "prev_cpc": prev_cpc,
            }
        except (ValueError, TypeError, ZeroDivisionError):
            pass

    # ── Campaign live status ──
    from datetime import date as _date_cls
    today = _date_cls.today()
    recent_days = PlacementDay.objects.filter(
        placement_line_id__in=line_ids, date__gte=today - timedelta(days=3),
    )
    live_line_ids = set(recent_days.values_list("placement_line_id", flat=True).distinct())
    campaigns_on = len(live_line_ids)
    campaigns_total = len(set(days_qs.values_list("placement_line_id", flat=True).distinct()))
    campaigns_off = campaigns_total - campaigns_on

    # (problem_campaigns and projections moved after campaigns_data is built)

    # ── Per-platform stats ──
    google_line_ids = list(lines_qs.filter(media_channel__in=google_channels).values_list("id", flat=True))
    meta_line_ids = list(lines_qs.filter(media_channel__in=meta_channels).values_list("id", flat=True))

    g_stats = days_qs.filter(placement_line_id__in=google_line_ids).aggregate(
        imp=Sum("impressions"), clk=Sum("clicks"), cst=Sum("cost"),
    )
    m_stats = days_qs.filter(placement_line_id__in=meta_line_ids).aggregate(
        imp=Sum("impressions"), clk=Sum("clicks"), cst=Sum("cost"),
    )

    def _plat(s):
        imp = s["imp"] or 0
        clk = s["clk"] or 0
        cst = float(s["cst"] or 0)
        return {
            "impressions": imp,
            "clicks": clk,
            "cost": round(cst, 2),
            "ctr": round((clk / imp * 100), 2) if imp > 0 else 0,
        }

    google_platform = _plat(g_stats)
    meta_platform = _plat(m_stats)

    # ── Trend data (daily, per platform) ──
    google_daily = defaultdict(lambda: {"imp": 0, "clk": 0, "cst": 0})
    meta_daily = defaultdict(lambda: {"imp": 0, "clk": 0, "cst": 0})

    for row in days_qs.filter(placement_line_id__in=google_line_ids).values("date").annotate(
        imp=Sum("impressions"), clk=Sum("clicks"), cst=Sum("cost"),
    ).order_by("date"):
        d = str(row["date"])
        google_daily[d] = {"imp": row["imp"] or 0, "clk": row["clk"] or 0, "cst": float(row["cst"] or 0)}

    for row in days_qs.filter(placement_line_id__in=meta_line_ids).values("date").annotate(
        imp=Sum("impressions"), clk=Sum("clicks"), cst=Sum("cost"),
    ).order_by("date"):
        d = str(row["date"])
        meta_daily[d] = {"imp": row["imp"] or 0, "clk": row["clk"] or 0, "cst": float(row["cst"] or 0)}

    all_dates = sorted(set(list(google_daily.keys()) + list(meta_daily.keys())))
    trend_labels = all_dates
    trend_google_imp = [google_daily[d]["imp"] for d in all_dates]
    trend_meta_imp = [meta_daily[d]["imp"] for d in all_dates]
    trend_google_cost = [google_daily[d]["cst"] for d in all_dates]
    trend_meta_cost = [meta_daily[d]["cst"] for d in all_dates]

    # ── Donut: investment by platform ──
    donut_labels = []
    donut_values = []
    if google_platform["cost"] > 0:
        donut_labels.append("Google Ads")
        donut_values.append(google_platform["cost"])
    if meta_platform["cost"] > 0:
        donut_labels.append("Meta Ads")
        donut_values.append(meta_platform["cost"])

    # ── Top 10 campaigns by investment ──
    campaigns_data = []
    for line in lines_qs.select_related("campaign", "campaign__cliente"):
        line_days = days_qs.filter(placement_line=line)
        agg = line_days.aggregate(imp=Sum("impressions"), clk=Sum("clicks"), cst=Sum("cost"))
        imp = agg["imp"] or 0
        clk = agg["clk"] or 0
        cst = float(agg["cst"] or 0)
        if imp == 0 and clk == 0 and cst == 0:
            continue
        line_ctr = round((clk / imp * 100), 2) if imp > 0 else 0
        line_cpc = round((cst / clk), 2) if clk > 0 else 0
        line_roi = round((clk / cst), 2) if cst > 0 else 0
        line_cpm = round((cst / imp * 1000), 2) if imp > 0 else 0
        platform = "Meta Ads" if line.media_channel in meta_channels else "Google Ads"
        campaigns_data.append({
            "id": line.id,
            "name": line.channel or line.property_text or f"Campaign #{line.external_ref}",
            "client": line.campaign.cliente.nome if line.campaign else "",
            "platform": platform,
            "impressions": imp,
            "clicks": clk,
            "ctr": line_ctr,
            "cost": round(cst, 2),
            "cpc": line_cpc,
            "roi": line_roi,
            "cpm": line_cpm,
        })
    campaigns_data.sort(key=lambda c: c["cost"], reverse=True)

    # Top 10 for bar chart
    top10 = campaigns_data[:10]
    bar_labels = [c["name"][:30] for c in top10]
    bar_values = [c["cost"] for c in top10]
    bar_colors = ["#1877F2" if c["platform"] == "Meta Ads" else "#FBBC04" for c in top10]

    # ── Channel performance comparison ──────────────────────────────
    channel_perf = []
    for ch_label, ch_ids in [("Google Ads", google_channels), ("Meta Ads", meta_channels)]:
        ch_line_ids = list(lines_qs.filter(media_channel__in=ch_ids).values_list("id", flat=True))
        if not ch_line_ids:
            continue
        ch_qs = days_qs.filter(placement_line_id__in=ch_line_ids)
        ch_stats = ch_qs.aggregate(imp=Sum("impressions"), clk=Sum("clicks"), cst=Sum("cost"))
        ch_imp = ch_stats["imp"] or 0
        ch_clk = ch_stats["clk"] or 0
        ch_cst = float(ch_stats["cst"] or 0)
        ch_ctr = round((ch_clk / ch_imp * 100), 2) if ch_imp > 0 else 0
        ch_cpc = round((ch_cst / ch_clk), 2) if ch_clk > 0 else 0
        ch_cpm = round((ch_cst / ch_imp * 1000), 2) if ch_imp > 0 else 0
        ch_roi = round((ch_clk / ch_cst), 2) if ch_cst > 0 else 0  # clicks per R$
        channel_perf.append({
            "channel": ch_label,
            "impressions": ch_imp,
            "clicks": ch_clk,
            "cost": round(ch_cst, 2),
            "ctr": ch_ctr,
            "cpc": ch_cpc,
            "cpm": ch_cpm,
            "roi": ch_roi,
        })

    # ── Problem campaigns & projections (needs campaigns_data) ──
    problem_campaigns = []
    for c in campaigns_data:
        if c["cost"] > 0 and c["ctr"] < 1.0:
            problem_campaigns.append(c["name"])

    days_in_period = max(1, len(set(d["date"] for d in days_qs.values("date"))))
    daily_avg_cost = total_cost / days_in_period if days_in_period > 0 else 0
    days_left_month = 30 - today.day
    projected_monthly_cost = round(total_cost + (daily_avg_cost * max(0, days_left_month)), 2)
    projected_monthly_clicks = int(total_clicks + ((total_clicks / days_in_period) * max(0, days_left_month))) if days_in_period > 0 else 0
    projected_roi = round(projected_monthly_clicks / projected_monthly_cost, 2) if projected_monthly_cost > 0 else 0

    # ── Top campaigns by ROI (clicks / cost) ───────────────────────
    top_roi = []
    for c in campaigns_data:
        if c["cost"] > 0:
            c_roi = round(c["clicks"] / c["cost"], 2)
            top_roi.append({**c, "roi": c_roi})
    top_roi.sort(key=lambda x: x["roi"], reverse=True)
    top_roi = top_roi[:10]

    # Average ROI across all campaigns with spend
    total_roi_campaigns = [c for c in campaigns_data if c["cost"] > 0]
    avg_roi = round(
        sum(c["clicks"] / c["cost"] for c in total_roi_campaigns) / len(total_roi_campaigns), 2
    ) if total_roi_campaigns else 0
    total_roi = round(total_clicks / total_cost, 2) if total_cost > 0 else 0

    # ── Smart Insights (deterministic) ──────────────────────────────
    smart_insights = []
    # Best and worst campaigns
    if campaigns_data:
        best_camp = max(campaigns_data, key=lambda c: c.get("roi", 0))
        if best_camp.get("roi", 0) > 0:
            smart_insights.append({
                "type": "positive",
                "icon": "trophy",
                "title": f"Melhor campanha: \"{best_camp['name'][:40]}\"",
                "text": f"ROI de {best_camp['roi']} cliques/R$ com CTR de {best_camp['ctr']}%",
            })
        worst_ctr = [c for c in campaigns_data if c["cost"] > 10]
        if worst_ctr:
            worst_camp = min(worst_ctr, key=lambda c: c["ctr"])
            if worst_camp["ctr"] < 2.0:
                smart_insights.append({
                    "type": "warning",
                    "icon": "alert",
                    "title": f"CTR baixo: \"{worst_camp['name'][:40]}\"",
                    "text": f"CTR de apenas {worst_camp['ctr']}% — considere revisar criativos ou segmentacao",
                })
        # Highest CPC
        high_cpc = max(campaigns_data, key=lambda c: c.get("cpc", 0))
        if high_cpc.get("cpc", 0) > cpc * 1.5 and cpc > 0:
            smart_insights.append({
                "type": "negative",
                "icon": "trending-up",
                "title": f"CPC elevado: \"{high_cpc['name'][:40]}\"",
                "text": f"R$ {high_cpc['cpc']:.2f} por clique — {round(high_cpc['cpc']/cpc*100-100)}% acima da media geral",
            })
    # CTR trend vs previous period
    if dashon_comparison and dashon_comparison.get("ctr_change") is not None:
        ctr_ch = dashon_comparison["ctr_change"]
        if ctr_ch < -10:
            smart_insights.append({
                "type": "negative",
                "icon": "trending-down",
                "title": f"CTR caiu {ctr_ch}% vs periodo anterior",
                "text": "Revise os criativos e segmentacao das campanhas com queda",
            })
        elif ctr_ch > 10:
            smart_insights.append({
                "type": "positive",
                "icon": "trending-up",
                "title": f"CTR subiu +{ctr_ch}% vs periodo anterior",
                "text": "Bom desempenho — mantenha a estrategia atual",
            })
    # CPC trend
    if dashon_comparison and dashon_comparison.get("cpc_change") is not None:
        cpc_ch = dashon_comparison["cpc_change"]
        if cpc_ch > 15:
            smart_insights.append({
                "type": "warning",
                "icon": "dollar",
                "title": f"CPC aumentou +{cpc_ch}% vs periodo anterior",
                "text": f"CPC atual R$ {cpc:.2f} — considere ajustar lances",
            })
    # Reallocation recommendation
    if len(campaigns_data) >= 2:
        with_roi = [c for c in campaigns_data if c.get("roi", 0) > 0]
        if len(with_roi) >= 2:
            best_r = max(with_roi, key=lambda c: c["roi"])
            worst_r = min(with_roi, key=lambda c: c["roi"])
            if best_r["roi"] > worst_r["roi"] * 2:
                realloc = min(round(worst_r["cost"] * 0.2, 2), 500)
                smart_insights.append({
                    "type": "info",
                    "icon": "shuffle",
                    "title": f"Realocar R$ {realloc:.0f} de \"{worst_r['name'][:25]}\"",
                    "text": f"Para \"{best_r['name'][:25]}\" que tem ROI {best_r['roi']}x vs {worst_r['roi']}x",
                })

    # ── Ad-level drill-down data ──────────────────────────────
    from campaigns.models import AdGroup, AdGroupDay, Ad, AdDay
    ads_by_campaign = {}
    for c in campaigns_data[:20]:  # limit to top 20 campaigns
        line_id = c["id"]
        ad_groups = AdGroup.objects.filter(placement_line_id=line_id).select_related("placement_line")
        campaign_ads = []
        for ag in ad_groups:
            ag_days = AdGroupDay.objects.filter(ad_group=ag)
            if date_from:
                ag_days = ag_days.filter(date__gte=date_from)
            if date_to:
                ag_days = ag_days.filter(date__lte=date_to)
            agg = ag_days.aggregate(imp=Sum("impressions"), clk=Sum("clicks"), cst=Sum("cost"))
            a_imp = agg["imp"] or 0
            a_clk = agg["clk"] or 0
            a_cst = float(agg["cst"] or 0)
            if a_imp == 0 and a_clk == 0:
                continue
            campaign_ads.append({
                "name": ag.name,
                "type": "Ad Group",
                "status": ag.status,
                "impressions": a_imp,
                "clicks": a_clk,
                "ctr": round((a_clk / a_imp * 100), 2) if a_imp > 0 else 0,
                "cost": round(a_cst, 2),
                "cpc": round((a_cst / a_clk), 2) if a_clk > 0 else 0,
            })
        if campaign_ads:
            ads_by_campaign[str(line_id)] = campaign_ads

    # ── Daily breakdown per campaign for drill-down chart ──
    campaign_daily = {}
    for c in campaigns_data[:10]:
        line_id = c["id"]
        daily = list(
            days_qs.filter(placement_line_id=line_id)
            .values("date")
            .annotate(imp=Sum("impressions"), clk=Sum("clicks"), cst=Sum("cost"))
            .order_by("date")
        )
        if daily:
            campaign_daily[str(line_id)] = {
                "labels": [str(d["date"]) for d in daily],
                "impressions": [d["imp"] or 0 for d in daily],
                "clicks": [d["clk"] or 0 for d in daily],
                "cost": [float(d["cst"] or 0) for d in daily],
            }

    return render(
        request,
        "web/dashon.html",
        {
            "active": "dashon",
            "page_title": "DashON",
            "has_accounts": has_accounts,
            "date_from": date_from,
            "date_to": date_to,
            "compare_on": compare_on,
            "compare_from": compare_from,
            "compare_to": compare_to,
            # Global stats
            "total_impressions": total_impressions,
            "total_clicks": total_clicks,
            "total_cost": round(total_cost, 2),
            "ctr": ctr,
            "cpc": cpc,
            "cpm": dashon_cpm,
            "alcance": dashon_alcance,
            "active_campaigns": active_campaigns,
            # Platform stats
            "google": google_platform,
            "meta": meta_platform,
            # Charts JSON
            "trend_labels_json": json.dumps(trend_labels),
            "trend_google_imp_json": json.dumps(trend_google_imp),
            "trend_meta_imp_json": json.dumps(trend_meta_imp),
            "trend_google_cost_json": json.dumps(trend_google_cost),
            "trend_meta_cost_json": json.dumps(trend_meta_cost),
            "donut_labels_json": json.dumps(donut_labels),
            "donut_values_json": json.dumps(donut_values),
            "bar_labels_json": json.dumps(bar_labels),
            "bar_values_json": json.dumps(bar_values),
            "bar_colors_json": json.dumps(bar_colors),
            # Table
            "campaigns_data": campaigns_data,
            # Channel comparison & ROI
            "channel_perf": channel_perf,
            "top_roi": top_roi,
            "avg_roi": avg_roi,
            "total_roi": total_roi,
            # Period comparison
            "comparison": dashon_comparison,
            # Live status
            "campaigns_on": campaigns_on,
            "campaigns_off": campaigns_off,
            "problem_campaigns": problem_campaigns,
            # Projections
            "daily_avg_cost": round(daily_avg_cost, 2),
            "projected_monthly_cost": projected_monthly_cost,
            "projected_monthly_clicks": projected_monthly_clicks,
            "projected_roi": projected_roi,
            # Smart insights
            "smart_insights": smart_insights,
            # Ad-level drill-down
            "ads_by_campaign_json": json.dumps(ads_by_campaign),
            "campaign_daily_json": json.dumps(campaign_daily),
            # Business KPIs (estimated - no conversion model yet)
            "total_roas": round(total_clicks * 0.05 / total_cost, 2) if total_cost > 0 else 0,  # estimated
            "cost_per_lead": round(total_cost / max(total_clicks * 0.03, 1), 2),  # est 3% conv rate
            "days_in_period": days_in_period,
            # Per-client module visibility
            "hidden_modules": hidden_modules,
            "can_manage_modules": can_manage_modules,
            "current_cliente_id": cliente_id,
        },
    )


# Allowed module IDs per page. Keep in sync with {% if 'X' in hidden_modules %} checks in templates.
DASHBOARD_TOGGLEABLE_MODULES = {
    "dashon": {
        "smart_insights", "kpi_primary", "kpi_secondary", "platform_strip",
        "live_status", "projection", "exec_summary",
        "charts", "channel_perf", "campaigns_table", "ai_insights",
    },
    "consolidated_on": {
        "filters", "hero_totals", "vehicles_grid", "trend_chart", "donut_chart",
        "bar_chart", "vehicles_table", "campaigns_table",
    },
}

# Maps page name -> (Cliente field name)
DASHBOARD_PAGE_FIELD = {
    "dashon": "dashon_hidden_modules",
    "consolidated_on": "consolidated_hidden_modules",
}


@login_required
def dashboard_toggle_module(request: HttpRequest) -> HttpResponse:
    """Admin-only: toggle visibility of a dashboard module for a specific cliente.

    Accepts POST: cliente_id, module_id, page (dashon|consolidated_on), hidden (0|1).
    """
    from django.http import JsonResponse
    from accounts.models import Cliente as _Cliente

    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "method"}, status=405)
    if not is_admin(request.user):
        return JsonResponse({"ok": False, "error": "forbidden"}, status=403)

    try:
        cliente_id = int(request.POST.get("cliente_id") or 0)
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "cliente_id"}, status=400)

    page = (request.POST.get("page") or "dashon").strip()
    module_id = (request.POST.get("module_id") or "").strip()
    hidden = (request.POST.get("hidden") or "").lower() in ("1", "true", "on", "yes")

    if page not in DASHBOARD_PAGE_FIELD:
        return JsonResponse({"ok": False, "error": "page"}, status=400)
    if module_id not in DASHBOARD_TOGGLEABLE_MODULES[page]:
        return JsonResponse({"ok": False, "error": "module_id"}, status=400)

    cliente = _Cliente.objects.filter(id=cliente_id).first()
    if not cliente:
        return JsonResponse({"ok": False, "error": "cliente"}, status=404)

    field_name = DASHBOARD_PAGE_FIELD[page]
    current = list(getattr(cliente, field_name) or [])
    if hidden and module_id not in current:
        current.append(module_id)
    elif not hidden and module_id in current:
        current = [m for m in current if m != module_id]
    setattr(cliente, field_name, current)
    cliente.save(update_fields=[field_name, "atualizado_em"])

    return JsonResponse({"ok": True, "page": page, "hidden": hidden, "module_id": module_id, "hidden_modules": current})


@login_required
def consolidated_on(request: HttpRequest) -> HttpResponse:
    """Consolidated ON – KPIs consolidados de todas as mídias digitais, por veículo."""
    from collections import defaultdict

    role = effective_role(request)
    cliente_id = effective_cliente_id(request)
    if not cliente_id and is_admin(request.user):
        cliente_id = selected_cliente_id(request)

    if not cliente_id:
        return render(request, "web/consolidated_on.html", {
            "active": "consolidated_on",
            "page_title": "Consolidated ON",
            "require_cliente": True,
        })

    # Per-client module visibility
    from accounts.models import Cliente as _Cliente
    _cliente_obj = _Cliente.objects.filter(id=cliente_id).only("id", "consolidated_hidden_modules").first()
    hidden_modules = list(_cliente_obj.consolidated_hidden_modules or []) if _cliente_obj else []
    can_manage_modules = is_admin(request.user)

    # All digital channels
    all_channels = [
        "google", "youtube", "display", "search", "meta",
        "tiktok", "linkedin", "dv360", "dv360_youtube", "dv360_spotify",
        "dv360_eletromid", "dv360_netflix", "dv360_globoplay", "dv360_admooh",
    ]

    # Human-readable labels and colors for each channel group
    channel_groups = {
        "google": {"label": "Google Ads", "channels": ["google", "youtube", "display", "search"], "color": "#FBBC04", "gradient": "linear-gradient(135deg,#FBBC04,#EA4335)"},
        "meta": {"label": "Meta Ads", "channels": ["meta"], "color": "#1877F2", "gradient": "linear-gradient(135deg,#1877F2,#0d65d9)"},
        "tiktok": {"label": "TikTok", "channels": ["tiktok"], "color": "#000000", "gradient": "linear-gradient(135deg,#25F4EE,#FE2C55)"},
        "linkedin": {"label": "LinkedIn", "channels": ["linkedin"], "color": "#0A66C2", "gradient": "linear-gradient(135deg,#0A66C2,#004182)"},
        "dv360_youtube": {"label": "DV360 YouTube", "channels": ["dv360_youtube"], "color": "#FF0000", "gradient": "linear-gradient(135deg,#FF0000,#CC0000)"},
        "dv360_spotify": {"label": "DV360 Spotify", "channels": ["dv360_spotify"], "color": "#1DB954", "gradient": "linear-gradient(135deg,#1DB954,#168D40)"},
        "dv360_eletromidia": {"label": "DV360 Eletromidia", "channels": ["dv360_eletromid"], "color": "#6366f1", "gradient": "linear-gradient(135deg,#6366f1,#4f46e5)"},
        "dv360_netflix": {"label": "DV360 Netflix", "channels": ["dv360_netflix"], "color": "#E50914", "gradient": "linear-gradient(135deg,#E50914,#B20710)"},
        "dv360_globoplay": {"label": "DV360 Globoplay", "channels": ["dv360_globoplay"], "color": "#F7631B", "gradient": "linear-gradient(135deg,#F7631B,#E0520A)"},
        "dv360_admooh": {"label": "DV360 AdMooh", "channels": ["dv360_admooh"], "color": "#8b5cf6", "gradient": "linear-gradient(135deg,#8b5cf6,#7c3aed)"},
        "dv360": {"label": "DV360 Geral", "channels": ["dv360"], "color": "#34A853", "gradient": "linear-gradient(135deg,#34A853,#0F9D58)"},
    }

    lines_qs = PlacementLine.objects.filter(media_channel__in=all_channels)
    if cliente_id:
        lines_qs = lines_qs.filter(campaign__cliente_id=cliente_id)

    line_ids = list(lines_qs.values_list("id", flat=True))

    # Date filter
    date_from = request.GET.get("date_from", "")
    date_to = request.GET.get("date_to", "")

    # Compare toggle (same UX as DashON)
    compare_on = request.GET.get("compare", "") == "on"
    compare_from = request.GET.get("compare_from", "")
    compare_to = request.GET.get("compare_to", "")

    days_qs = PlacementDay.objects.filter(placement_line_id__in=line_ids)
    if date_from:
        days_qs = days_qs.filter(date__gte=date_from)
    if date_to:
        days_qs = days_qs.filter(date__lte=date_to)

    # ── Global totals ──
    stats = days_qs.aggregate(
        total_impressions=Sum("impressions"),
        total_clicks=Sum("clicks"),
        total_cost=Sum("cost"),
    )
    total_impressions = stats["total_impressions"] or 0
    total_clicks = stats["total_clicks"] or 0
    total_cost = float(stats["total_cost"] or 0)
    ctr = round((total_clicks / total_impressions * 100), 2) if total_impressions > 0 else 0
    cpc = round((total_cost / total_clicks), 2) if total_clicks > 0 else 0
    cpm = round((total_cost / total_impressions * 1000), 2) if total_impressions > 0 else 0
    total_roi = round(total_clicks / total_cost, 2) if total_cost > 0 else 0

    # ── Period comparison (same logic as DashON) ──────────────────────
    consolidated_comparison = None
    prev_qs = None
    prev_start = None
    prev_end = None

    def _pct(curr, prev):
        return round(((curr - prev) / prev) * 100, 1) if prev else None

    if compare_on:
        try:
            if compare_from and compare_to:
                prev_start = datetime.strptime(compare_from, "%Y-%m-%d").date()
                prev_end = datetime.strptime(compare_to, "%Y-%m-%d").date()
            elif date_from and date_to:
                p_start = datetime.strptime(date_from, "%Y-%m-%d").date()
                p_end = datetime.strptime(date_to, "%Y-%m-%d").date()
                p_len = (p_end - p_start).days + 1
                prev_end = p_start - timedelta(days=1)
                prev_start = prev_end - timedelta(days=p_len - 1)
            else:
                from datetime import date as _d
                p_end = _d.today()
                p_start = p_end - timedelta(days=29)
                prev_end = p_start - timedelta(days=1)
                prev_start = prev_end - timedelta(days=29)

            prev_qs = PlacementDay.objects.filter(
                placement_line_id__in=line_ids,
                date__gte=prev_start,
                date__lte=prev_end,
            )
            prev_stats = prev_qs.aggregate(
                imp=Sum("impressions"), clk=Sum("clicks"), cst=Sum("cost"),
            )
            prev_imp = prev_stats["imp"] or 0
            prev_clk = prev_stats["clk"] or 0
            prev_cost = float(prev_stats["cst"] or 0)
            prev_ctr = round((prev_clk / prev_imp * 100), 2) if prev_imp > 0 else 0
            prev_cpc = round((prev_cost / prev_clk), 2) if prev_clk > 0 else 0
            prev_cpm = round((prev_cost / prev_imp * 1000), 2) if prev_imp > 0 else 0
            prev_roi = round((prev_clk / prev_cost), 2) if prev_cost > 0 else 0

            consolidated_comparison = {
                "imp_change": _pct(total_impressions, prev_imp),
                "clk_change": _pct(total_clicks, prev_clk),
                "ctr_change": _pct(ctr, prev_ctr),
                "cost_change": _pct(total_cost, prev_cost),
                "cpc_change": _pct(cpc, prev_cpc),
                "cpm_change": _pct(cpm, prev_cpm),
                "roi_change": _pct(total_roi, prev_roi),
                "prev_start": prev_start.strftime("%d/%m"),
                "prev_end": prev_end.strftime("%d/%m"),
                "period_label": f"{prev_start.strftime('%d/%m')} - {prev_end.strftime('%d/%m')}",
                "prev_start_iso": prev_start.strftime("%Y-%m-%d"),
                "prev_end_iso": prev_end.strftime("%Y-%m-%d"),
                "prev_impressions": prev_imp,
                "prev_clicks": prev_clk,
                "prev_cost": round(prev_cost, 2),
                "prev_ctr": prev_ctr,
                "prev_cpc": prev_cpc,
                "prev_cpm": prev_cpm,
                "prev_roi": prev_roi,
            }
        except (ValueError, TypeError, ZeroDivisionError):
            pass

    # ── Per-channel group stats ──
    vehicles_data = []
    donut_labels = []
    donut_values = []
    donut_colors = []
    bar_labels = []
    bar_imp = []
    bar_clk = []
    bar_colors = []

    for key, cfg in channel_groups.items():
        ch_line_ids = list(lines_qs.filter(media_channel__in=cfg["channels"]).values_list("id", flat=True))
        if not ch_line_ids:
            continue
        ch_qs = days_qs.filter(placement_line_id__in=ch_line_ids)
        ch_stats = ch_qs.aggregate(imp=Sum("impressions"), clk=Sum("clicks"), cst=Sum("cost"))
        ch_imp = ch_stats["imp"] or 0
        ch_clk = ch_stats["clk"] or 0
        ch_cst = float(ch_stats["cst"] or 0)
        if ch_imp == 0 and ch_clk == 0 and ch_cst == 0:
            continue
        ch_ctr = round((ch_clk / ch_imp * 100), 2) if ch_imp > 0 else 0
        ch_cpc = round((ch_cst / ch_clk), 2) if ch_clk > 0 else 0
        ch_cpm = round((ch_cst / ch_imp * 1000), 2) if ch_imp > 0 else 0
        ch_roi = round((ch_clk / ch_cst), 2) if ch_cst > 0 else 0
        share_cost = round((ch_cst / total_cost * 100), 1) if total_cost > 0 else 0
        share_imp = round((ch_imp / total_impressions * 100), 1) if total_impressions > 0 else 0

        # Count campaigns per vehicle
        ch_campaigns = lines_qs.filter(
            media_channel__in=cfg["channels"],
            id__in=ch_qs.values_list("placement_line_id", flat=True).distinct(),
        ).count()

        # URL for the vehicle's veiculacao page
        url_map = {
            "google": "web:veiculacao_google",
            "meta": "web:veiculacao_meta",
            "tiktok": "web:veiculacao_tiktok",
            "linkedin": "web:veiculacao_linkedin",
            "dv360": "web:veiculacao_dv360",
            "dv360_youtube": "web:veiculacao_dv360_youtube",
            "dv360_spotify": "web:veiculacao_dv360_spotify",
            "dv360_eletromidia": "web:veiculacao_dv360_eletromidia",
            "dv360_netflix": "web:veiculacao_dv360_netflix",
            "dv360_globoplay": "web:veiculacao_dv360_globoplay",
            "dv360_admooh": "web:veiculacao_dv360_admooh",
        }
        v_url = ""
        if key in url_map:
            v_url = reverse(url_map[key])

        vehicles_data.append({
            "key": key,
            "label": cfg["label"],
            "color": cfg["color"],
            "gradient": cfg["gradient"],
            "url": v_url,
            "impressions": ch_imp,
            "clicks": ch_clk,
            "cost": round(ch_cst, 2),
            "ctr": ch_ctr,
            "cpc": ch_cpc,
            "cpm": ch_cpm,
            "roi": ch_roi,
            "share_cost": share_cost,
            "share_imp": share_imp,
            "campaigns": ch_campaigns,
        })

        donut_labels.append(cfg["label"])
        donut_values.append(round(ch_cst, 2))
        donut_colors.append(cfg["color"])

        bar_labels.append(cfg["label"])
        bar_imp.append(ch_imp)
        bar_clk.append(ch_clk)
        bar_colors.append(cfg["color"])

    vehicles_data.sort(key=lambda v: v["cost"], reverse=True)

    # ── Daily trend (all channels combined) ──
    daily_all = list(
        days_qs.values("date")
        .annotate(imp=Sum("impressions"), clk=Sum("clicks"), cst=Sum("cost"))
        .order_by("date")
    )
    trend_labels = [str(d["date"]) for d in daily_all]
    trend_imp = [d["imp"] or 0 for d in daily_all]
    trend_clk = [d["clk"] or 0 for d in daily_all]
    trend_cost = [float(d["cst"] or 0) for d in daily_all]

    # ── Daily trend per top vehicles (for stacked chart) ──
    top_vehicles = vehicles_data[:6]
    vehicle_trends = {}
    for v in top_vehicles:
        v_line_ids = list(lines_qs.filter(
            media_channel__in=channel_groups[v["key"]]["channels"]
        ).values_list("id", flat=True))
        v_daily = {}
        for row in days_qs.filter(placement_line_id__in=v_line_ids).values("date").annotate(
            imp=Sum("impressions")
        ).order_by("date"):
            v_daily[str(row["date"])] = row["imp"] or 0
        vehicle_trends[v["key"]] = {
            "label": v["label"],
            "color": v["color"],
            "data": [v_daily.get(d, 0) for d in trend_labels],
        }

    # ── Previous-period totals series for trend chart overlay ──
    # We aggregate the previous period day-by-day so the chart can render a
    # dotted "Período anterior" line aligned to the current series length.
    trend_prev_total = []
    if compare_on and prev_qs is not None and len(trend_labels) > 0:
        prev_daily = {
            str(row["date"]): int(row["imp"] or 0)
            for row in prev_qs.values("date").annotate(imp=Sum("impressions")).order_by("date")
        }
        # Align previous series by index (not by absolute date) so the curves
        # overlap visually
        prev_dates_sorted = sorted(prev_daily.keys())
        # Pad / truncate to match current length
        n = len(trend_labels)
        if len(prev_dates_sorted) >= n:
            trend_prev_total = [prev_daily[d] for d in prev_dates_sorted[:n]]
        else:
            trend_prev_total = [prev_daily.get(d, 0) for d in prev_dates_sorted] + [0] * (n - len(prev_dates_sorted))

    # ── Top campaigns across all vehicles ──
    campaigns_data = []
    for line in lines_qs.select_related("campaign", "campaign__cliente"):
        line_days = days_qs.filter(placement_line=line)
        agg = line_days.aggregate(imp=Sum("impressions"), clk=Sum("clicks"), cst=Sum("cost"))
        imp = agg["imp"] or 0
        clk = agg["clk"] or 0
        cst = float(agg["cst"] or 0)
        if imp == 0 and clk == 0 and cst == 0:
            continue
        # Find vehicle label
        v_label = line.get_media_channel_display()
        for cfg in channel_groups.values():
            if line.media_channel in cfg["channels"]:
                v_label = cfg["label"]
                break
        campaigns_data.append({
            "name": line.channel or line.property_text or f"Campaign #{line.external_ref}",
            "client": line.campaign.cliente.nome if line.campaign else "",
            "vehicle": v_label,
            "impressions": imp,
            "clicks": clk,
            "ctr": round((clk / imp * 100), 2) if imp > 0 else 0,
            "cost": round(cst, 2),
            "cpc": round((cst / clk), 2) if clk > 0 else 0,
            "roi": round((clk / cst), 2) if cst > 0 else 0,
        })
    campaigns_data.sort(key=lambda c: c["cost"], reverse=True)

    # Unique vehicle labels for filter pills (preserving cost order)
    _seen_vehicles: set[str] = set()
    vehicles_in_campaigns: list[str] = []
    for c in campaigns_data:
        v = c.get("vehicle") or ""
        if v and v not in _seen_vehicles:
            _seen_vehicles.add(v)
            vehicles_in_campaigns.append(v)

    has_data = bool(vehicles_data)

    return render(
        request,
        "web/consolidated_on.html",
        {
            "active": "consolidated_on",
            "page_title": "Consolidated ON",
            "has_data": has_data,
            "date_from": date_from,
            "date_to": date_to,
            # Period comparison
            "compare_on": compare_on,
            "compare_from": compare_from,
            "compare_to": compare_to,
            "comparison": consolidated_comparison,
            "trend_prev_json": json.dumps(trend_prev_total),
            # Totals
            "total_impressions": total_impressions,
            "total_clicks": total_clicks,
            "total_cost": round(total_cost, 2),
            "ctr": ctr,
            "cpc": cpc,
            "cpm": cpm,
            "total_roi": total_roi,
            "vehicles_count": len(vehicles_data),
            "campaigns_count": len(campaigns_data),
            # Per-vehicle breakdown
            "vehicles_data": vehicles_data,
            # Charts JSON
            "trend_labels_json": json.dumps(trend_labels),
            "trend_imp_json": json.dumps(trend_imp),
            "trend_clk_json": json.dumps(trend_clk),
            "trend_cost_json": json.dumps(trend_cost),
            "donut_labels_json": json.dumps(donut_labels),
            "donut_values_json": json.dumps(donut_values),
            "donut_colors_json": json.dumps(donut_colors),
            "bar_labels_json": json.dumps(bar_labels),
            "bar_imp_json": json.dumps(bar_imp),
            "bar_clk_json": json.dumps(bar_clk),
            "bar_colors_json": json.dumps(bar_colors),
            "vehicle_trends_json": json.dumps(vehicle_trends),
            # Campaigns table
            "campaigns_data": campaigns_data,
            "vehicles_in_campaigns": vehicles_in_campaigns,
            # Per-client module visibility
            "hidden_modules": hidden_modules,
            "can_manage_modules": can_manage_modules,
            "current_cliente_id": cliente_id,
        },
    )


@login_required
def relatorios(request: HttpRequest) -> HttpResponse:
    """Redireciona para lista de clientes para relatórios."""
    return redirect("web:relatorios_clientes")


@login_required
def integracoes(request: HttpRequest) -> HttpResponse:
    from integrations.models import GoogleAdsAccount, SyncLog, MetaAdsAccount, MetaSyncLog

    role = effective_role(request)
    if role == "cliente":
        return redirect("web:dashboard")

    # Flash messages from OAuth callback
    gads_error = request.session.pop("gads_error", "")
    gads_success = request.session.pop("gads_success", "")
    mads_error = request.session.pop("mads_error", "")
    mads_success = request.session.pop("mads_success", "")

    # Google Ads accounts
    gads_accounts = list(
        GoogleAdsAccount.objects.filter(is_active=True)
        .select_related("cliente")
        .order_by("cliente__nome", "descriptive_name")
    )

    # Google Ads sync logs (last 20)
    gads_logs = list(
        SyncLog.objects.select_related("account", "account__cliente")
        .order_by("-started_at")[:20]
    )

    # Detect developer token issues from recent errors
    has_token_error = any(
        log.error_message and "Developer Token" in log.error_message
        for log in gads_logs
    )

    # Meta Ads accounts
    mads_accounts = list(
        MetaAdsAccount.objects.filter(is_active=True)
        .select_related("cliente")
        .order_by("cliente__nome", "descriptive_name")
    )

    # Meta Ads sync logs (last 20)
    mads_logs = list(
        MetaSyncLog.objects.select_related("account", "account__cliente")
        .order_by("-started_at")[:20]
    )

    # Sidebar clientes for the "connect" form
    clientes = list(
        Cliente.objects.filter(ativo=True).order_by("nome").values("id", "nome")
    )

    # Count synced data in DB for "clear data" buttons
    google_channels = ["google", "youtube", "display", "search"]
    gads_data_count = PlacementLine.objects.filter(
        media_channel__in=google_channels, external_ref__gt=""
    ).count()
    mads_data_count = PlacementLine.objects.filter(
        media_channel="meta", external_ref__gt=""
    ).count()

    return render(
        request,
        "web/integracoes.html",
        {
            "active": "integracoes",
            "page_title": "Integrações",
            "accounts": gads_accounts,
            "recent_logs": gads_logs,
            "mads_accounts": mads_accounts,
            "mads_logs": mads_logs,
            "clientes": clientes,
            "gads_error": gads_error,
            "gads_success": gads_success,
            "mads_error": mads_error,
            "mads_success": mads_success,
            "has_token_error": has_token_error,
            "gads_data_count": gads_data_count,
            "mads_data_count": mads_data_count,
        },
    )


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
    from accounts.models import SiteConfig, User
    import json as _json

    tab = request.GET.get("tab", "empresa")
    success_message = ""
    cfg = SiteConfig.load()

    if request.method == "POST":
        post_tab = request.POST.get("_tab", "empresa")

        if post_tab == "empresa":
            cfg.empresa = {
                "company_name": request.POST.get("company_name", ""),
                "cnpj": request.POST.get("cnpj", ""),
                "timezone": request.POST.get("timezone", "America/Sao_Paulo"),
                "currency": request.POST.get("currency", "BRL - Real Brasileiro"),
                "primary_color": request.POST.get("primary_color", "#6C3BFF"),
            }
            update_fields = ["empresa", "updated_at"]
            logo_file = request.FILES.get("logo")
            if logo_file:
                cfg.logo = logo_file
                update_fields.append("logo")
            cfg.save(update_fields=update_fields)
            success_message = "Configurações da empresa salvas."

        elif post_tab == "metricas":
            cfg.metricas = {
                "ctr_min": request.POST.get("ctr_min", ""),
                "cpc_max": request.POST.get("cpc_max", ""),
                "roi_target": request.POST.get("roi_target", ""),
                "cpm_max": request.POST.get("cpm_max", ""),
                "freq_max": request.POST.get("freq_max", ""),
                "coverage_min": request.POST.get("coverage_min", ""),
                "auto_alerts": "auto_alerts" in request.POST,
                "daily_report": "daily_report" in request.POST,
            }
            cfg.save(update_fields=["metricas", "updated_at"])
            success_message = "Métricas atualizadas."

        elif post_tab == "alertas":
            try:
                rules = _json.loads(request.POST.get("rules_json", "[]"))
            except _json.JSONDecodeError:
                rules = []
            cfg.alertas = rules
            cfg.save(update_fields=["alertas", "updated_at"])
            success_message = "Regras de alertas salvas."

        elif post_tab == "financeiro":
            cats = request.POST.getlist("categories")
            cfg.financeiro = {
                "comissao": request.POST.get("comissao", ""),
                "imposto": request.POST.get("imposto", ""),
                "desconto_max": request.POST.get("desconto_max", ""),
                "prazo_pgto": request.POST.get("prazo_pgto", ""),
                "categories": cats,
            }
            cfg.save(update_fields=["financeiro", "updated_at"])
            success_message = "Configurações financeiras salvas."

        elif post_tab == "estrutura":
            cfg.estrutura = {
                "meios": request.POST.getlist("meios"),
                "statuses": request.POST.getlist("statuses"),
                "pracas": request.POST.getlist("pracas"),
            }
            cfg.save(update_fields=["estrutura", "updated_at"])
            success_message = "Estrutura salva."

        elif post_tab == "ia":
            cfg.ia = {
                "auto_recommendations": "auto_recommendations" in request.POST,
                "style": request.POST.get("ia_style", "balanced"),
                "auto_insights": "auto_insights" in request.POST,
                "budget_suggestion": "budget_suggestion" in request.POST,
            }
            cfg.save(update_fields=["ia", "updated_at"])
            success_message = "Configurações de IA salvas."

        elif post_tab == "seguranca":
            cfg.seguranca = {
                "force_password_change": "force_password_change" in request.POST,
                "two_factor": "two_factor" in request.POST,
                "log_access": "log_access" in request.POST,
                "session_timeout": request.POST.get("session_timeout", "60"),
                "login_attempts": request.POST.get("login_attempts", "5"),
            }
            cfg.save(update_fields=["seguranca", "updated_at"])
            success_message = "Configurações de segurança salvas."

        tab = post_tab

    users = User.objects.filter(role__in=["admin", "colaborador"]).order_by("-date_joined")
    clientes_list = Cliente.objects.filter(ativo=True).order_by("nome")

    # Ensure defaults for empty JSON fields
    if not cfg.estrutura:
        cfg.estrutura = {
            "meios": ["TV Aberta", "Pay TV", "Rádio", "Jornal", "Digital", "OOH"],
            "statuses": ["Active", "Paused", "Draft", "Completed"],
            "pracas": ["São Paulo Capital", "São Paulo Estado", "ABC", "Rio de Janeiro"],
        }
    if not cfg.financeiro or "categories" not in cfg.financeiro:
        if not cfg.financeiro:
            cfg.financeiro = {}
        cfg.financeiro.setdefault("categories", ["Mídia", "Produção", "Taxas", "Veiculação", "Geração"])

    return render(
        request,
        "web/configuracoes.html",
        {
            "active": "configuracoes",
            "page_title": "Configurações",
            "tab": tab,
            "success_message": success_message,
            "users": users,
            "clientes_list": clientes_list,
            "cfg": cfg,
        },
    )


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
    recent_logs = list(logs_qs.select_related("user", "cliente")[:50])
    # Adicionar details_json para serialização correta no template
    for log in recent_logs:
        log.details_json = json.dumps(log.details, default=str) if log.details else "{}"

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
@require_admin
def analytics_real(request: HttpRequest) -> HttpResponse:
    """Analytics Real – AI-powered version with Claude-generated insights."""
    return analytics(request, template="web/analytics_real.html", ai_mode=True)


@login_required
def analytics(request: HttpRequest, template: str = "web/analytics.html", ai_mode: bool = False) -> HttpResponse:
    """Analytics Intelligence – diagnostic scoring, insights, recommendations, funnel & alerts."""
    from collections import defaultdict
    from decimal import Decimal

    role = effective_role(request)
    cliente_id = effective_cliente_id(request)
    if not cliente_id and is_admin(request.user):
        cliente_id = selected_cliente_id(request)

    if not cliente_id:
        return render(request, template, {
            "active": "analytics",
            "page_title": "Analytics Intelligence",
            "require_cliente": True,
        })

    # ── Digital channels ──
    google_channels = ["google", "youtube", "display", "search"]
    meta_channels = ["meta"]
    all_channels = google_channels + meta_channels

    lines_qs = PlacementLine.objects.filter(
        media_channel__in=all_channels,
        campaign__cliente_id=cliente_id,
    )
    line_ids = list(lines_qs.values_list("id", flat=True))

    # Date filter
    date_from = request.GET.get("date_from", "")
    date_to = request.GET.get("date_to", "")

    days_qs = PlacementDay.objects.filter(placement_line_id__in=line_ids)
    if date_from:
        days_qs = days_qs.filter(date__gte=date_from)
    if date_to:
        days_qs = days_qs.filter(date__lte=date_to)

    if not line_ids or not days_qs.exists():
        return render(request, template, {
            "active": "analytics",
            "page_title": "Analytics Intelligence",
            "no_data": True,
            "date_from": date_from,
            "date_to": date_to,
        })

    # ── Global aggregates ──
    stats = days_qs.aggregate(
        total_imp=Sum("impressions"),
        total_clk=Sum("clicks"),
        total_cost=Sum("cost"),
    )
    total_imp = stats["total_imp"] or 0
    total_clk = stats["total_clk"] or 0
    total_cost = float(stats["total_cost"] or 0)
    global_ctr = round((total_clk / total_imp * 100), 2) if total_imp > 0 else 0
    global_cpc = round((total_cost / total_clk), 2) if total_clk > 0 else 0

    # ── Period comparison (current vs previous) ──
    period_comparison = None
    compare_mode = request.GET.get("compare", "")
    if date_from and date_to:
        try:
            from datetime import timedelta as _td
            p_start = datetime.strptime(date_from, "%Y-%m-%d").date()
            p_end = datetime.strptime(date_to, "%Y-%m-%d").date()
            p_len = (p_end - p_start).days + 1
            prev_end = p_start - _td(days=1)
            prev_start = prev_end - _td(days=p_len - 1)

            prev_qs = PlacementDay.objects.filter(
                placement_line_id__in=line_ids,
                date__gte=prev_start,
                date__lte=prev_end,
            )
            prev_stats = prev_qs.aggregate(
                total_imp=Sum("impressions"), total_clk=Sum("clicks"), total_cost=Sum("cost"),
            )
            prev_imp = prev_stats["total_imp"] or 0
            prev_clk = prev_stats["total_clk"] or 0
            prev_cost = float(prev_stats["total_cost"] or 0)
            prev_ctr = round((prev_clk / prev_imp * 100), 2) if prev_imp > 0 else 0
            prev_cpc = round((prev_cost / prev_clk), 2) if prev_clk > 0 else 0

            def _pct_change(curr, prev):
                if prev == 0:
                    return None
                return round(((curr - prev) / prev) * 100, 1)

            period_comparison = {
                "prev_start": prev_start.strftime("%d/%m/%Y"),
                "prev_end": prev_end.strftime("%d/%m/%Y"),
                "curr_start": p_start.strftime("%d/%m/%Y"),
                "curr_end": p_end.strftime("%d/%m/%Y"),
                "days": p_len,
                "metrics": [
                    {"label": "Impressões", "curr": total_imp, "prev": prev_imp, "change": _pct_change(total_imp, prev_imp), "up_good": True},
                    {"label": "Cliques", "curr": total_clk, "prev": prev_clk, "change": _pct_change(total_clk, prev_clk), "up_good": True},
                    {"label": "CTR", "curr": global_ctr, "prev": prev_ctr, "change": _pct_change(global_ctr, prev_ctr), "unit": "%", "up_good": True},
                    {"label": "CPC", "curr": global_cpc, "prev": prev_cpc, "change": _pct_change(global_cpc, prev_cpc), "unit": "R$", "up_good": False},
                    {"label": "Investimento", "curr": round(total_cost, 2), "prev": round(prev_cost, 2), "change": _pct_change(total_cost, prev_cost), "unit": "R$", "up_good": False},
                ],
            }
        except (ValueError, TypeError):
            pass

    # ── Per-platform aggregates ──
    google_line_ids = list(lines_qs.filter(media_channel__in=google_channels).values_list("id", flat=True))
    meta_line_ids = list(lines_qs.filter(media_channel__in=meta_channels).values_list("id", flat=True))

    def _agg(ids):
        qs = days_qs.filter(placement_line_id__in=ids)
        s = qs.aggregate(imp=Sum("impressions"), clk=Sum("clicks"), cst=Sum("cost"))
        imp = s["imp"] or 0
        clk = s["clk"] or 0
        cst = float(s["cst"] or 0)
        return {
            "impressions": imp,
            "clicks": clk,
            "cost": round(cst, 2),
            "ctr": round((clk / imp * 100), 2) if imp > 0 else 0,
            "cpc": round((cst / clk), 2) if clk > 0 else 0,
        }

    google_agg = _agg(google_line_ids)
    meta_agg = _agg(meta_line_ids)

    # ── Per-campaign metrics ──
    campaign_metrics = []
    for line in lines_qs.select_related("campaign", "campaign__cliente"):
        agg = days_qs.filter(placement_line=line).aggregate(
            imp=Sum("impressions"), clk=Sum("clicks"), cst=Sum("cost"),
        )
        imp = agg["imp"] or 0
        clk = agg["clk"] or 0
        cst = float(agg["cst"] or 0)
        if imp == 0 and clk == 0 and cst == 0:
            continue
        ctr = round((clk / imp * 100), 2) if imp > 0 else 0
        cpc = round((cst / clk), 2) if clk > 0 else 0
        platform = "Meta Ads" if line.media_channel in meta_channels else "Google Ads"
        name = line.channel or line.property_text or f"Campaign #{line.external_ref}"
        campaign_metrics.append({
            "id": line.id,
            "name": name,
            "platform": platform,
            "impressions": imp,
            "clicks": clk,
            "ctr": ctr,
            "cost": round(cst, 2),
            "cpc": cpc,
        })
    campaign_metrics.sort(key=lambda c: c["cost"], reverse=True)

    # ── Daily trend (last 30 unique dates) ──
    daily_data = list(
        days_qs.values("date")
        .annotate(imp=Sum("impressions"), clk=Sum("clicks"), cst=Sum("cost"))
        .order_by("date")
    )
    trend_labels = [str(d["date"]) for d in daily_data]
    trend_imp = [d["imp"] or 0 for d in daily_data]
    trend_clk = [d["clk"] or 0 for d in daily_data]

    # Moving average 7d and trend signal
    def _ma7(series):
        out = []
        for i in range(len(series)):
            window = series[max(0, i - 6): i + 1]
            avg = sum(window) / len(window) if window else 0
            out.append(round(avg, 2))
        return out

    trend_ma7 = _ma7(trend_imp)
    trend_signal = "estavel"
    if len(trend_ma7) >= 14:
        recent_avg = sum(trend_ma7[-7:]) / 7
        prev_avg = sum(trend_ma7[-14:-7]) / 7
        if prev_avg > 0:
            change = (recent_avg - prev_avg) / prev_avg * 100
            if change > 5:
                trend_signal = "up"
            elif change < -5:
                trend_signal = "down"

    # ──────────────────────────────────────────────────
    # BLOCO 1: DIAGNÓSTICO AUTOMÁTICO (Performance Score)
    # ──────────────────────────────────────────────────
    # Benchmarks (industry averages for digital ads)
    BENCH_CTR = 2.0        # 2% CTR benchmark
    BENCH_CPC = 3.50       # R$ 3.50 CPC benchmark
    BENCH_CPM = 15.0       # R$ 15 CPM benchmark

    # CTR score (25%) – higher is better, cap at 200% of benchmark
    ctr_ratio = min(global_ctr / BENCH_CTR, 2.0) if BENCH_CTR > 0 else 0
    ctr_score = round(ctr_ratio * 50, 1)  # 0-100

    # CPC score (20%) – lower is better
    if global_cpc > 0:
        cpc_ratio = min(BENCH_CPC / global_cpc, 2.0)
        cpc_score = round(cpc_ratio * 50, 1)
    else:
        cpc_score = 50  # neutral if no clicks

    # CPM / reach efficiency (25%)
    cpm = round((total_cost / total_imp * 1000), 2) if total_imp > 0 else 0
    if cpm > 0:
        cpm_ratio = min(BENCH_CPM / cpm, 2.0)
        cpm_score = round(cpm_ratio * 50, 1)
    else:
        cpm_score = 50

    # Activity rate (20%) – percentage of campaigns with data
    total_lines = lines_qs.count()
    active_lines = days_qs.values("placement_line_id").distinct().count()
    activity_rate = round((active_lines / total_lines * 100), 1) if total_lines > 0 else 0
    activity_score = round(min(activity_rate, 100), 1)

    # Consistency (10%) – low daily variation = good
    if len(trend_imp) > 1:
        avg_imp = sum(trend_imp) / len(trend_imp) if trend_imp else 1
        variance = sum((x - avg_imp) ** 2 for x in trend_imp) / len(trend_imp)
        std_dev = variance ** 0.5
        cv = std_dev / avg_imp if avg_imp > 0 else 1  # coefficient of variation
        consistency_score = round(max(0, min(100, (1 - cv) * 100)), 1)
    else:
        consistency_score = 50

    # Weighted Performance Score
    perf_score = round(
        ctr_score * 0.25 +
        cpc_score * 0.20 +
        cpm_score * 0.25 +
        activity_score * 0.20 +
        consistency_score * 0.10
    )
    perf_score = max(0, min(100, perf_score))

    # Score classification
    if perf_score >= 80:
        score_class = "excellent"
        score_label = "Excelente"
    elif perf_score >= 60:
        score_class = "good"
        score_label = "Bom"
    elif perf_score >= 40:
        score_class = "average"
        score_label = "Regular"
    else:
        score_class = "poor"
        score_label = "Precisa Melhorar"

    score_breakdown = [
        {"key": "ctr", "label": "CTR", "weight": "25%", "score": round(ctr_score), "max": 100, "benchmark": BENCH_CTR, "current": global_ctr, "unit": "%"},
        {"key": "cpc", "label": "CPC", "weight": "20%", "score": round(cpc_score), "max": 100, "benchmark": BENCH_CPC, "current": global_cpc, "unit": "R$"},
        {"key": "cpm", "label": "CPM / Alcance", "weight": "25%", "score": round(cpm_score), "max": 100, "benchmark": BENCH_CPM, "current": cpm, "unit": "R$"},
        {"key": "activity", "label": "Atividade", "weight": "20%", "score": round(activity_score), "max": 100},
        {"key": "consistency", "label": "Consistencia", "weight": "10%", "score": round(consistency_score), "max": 100},
    ]

    # Explainable negative impacts (deductions in points out of 100)
    def _deduction(weight_pct: float, score_val: float) -> int:
        max_pts = int(weight_pct * 100)
        contrib = int(round(score_val * weight_pct))
        return max(0, max_pts - contrib)

    negative_impacts: list[dict] = []
    d_cpm = _deduction(0.25, cpm_score)
    if d_cpm >= 5:
        negative_impacts.append({"label": "CPM elevado", "points": d_cpm})
    d_cpc = _deduction(0.20, cpc_score)
    if d_cpc >= 5:
        negative_impacts.append({"label": "CPC elevado", "points": d_cpc})
    d_ctr = _deduction(0.25, ctr_score)
    if d_ctr >= 5:
        negative_impacts.append({"label": "CTR abaixo do benchmark", "points": d_ctr})
    d_act = _deduction(0.20, activity_score)
    if d_act >= 5:
        negative_impacts.append({"label": "Baixa atividade", "points": d_act})
    d_cons = _deduction(0.10, consistency_score)
    if d_cons >= 5:
        negative_impacts.append({"label": "Falta de consistencia", "points": d_cons})

    # ──────────────────────────────────────────────────
    # BLOCO 2: INSIGHTS AUTOMÁTICOS
    # ──────────────────────────────────────────────────
    insights: list[dict] = []

    # Insight: CTR above/below benchmark
    if global_ctr >= BENCH_CTR * 1.5:
        insights.append({
            "type": "positive",
            "icon": "trending-up",
            "title": "CTR acima da media",
            "text": f"Seu CTR de {global_ctr}% esta {round(global_ctr / BENCH_CTR, 1)}x acima do benchmark de {BENCH_CTR}%. Campanhas estao gerando bom engajamento.",
        })
    elif global_ctr < BENCH_CTR * 0.5:
        insights.append({
            "type": "negative",
            "icon": "trending-down",
            "title": "CTR abaixo do esperado",
            "text": f"CTR de {global_ctr}% esta abaixo do benchmark de {BENCH_CTR}%. Considere revisar criativos e segmentacao.",
        })

    # Insight: Platform comparison
    if google_agg["impressions"] > 0 and meta_agg["impressions"] > 0:
        if google_agg["ctr"] > meta_agg["ctr"] * 1.3:
            insights.append({
                "type": "info",
                "icon": "bar-chart",
                "title": "Google Ads com melhor CTR",
                "text": f"Google Ads ({google_agg['ctr']}%) supera Meta Ads ({meta_agg['ctr']}%) em taxa de cliques. Considere realocar orcamento.",
            })
        elif meta_agg["ctr"] > google_agg["ctr"] * 1.3:
            insights.append({
                "type": "info",
                "icon": "bar-chart",
                "title": "Meta Ads com melhor CTR",
                "text": f"Meta Ads ({meta_agg['ctr']}%) supera Google Ads ({google_agg['ctr']}%) em taxa de cliques. Considere realocar orcamento.",
            })

    # Insight: CPC comparison between platforms
    if google_agg["cpc"] > 0 and meta_agg["cpc"] > 0:
        cheaper = "Google Ads" if google_agg["cpc"] < meta_agg["cpc"] else "Meta Ads"
        cheaper_cpc = min(google_agg["cpc"], meta_agg["cpc"])
        expensive_cpc = max(google_agg["cpc"], meta_agg["cpc"])
        if expensive_cpc > cheaper_cpc * 1.5:
            insights.append({
                "type": "warning",
                "icon": "dollar-sign",
                "title": f"CPC mais barato no {cheaper}",
                "text": f"{cheaper} tem CPC de R$ {cheaper_cpc:.2f} vs R$ {expensive_cpc:.2f}. Diferenca de {round((expensive_cpc / cheaper_cpc - 1) * 100)}%.",
            })

    # Insight: High CPC campaigns
    high_cpc_camps = [c for c in campaign_metrics if c["cpc"] > BENCH_CPC * 2 and c["clicks"] > 10]
    if high_cpc_camps:
        names = ", ".join(c["name"][:25] for c in high_cpc_camps[:3])
        insights.append({
            "type": "negative",
            "icon": "alert-triangle",
            "title": f"{len(high_cpc_camps)} campanha(s) com CPC elevado",
            "text": f"Campanhas com CPC acima de R$ {BENCH_CPC * 2:.2f}: {names}.",
        })

    # Insight: Budget concentration
    if len(campaign_metrics) >= 3:
        top_cost = campaign_metrics[0]["cost"]
        if top_cost > total_cost * 0.5:
            insights.append({
                "type": "warning",
                "icon": "pie-chart",
                "title": "Concentracao de orcamento",
                "text": f"\"{campaign_metrics[0]['name'][:30]}\" consome {round(top_cost / total_cost * 100)}% do investimento total. Diversifique para reduzir riscos.",
            })

    # Insight: Consistency trend
    recent_drop_points = 0
    if len(trend_imp) >= 7:
        last_7 = trend_imp[-7:]
        prev_7 = trend_imp[-14:-7] if len(trend_imp) >= 14 else trend_imp[:7]
        avg_last = sum(last_7) / len(last_7)
        avg_prev = sum(prev_7) / len(prev_7)
        if avg_prev > 0:
            change = round((avg_last - avg_prev) / avg_prev * 100, 1)
            if change > 20:
                insights.append({
                    "type": "positive",
                    "icon": "trending-up",
                    "title": "Impressoes em alta",
                    "text": f"Impressoes cresceram {change}% nos ultimos 7 dias comparado ao periodo anterior.",
                })
            elif change < -20:
                insights.append({
                    "type": "negative",
                    "icon": "trending-down",
                    "title": "Queda nas impressoes",
                    "text": f"Impressoes cairam {abs(change)}% nos ultimos 7 dias comparado ao periodo anterior.",
                })
                # Map drop percentage to a points penalty up to 20
                recent_drop_points = min(20, int(round(abs(change) * 0.6)))
                if recent_drop_points >= 5:
                    negative_impacts.append({"label": "Queda recente de impressoes", "points": recent_drop_points})

    # Positivos adicionais
    if global_ctr >= BENCH_CTR * 1.1:
        insights.append({
            "type": "positive",
            "icon": "trending-up",
            "title": "CTR acima da media",
            "text": f"CTR geral {global_ctr}% supera benchmark de {BENCH_CTR}%.",
        })
    if global_cpc > 0 and global_cpc <= BENCH_CPC * 0.8:
        insights.append({
            "type": "positive",
            "icon": "dollar-sign",
            "title": "CPC eficiente",
            "text": f"CPC de R$ {global_cpc:.2f}, abaixo do benchmark de R$ {BENCH_CPC:.2f}.",
        })

    # Negativos adicionais
    if cpm > BENCH_CPM * 1.2:
        insights.append({
            "type": "negative",
            "icon": "alert-triangle",
            "title": "CPM elevado",
            "text": f"CPM em R$ {cpm:.2f} excede benchmark de R$ {BENCH_CPM:.2f}.",
        })
    # Concentração já pode ter sido adicionada; manter se não existir similar
    if total_cost > 0 and len(campaign_metrics) >= 2:
        share_top2 = (campaign_metrics[0]["cost"] + campaign_metrics[1]["cost"]) / total_cost
        if share_top2 > 0.75:
            insights.append({
                "type": "warning",
                "icon": "pie-chart",
                "title": "Concentracao excessiva",
                "text": f"Top 2 campanhas concentram {round(share_top2*100)}% do investimento.",
            })
    # 'Frequencia' proxy: muito volume com baixo CTR
    if total_imp > 10000 and global_ctr < BENCH_CTR * 0.6:
        insights.append({
            "type": "negative",
            "icon": "info",
            "title": "Frequencia elevada (proxy)",
            "text": "Impressoes altas com CTR baixo indicam desgaste/alta frequencia. Revise capping e criativos.",
        })

    # Balancear 3–6 insights (positivos e negativos)
    if len(insights) < 3:
        insights.append({
            "type": "info",
            "icon": "info",
            "title": "Dados sendo analisados",
            "text": "Continue acumulando dados para gerar insights mais precisos.",
        })
    # Limitar a 6 para foco executivo
    insights = insights[:6]

    # ──────────────────────────────────────────────────
    # BLOCO 3: DECISÃO RECOMENDADA
    # ──────────────────────────────────────────────────
    recommendations: list[dict] = []

    # Recommendation: Reallocate budget
    if google_agg["cpc"] > 0 and meta_agg["cpc"] > 0:
        if google_agg["cpc"] < meta_agg["cpc"] * 0.7:
            recommendations.append({
            "priority": "high",
                "icon": "refresh-cw",
                "title": "Realocar orcamento para Google Ads",
                "text": f"Google Ads oferece CPC {round((1 - google_agg['cpc'] / meta_agg['cpc']) * 100)}% menor. Transfira parte do budget de Meta para Google.",
                "action": "Ajustar alocacao de budget entre plataformas",
            "impact": 18,
            "confidence": 82,
            })
        elif meta_agg["cpc"] < google_agg["cpc"] * 0.7:
            recommendations.append({
            "priority": "high",
                "icon": "refresh-cw",
                "title": "Realocar orcamento para Meta Ads",
                "text": f"Meta Ads oferece CPC {round((1 - meta_agg['cpc'] / google_agg['cpc']) * 100)}% menor. Transfira parte do budget de Google para Meta.",
                "action": "Ajustar alocacao de budget entre plataformas",
            "impact": 18,
            "confidence": 82,
            })

    # Recommendation: Pause underperformers
    low_perf = [c for c in campaign_metrics if c["ctr"] < BENCH_CTR * 0.3 and c["impressions"] > 1000]
    if low_perf:
        recommendations.append({
            "priority": "medium",
            "icon": "pause-circle",
            "title": f"Pausar {len(low_perf)} campanha(s) de baixo desempenho",
            "text": f"Campanhas com CTR abaixo de {round(BENCH_CTR * 0.3, 2)}% e mais de 1.000 impressoes. Revisao de criativos recomendada antes de reativar.",
            "action": "Pausar e revisar criativos",
            "impact": 8,
            "confidence": 70,
        })

    # Recommendation: Scale top performers
    top_perf = [c for c in campaign_metrics if c["ctr"] > BENCH_CTR * 1.5 and c["cost"] < total_cost * 0.3]
    if top_perf:
        names = ", ".join(c["name"][:20] for c in top_perf[:3])
        recommendations.append({
            "priority": "high",
            "icon": "zap",
            "title": "Escalar campanhas de alto desempenho",
            "text": f"Campanhas com CTR acima de {round(BENCH_CTR * 1.5, 1)}% recebem pouca verba: {names}. Aumente o budget para maximizar resultados.",
            "action": "Aumentar budget das top performers",
            "impact": 12,
            "confidence": 75,
        })

    # Recommendation: Improve creatives for low CTR
    if global_ctr < BENCH_CTR:
        recommendations.append({
            "priority": "medium",
            "icon": "image",
            "title": "Revisar criativos",
            "text": f"CTR geral ({global_ctr}%) abaixo do benchmark ({BENCH_CTR}%). Teste novos formatos de anuncio, titulos e calls-to-action.",
            "action": "Testar novos criativos A/B",
            "impact": 10,
            "confidence": 65,
        })

    # Recommendation: Expand reach if high CTR but low impressions
    if global_ctr > BENCH_CTR * 1.5 and total_imp < 10000:
        recommendations.append({
            "priority": "medium",
            "icon": "maximize",
            "title": "Expandir alcance",
            "text": f"Excelente CTR ({global_ctr}%) mas volume baixo ({total_imp:,} impressoes). Aumente os lances ou amplie a segmentacao.",
            "action": "Aumentar lances e audiencia",
            "impact": 9,
            "confidence": 60,
        })

    if not recommendations:
        recommendations.append({
            "priority": "low",
            "icon": "check-circle",
            "title": "Campanhas em bom estado",
            "text": "Nenhuma acao urgente identificada. Continue monitorando as metricas.",
            "action": "Acompanhar metricas semanalmente",
            "impact": 0,
            "confidence": 90,
        })

    # ──────────────────────────────────────────────────
    # BLOCO 4: FUNIL DE PERFORMANCE
    # ──────────────────────────────────────────────────
    funnel_steps = []
    funnel_steps.append({
        "label": "Impressoes",
        "value": total_imp,
        "formatted": f"{total_imp:,}".replace(",", "."),
        "pct": 100,
        "drop": None,
        "cost_label": f"CPM: R$ {cpm:.2f}",
    })
    funnel_steps.append({
        "label": "Cliques",
        "value": total_clk,
        "formatted": f"{total_clk:,}".replace(",", "."),
        "pct": round(total_clk / total_imp * 100, 2) if total_imp > 0 else 0,
        "drop": round((1 - total_clk / total_imp) * 100, 1) if total_imp > 0 else 0,
        "cost_label": f"CPC: R$ {global_cpc:.2f}",
    })
    # Engagement proxy: clicks with cost > 0 (qualified clicks)
    qualified_clicks = days_qs.filter(clicks__gt=0, cost__gt=0).aggregate(
        clk=Sum("clicks")
    )["clk"] or 0
    funnel_steps.append({
        "label": "Cliques Qualificados",
        "value": qualified_clicks,
        "formatted": f"{qualified_clicks:,}".replace(",", "."),
        "pct": round(qualified_clicks / total_imp * 100, 2) if total_imp > 0 else 0,
        "drop": round((1 - qualified_clicks / total_clk) * 100, 1) if total_clk > 0 else 0,
        "cost_label": f"Custo/QC: R$ { (total_cost/qualified_clicks):.2f}" if qualified_clicks>0 else "Custo/QC: -",
    })
    funnel_steps.append({
        "label": "Investimento",
        "value": total_cost,
        "formatted": f"R$ {total_cost:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
        "pct": round(total_cost / (total_imp * 0.015) * 100, 1) if total_imp > 0 else 0,  # vs benchmark CPM
        "drop": None,
    })

    # ──────────────────────────────────────────────────
    # BLOCO 5: ALERTAS AUTOMÁTICOS
    # ──────────────────────────────────────────────────
    alerts = []

    # Alert: Campaigns with 0 clicks (significant impressions)
    zero_click_camps = [c for c in campaign_metrics if c["clicks"] == 0 and c["impressions"] > 500]
    if zero_click_camps:
        alerts.append({
            "severity": "critical",
            "icon": "alert-circle",
            "title": f"{len(zero_click_camps)} campanha(s) sem cliques",
            "text": f"Campanhas com impressoes mas zero cliques. Revise urgentemente.",
            "impact_pct": 25,
            "impact_window": 7,
        })

    # Alert: CPC above limit
    cpc_limit = BENCH_CPC * 3
    expensive_camps = [c for c in campaign_metrics if c["cpc"] > cpc_limit and c["clicks"] > 5]
    if expensive_camps:
        alerts.append({
            "severity": "warning",
            "icon": "alert-triangle",
            "title": f"CPC acima de R$ {cpc_limit:.2f}",
            "text": f"{len(expensive_camps)} campanha(s) com custo por clique excessivo. Reavalie segmentacao e lances.",
            "impact_pct": 10,
            "impact_window": 14,
        })

    # Alert: No recent data (last 3 days)
    from datetime import date
    today = date.today()
    recent_days = days_qs.filter(date__gte=today - timedelta(days=3))
    if not recent_days.exists() and days_qs.exists():
        alerts.append({
            "severity": "warning",
            "icon": "clock",
            "title": "Sem dados recentes",
            "text": "Nenhum dado de veiculacao nos ultimos 3 dias. Verifique se as campanhas estao ativas e se a sincronizacao esta funcionando.",
            "impact_pct": 20,
            "impact_window": 7,
        })

    # Alert: Sudden drop in impressions
    if len(trend_imp) >= 3:
        last_3_avg = sum(trend_imp[-3:]) / 3
        overall_avg = sum(trend_imp) / len(trend_imp)
        if overall_avg > 0 and last_3_avg < overall_avg * 0.3:
            alerts.append({
                "severity": "critical",
                "icon": "trending-down",
                "title": "Queda brusca nas impressoes",
                "text": f"Impressoes dos ultimos 3 dias caiu {round((1 - last_3_avg / overall_avg) * 100)}% em relacao a media. Verifique status das campanhas.",
                "impact_pct": 15,
                "impact_window": 7,
            })

    # Alert: Low CTR across all campaigns
    if global_ctr < BENCH_CTR * 0.3 and total_imp > 5000:
        alerts.append({
            "severity": "warning",
            "icon": "thumbs-down",
            "title": "CTR critico em todas as campanhas",
            "text": f"CTR geral de {global_ctr}% esta muito abaixo do aceitavel. Acao imediata de revisao de criativos recomendada.",
            "impact_pct": 12,
            "impact_window": 14,
        })

    # ──────────────────────────────────────────────────
    # BLOCO 6: COMPARATIVO HISTÓRICO (current vs previous period)
    # ──────────────────────────────────────────────────
    # Determine the current period span
    all_dates = days_qs.aggregate(min_d=Min("date"), max_d=Max("date"))
    period_start = all_dates["min_d"]
    period_end = all_dates["max_d"]

    if date_from:
        try:
            period_start = datetime.strptime(date_from, "%Y-%m-%d").date()
        except ValueError:
            pass
    if date_to:
        try:
            period_end = datetime.strptime(date_to, "%Y-%m-%d").date()
        except ValueError:
            pass

    if period_start and period_end:
        period_days = (period_end - period_start).days + 1
        prev_end = period_start - timedelta(days=1)
        prev_start = prev_end - timedelta(days=period_days - 1)

        prev_qs = PlacementDay.objects.filter(
            placement_line_id__in=line_ids,
            date__gte=prev_start,
            date__lte=prev_end,
        )
        prev_stats = prev_qs.aggregate(
            imp=Sum("impressions"), clk=Sum("clicks"), cst=Sum("cost"),
        )
        prev_imp = prev_stats["imp"] or 0
        prev_clk = prev_stats["clk"] or 0
        prev_cost = float(prev_stats["cst"] or 0)
        prev_ctr = round((prev_clk / prev_imp * 100), 2) if prev_imp > 0 else 0
        prev_cpc = round((prev_cost / prev_clk), 2) if prev_clk > 0 else 0

        def _delta(cur, prev_val):
            if prev_val == 0:
                return {"value": cur, "delta": 0, "pct": 0, "dir": "neutral"}
            pct = round((cur - prev_val) / abs(prev_val) * 100, 1)
            return {
                "value": cur,
                "prev": prev_val,
                "delta": round(cur - prev_val, 2),
                "pct": pct,
                "dir": "up" if pct > 0 else ("down" if pct < 0 else "neutral"),
            }

        historical = {
            "has_prev": prev_qs.exists(),
            "period_label": f"{period_start.strftime('%d/%m')} - {period_end.strftime('%d/%m')}",
            "prev_label": f"{prev_start.strftime('%d/%m')} - {prev_end.strftime('%d/%m')}",
            "ctr": _delta(global_ctr, prev_ctr),
            "cpc": _delta(global_cpc, prev_cpc),
            "impressions": _delta(total_imp, prev_imp),
            "clicks": _delta(total_clk, prev_clk),
            "investment": _delta(round(total_cost, 2), round(prev_cost, 2)),
        }
    else:
        historical = {"has_prev": False}

    # ──────────────────────────────────────────────────
    # BLOCO 7: MATRIZ DE EFICIÊNCIA (per-channel efficiency)
    # ──────────────────────────────────────────────────
    channel_map = {}
    for line in lines_qs:
        ch = line.media_channel.upper()
        if ch not in channel_map:
            channel_map[ch] = {"line_ids": [], "label": ch}
        channel_map[ch]["line_ids"].append(line.id)

    efficiency_matrix = []
    for ch_key, ch_info in channel_map.items():
        ch_agg = days_qs.filter(placement_line_id__in=ch_info["line_ids"]).aggregate(
            imp=Sum("impressions"), clk=Sum("clicks"), cst=Sum("cost"),
        )
        ch_imp = ch_agg["imp"] or 0
        ch_clk = ch_agg["clk"] or 0
        ch_cost = float(ch_agg["cst"] or 0)
        if ch_imp == 0 and ch_clk == 0:
            continue
        ch_ctr = round((ch_clk / ch_imp * 100), 2) if ch_imp > 0 else 0
        ch_cpc = round((ch_cost / ch_clk), 2) if ch_clk > 0 else 0
        ch_cpm = round((ch_cost / ch_imp * 1000), 2) if ch_imp > 0 else 0
        # ROI proxy: clicks per R$ spent
        ch_roi = round((ch_clk / ch_cost), 2) if ch_cost > 0 else 0
        # Channel score: weighted composite
        ctr_s = min(ch_ctr / BENCH_CTR, 2.0) * 50 if BENCH_CTR > 0 else 50
        cpc_s = min(BENCH_CPC / ch_cpc, 2.0) * 50 if ch_cpc > 0 else 50
        roi_s = min(ch_roi / 0.5, 2.0) * 50  # 0.5 clicks/R$ benchmark
        ch_score = round(ctr_s * 0.35 + cpc_s * 0.35 + roi_s * 0.30)
        ch_score = max(0, min(100, ch_score))

        # Simple recommendation per channel
        if ch_score >= 60 and ch_ctr >= BENCH_CTR:
            rec_text = "Escalar investimento"
        elif ch_cpc > BENCH_CPC * 1.3 or ch_cpm > BENCH_CPM * 1.3:
            rec_text = "Reduzir lances / ajustar segmentacao"
        else:
            rec_text = "Testar novos criativos"

        efficiency_matrix.append({
            "channel": ch_info["label"],
            "impressions": ch_imp,
            "clicks": ch_clk,
            "cost": round(ch_cost, 2),
            "ctr": ch_ctr,
            "cpc": ch_cpc,
            "cpm": ch_cpm,
            "roi": ch_roi,
            "score": ch_score,
            "recommendation": rec_text,
        })
    efficiency_matrix.sort(key=lambda x: x["score"], reverse=True)

    # Grouped alerts and counts for UI filters
    alerts_grouped = {
        "critical": [a for a in alerts if a.get("severity") == "critical"],
        "warning": [a for a in alerts if a.get("severity") == "warning"],
        "info": [a for a in alerts if a.get("severity") == "info"],
    }
    alert_counts = {
        "all": len(alerts),
        "critical": len(alerts_grouped["critical"]),
        "warning": len(alerts_grouped["warning"]),
        "info": len(alerts_grouped["info"]),
    }

    # ──────────────────────────────────────────────────
    # BLOCO 8: SIMULADOR DE OTIMIZAÇÃO (data for JS)
    # ──────────────────────────────────────────────────
    # Provide per-platform averages for the simulator
    # Markets (regions) shares for optional redistribution UI
    markets_qs = (
        PlacementDay.objects.filter(placement_line_id__in=line_ids)
        .values("placement_line__market")
        .annotate(total_cost=Sum("cost"))
        .order_by("-total_cost")
    )
    _tot_market_cost = sum(float(m.get("total_cost") or 0) for m in markets_qs)
    markets_data = []
    if _tot_market_cost > 0:
        for m in markets_qs[:5]:
            name = (m.get("placement_line__market") or "Outros").strip() or "Outros"
            share = float(m.get("total_cost") or 0) / _tot_market_cost * 100
            markets_data.append({"name": name, "share": round(share, 2)})

    sim_data = {
        "google": {
            "cost": google_agg["cost"],
            "impressions": google_agg["impressions"],
            "clicks": google_agg["clicks"],
            "ctr": google_agg["ctr"],
            "cpc": google_agg["cpc"],
            "cpm": round((google_agg["cost"] / google_agg["impressions"] * 1000), 2) if google_agg["impressions"] > 0 else 0,
        },
        "meta": {
            "cost": meta_agg["cost"],
            "impressions": meta_agg["impressions"],
            "clicks": meta_agg["clicks"],
            "ctr": meta_agg["ctr"],
            "cpc": meta_agg["cpc"],
            "cpm": round((meta_agg["cost"] / meta_agg["impressions"] * 1000), 2) if meta_agg["impressions"] > 0 else 0,
        },
        "total_budget": round(total_cost, 2),
        "markets": markets_data,
    }

    # ── AI status check (non-blocking — insights loaded via AJAX) ──
    ai_summary = ""
    ai_status = None
    if ai_mode:
        try:
            from web.services.ai_analytics import check_ai_status
            ai_status = check_ai_status()
        except Exception:
            pass

    return render(request, template, {
        "active": "analytics",
        "page_title": "Analytics Intelligence" + (" (AI)" if ai_mode else ""),
        "ai_mode": ai_mode,
        "ai_status": ai_status,
        "ai_summary": ai_summary,
        "date_from": date_from,
        "date_to": date_to,
        # Global stats
        "total_imp": total_imp,
        "total_clk": total_clk,
        "total_cost": round(total_cost, 2),
        "global_ctr": global_ctr,
        "global_cpc": global_cpc,
        "cpm": cpm,
        # Platform stats
        "google": google_agg,
        "meta": meta_agg,
        # Performance Score (Bloco 1)
        "perf_score": perf_score,
        "score_class": score_class,
        "score_label": score_label,
        "score_dash_offset": round(477.5 - (perf_score / 100) * 477.5, 1),
        "score_breakdown": score_breakdown,
        "score_deficits": negative_impacts,
        # Insights (Bloco 2)
        "insights": insights,
        # Recommendations (Bloco 3)
        "recommendations": recommendations,
        # Funnel (Bloco 4)
        "funnel_steps": funnel_steps,
        # Alerts (Bloco 5)
        "alerts": alerts,
        # Historical comparison (Bloco 6)
        "historical": historical,
        # Efficiency matrix (Bloco 7)
        "efficiency_matrix": efficiency_matrix,
        "alerts_grouped": alerts_grouped,
        "alert_counts": alert_counts,
        # Simulator data (Bloco 8)
        "sim_data_json": json.dumps(sim_data),
        # Chart data
        "trend_labels_json": json.dumps(trend_labels),
        "trend_imp_json": json.dumps(trend_imp),
        "trend_clk_json": json.dumps(trend_clk),
        "trend_ma7_json": json.dumps(trend_ma7),
        "trend_signal": trend_signal,
        # Explicit comparisons
        "benchmarks": {"ctr": BENCH_CTR, "cpc": BENCH_CPC, "cpm": BENCH_CPM},
        "targets": {
            "ctr": float(request.GET.get("meta_ctr") or 0) or round(BENCH_CTR * 1.2, 2),
            "cpc": float(request.GET.get("meta_cpc") or 0) or round(BENCH_CPC * 0.9, 2),
            "cpm": float(request.GET.get("meta_cpm") or 0) or round(BENCH_CPM * 0.9, 2),
        },
        # Campaign table
        "campaigns": campaign_metrics,
        # Period comparison
        "period_comparison": period_comparison,
    })


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
    success_message = ""
    if request.method == "POST":
        form = ClienteForm(request.POST, request.FILES, instance=cliente)
        if form.is_valid():
            form.save()
            success_message = "Cliente atualizado com sucesso."
            cliente.refresh_from_db()
            form = ClienteForm(instance=cliente)
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
            "success_message": success_message,
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
@require_true_admin
def cliente_delete(request: HttpRequest, cliente_id: int) -> HttpResponse:
    if request.method != "POST":
        return redirect("web:clientes_detail", cliente_id=cliente_id)

    cliente = Cliente.objects.get(id=cliente_id)
    confirm_name = request.POST.get("confirm_name", "").strip()
    delete_mode = request.POST.get("delete_mode", "deactivate")

    if confirm_name != cliente.nome:
        return redirect("web:clientes_detail", cliente_id=cliente_id)

    nome_log = cliente.nome

    if delete_mode == "all":
        User = get_user_model()
        campaigns_qs = Campaign.objects.filter(cliente_id=cliente.id)
        for campaign in campaigns_qs:
            placements = PlacementLine.objects.filter(campaign=campaign)
            for placement in placements:
                PlacementDay.objects.filter(placement_line=placement).delete()
                PlacementCreative.objects.filter(placement_line=placement).delete()
            placements.delete()
            for piece in Piece.objects.filter(campaign=campaign):
                CreativeAsset.objects.filter(piece=piece).delete()
            Piece.objects.filter(campaign=campaign).delete()
            RegionInvestment.objects.filter(campaign=campaign).delete()
            ContractUpload.objects.filter(campaign=campaign).delete()
            MediaPlanUpload.objects.filter(campaign=campaign).delete()
        campaigns_qs.delete()
        User.objects.filter(cliente_id=cliente.id).delete()
        AuditLog.log(
            AuditLog.EventType.CLIENTE_DELETED,
            request=request,
            details={"nome": nome_log, "modo": "completo"},
        )
        cliente.delete()
        return redirect("web:clientes")
    else:
        cliente.ativo = False
        cliente.save()
        AuditLog.log(
            AuditLog.EventType.CLIENTE_DELETED,
            request=request,
            details={"nome": nome_log, "modo": "desativado"},
        )
        return redirect("web:clientes")


@login_required
@require_admin
def cliente_campaigns(request: HttpRequest, cliente_id: int) -> HttpResponse:
    from django.core.paginator import Paginator
    from django.db.models import Exists, OuterRef, Q

    cliente = Cliente.objects.get(id=cliente_id)
    campaigns_qs = Campaign.objects.filter(cliente_id=cliente.id)

    # Annotate placement-line presence so we can compute media_kind consistently
    # with /campanhas/<id>/ — the Campaign.media_type field is unreliable, so we
    # rely on PlacementLine.media_type counts + Google/Meta name heuristic.
    has_online = PlacementLine.objects.filter(campaign=OuterRef("pk"), media_type="online")
    has_offline = PlacementLine.objects.filter(campaign=OuterRef("pk"), media_type="offline")
    google_meta_q = Q(name__startswith="Google Ads - ") | Q(name__startswith="Meta Ads - ")
    campaigns_qs = campaigns_qs.annotate(
        _has_on=Exists(has_online),
        _has_off=Exists(has_offline),
    ).order_by("-created_at")

    # Search filter
    q = request.GET.get("q", "").strip()
    if q:
        campaigns_qs = campaigns_qs.filter(name__icontains=q)

    # Status filter
    status_filter = request.GET.get("status", "")
    if status_filter:
        campaigns_qs = campaigns_qs.filter(status=status_filter)

    # Meio filter (uses computed media_kind, not the stale Campaign.media_type field)
    meio_filter = request.GET.get("meio", "")
    if meio_filter == "online":
        campaigns_qs = campaigns_qs.filter(google_meta_q | Q(_has_on=True, _has_off=False))
    elif meio_filter == "offline":
        campaigns_qs = campaigns_qs.filter(_has_off=True, _has_on=False).exclude(google_meta_q)
    elif meio_filter == "mixed":
        campaigns_qs = campaigns_qs.filter(_has_on=True, _has_off=True).exclude(google_meta_q)

    paginator = Paginator(campaigns_qs, 10)
    # Sanitize page param: clamp to >= 1 and fall back to 1 on garbage input.
    # Django's get_page() should handle this but in 4.2.7 some edge cases
    # (empty string, redirect from upload with stale ?page=) propagate an
    # EmptyPage all the way up. Guarding here is harmless and bulletproof.
    try:
        page_number = max(1, int(request.GET.get("page") or 1))
    except (TypeError, ValueError):
        page_number = 1
    page_obj = paginator.get_page(page_number)

    # Compute media_kind for each campaign on the current page
    for c in page_obj.object_list:
        is_google_meta = c.name.startswith("Google Ads - ") or c.name.startswith("Meta Ads - ")
        if is_google_meta:
            c.media_kind = "online"
        elif c._has_on and not c._has_off:
            c.media_kind = "online"
        elif c._has_off and not c._has_on:
            c.media_kind = "offline"
        elif c._has_on and c._has_off:
            c.media_kind = "mixed"
        else:
            c.media_kind = "none"

    return render(
        request,
        "web/cliente_campaigns.html",
        {
            "active": "clientes",
            "page_title": "Campanhas",
            "cliente": cliente,
            "campaigns": page_obj,
            "page_obj": page_obj,
            "q": q,
            "status_filter": status_filter,
            "meio_filter": meio_filter,
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
def set_selected_cliente(request: HttpRequest) -> HttpResponse:
    """AJAX endpoint: sets session['selected_cliente_id'] for admin global filter."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        body = request.POST
    cliente_id = body.get("cliente_id")
    if cliente_id:
        try:
            cliente_id = int(cliente_id)
            if Cliente.objects.filter(id=cliente_id, ativo=True).exists():
                request.session["selected_cliente_id"] = cliente_id
            else:
                request.session.pop("selected_cliente_id", None)
        except (ValueError, TypeError):
            request.session.pop("selected_cliente_id", None)
    else:
        request.session.pop("selected_cliente_id", None)
    return JsonResponse({"ok": True})


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
            "active": "clientes",
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
    result = None
    form = MediaPlanUploadForm()

    if request.method == "POST":
        action = request.POST.get("_action") or "validate"

        if action == "import":
            upload_id = request.POST.get("upload_id")
            replace = bool(request.POST.get("replace_existing"))
            selected_sheets = request.POST.getlist("selected_sheets") or None
            upload = MediaPlanUpload.objects.filter(id=upload_id, campaign=campaign).first()
            if upload is None:
                form_errors = "Upload não encontrado."
            else:
                parsed = import_media_plan_xlsx(
                    campaign=campaign,
                    uploaded_file=upload.file,
                    replace_existing=replace,
                    selected_sheets=selected_sheets,
                )
                if parsed.get("ok"):
                    upload.summary = parsed
                    upload.save(update_fields=["summary"])
                    # Salva também como ContractUpload para registro
                    ContractUpload.objects.get_or_create(
                        campaign=campaign,
                        defaults={"file": upload.file.name},
                    )
                    AuditLog.log(
                        AuditLog.EventType.MEDIA_PLAN_UPLOADED,
                        request=request,
                        cliente=campaign.cliente,
                        details={"campaign_id": campaign.id, "campaign_name": campaign.name},
                    )
                    return redirect("web:contract_done", campaign_id=campaign.id)
                else:
                    form_errors = "; ".join(parsed.get("errors", ["Falha ao importar."]))
                    result = {"upload_id": upload_id}
        else:
            form = MediaPlanUploadForm(request.POST, request.FILES)
            if form.is_valid():
                xlsx = form.cleaned_data["xlsx_file"]
                upload = MediaPlanUpload.objects.create(campaign=campaign, file=xlsx, summary={})
                parsed = parse_media_plan_xlsx(upload.file)

                rows_per_sheet: dict[str, int] = {}
                for row in (parsed.get("parsed_rows") or []):
                    rows_per_sheet[row.sheet] = rows_per_sheet.get(row.sheet, 0) + 1
                detected = parsed.get("detected") or {}
                for sheet_name, info in (detected.get("sheets") or {}).items():
                    info["valid_rows"] = rows_per_sheet.get(sheet_name, 0)

                upload.summary = {
                    "ok": bool(parsed.get("ok")),
                    "errors": parsed.get("errors", []),
                    "sheets": parsed.get("sheets", []),
                    "total_rows": parsed.get("total_rows", 0),
                    "valid_rows": len(parsed.get("parsed_rows", []) or []),
                    "detected": detected,
                }
                upload.save(update_fields=["summary"])
                result = dict(upload.summary)
                result["upload_id"] = upload.id
            else:
                form_errors = "Selecione um arquivo .xlsx válido."

    return render(
        request,
        "web/contract_wizard_step2.html",
        {
            "active": "clientes",
            "page_title": "Contrato de Upload",
            "cliente": campaign.cliente,
            "campaign": campaign,
            "form": form,
            "form_errors": form_errors,
            "result": result,
        },
    )


def _build_media_tabs(unique_media_channels: set) -> list:
    """Build 4 fixed media type tabs: TV, Rádio, Impressa, Todas."""
    # Agrupamentos: cada tab filtra um ou mais media_channels
    TV_CHANNELS = {"tv_aberta", "paytv"}
    RADIO_CHANNELS = {"radio"}
    PRINT_CHANNELS = {"jornal", "revista", "magazine", "impresso"}

    tabs = []
    if unique_media_channels & TV_CHANNELS:
        tabs.append({"key": "tv", "label": "TV", "channels": ",".join(sorted(TV_CHANNELS & unique_media_channels))})
    if unique_media_channels & RADIO_CHANNELS:
        tabs.append({"key": "radio", "label": "Rádio", "channels": ",".join(sorted(RADIO_CHANNELS & unique_media_channels))})
    if unique_media_channels & PRINT_CHANNELS:
        tabs.append({"key": "impressa", "label": "Impressa", "channels": ",".join(sorted(PRINT_CHANNELS & unique_media_channels))})
    return tabs


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
    unique_media_channels: set = set()  # para tabs de tipo de mídia

    # Mídia impressa: para esses canais a planilha geralmente não traz código de
    # peça nos cabeçalhos, então renderizamos um card sintético "Veiculação <Tipo>"
    # mesmo sem peça vinculada.
    PRINT_CHANNELS = {"jornal", "revista", "magazine", "impresso"}
    PRINT_TYPE_LABELS = {
        "jornal": "Jornal",
        "revista": "Revista",
        "magazine": "Revista",
        "impresso": "Impresso",
    }
    PRINT_COLORS = {
        "jornal": "#fdba74",   # laranja claro
        "revista": "#f9a8d4",  # rosa
        "magazine": "#f9a8d4",
        "impresso": "#a3e635", # lima
    }

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

        # Coletar media_channel para tabs de tipo
        media_ch_norm = (line.media_channel or "").strip().lower()
        if media_ch_norm:
            unique_media_channels.add(media_ch_norm)

        # Buscar peças vinculadas a esta linha
        linked_pieces = list(line.placement_creatives.select_related("piece").all())

        is_print = media_ch_norm in PRINT_CHANNELS
        prop_text = (line.property_text or "").strip()

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
                    "property_text": prop_text,
                    "format_text": (line.format_text or "").strip(),
                })
        elif is_print:
            type_label = PRINT_TYPE_LABELS.get(media_ch_norm, "Impresso")
            title = f"Veiculação {type_label}"
            unique_piece_titles.add(title)
            grouped_by_channel[channel]["items"].append({
                "title": title,
                "piece_id": None,
                "piece_code": "",
                "channel": line.media_channel,
                "channel_name": channel,
                "market": market,
                "program": line.channel or line.program or "",
                "start": line.min_day,
                "end": line.max_day,
                "insertions": line.total_insertions or 0,
                "color": PRINT_COLORS.get(media_ch_norm, "#fcd34d"),
                "property_text": prop_text,
                "format_text": (line.format_text or "").strip(),
            })
        # Demais linhas sem peças vinculadas não entram na timeline

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
            y, m = current.year, current.month
            current = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)

    # Fallback de Investimento Total: se não há budget cadastrado nem custo
    # importado de placement days, usa o total da planilha financeira (FinancialSummary).
    investment_value = campaign.total_budget or totals.get("cost") or 0
    if not investment_value:
        fin_summary = getattr(campaign, "financial_summary", None)
        if fin_summary and fin_summary.total_valor_tabela:
            investment_value = fin_summary.total_valor_tabela

    return render(
        request,
        "web/contract_done.html",
        {
            "active": "campanhas",
            "page_title": "Timeline - Campanhas",
            "campaign": campaign,
            "cliente": campaign.cliente,
            "last_upload": last_upload,
            "totals": {
                "investment": investment_value,
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
            "media_type_tabs": _build_media_tabs(unique_media_channels),
            "role": role,
            "has_financial": campaign.financial_uploads.exists() or hasattr(campaign, "financial_summary"),
            "financial_client_visible": getattr(getattr(campaign, "financial_summary", None), "client_visible", False),
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
            selected_sheets = request.POST.getlist("selected_sheets") or None
            upload = MediaPlanUpload.objects.filter(id=upload_id, campaign=campaign).first()
            if upload is None:
                form_errors = "Upload não encontrado."
            else:
                parsed = import_media_plan_xlsx(campaign=campaign, uploaded_file=upload.file, replace_existing=replace, selected_sheets=selected_sheets)
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

                # Conta linhas válidas por aba e injeta no detected.sheets
                rows_per_sheet: dict[str, int] = {}
                for row in (parsed.get("parsed_rows") or []):
                    rows_per_sheet[row.sheet] = rows_per_sheet.get(row.sheet, 0) + 1
                detected = parsed.get("detected") or {}
                for sheet_name, info in (detected.get("sheets") or {}).items():
                    info["valid_rows"] = rows_per_sheet.get(sheet_name, 0)

                upload.summary = {
                    "ok": bool(parsed.get("ok")),
                    "errors": parsed.get("errors", []),
                    "sheets": parsed.get("sheets", []),
                    "total_rows": parsed.get("total_rows", 0),
                    "valid_rows": len(parsed.get("parsed_rows", []) or []),
                    "detected": detected,
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


@login_required
def api_campaign_detail(request: HttpRequest, campaign_id: int) -> HttpResponse:
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


@csrf_exempt
@login_required
def api_alerta_lido(request: HttpRequest, alerta_id: int) -> HttpResponse:
    """API para marcar um alerta como lido."""
    from accounts.models import Alert

    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Método não permitido"}, status=405)

    # Buscar o alerta
    alerta = Alert.objects.filter(id=alerta_id).first()
    if alerta is None:
        return JsonResponse({"success": False, "error": "Alerta não encontrado"}, status=404)

    # Verificar se o usuário tem acesso ao alerta (pertence ao cliente dele)
    cliente_id = effective_cliente_id(request)
    if cliente_id and alerta.cliente_id != cliente_id:
        return JsonResponse({"success": False, "error": "Acesso negado"}, status=403)

    # Marcar como lido
    alerta.marcar_como_lido(request.user)

    return JsonResponse({"success": True, "alerta_id": alerta_id})


@login_required
def relatorios_clientes(request: HttpRequest) -> HttpResponse:
    """Lista os clientes para seleção de relatórios."""
    role = effective_role(request)

    if role == "cliente":
        cliente_id = effective_cliente_id(request)
        return redirect("web:relatorios_campanhas", cliente_id=cliente_id)

    # Se admin selecionou cliente no sidebar, pula a página intermediária
    sel_cliente = selected_cliente_id(request)
    if sel_cliente:
        return redirect("web:relatorios_campanhas", cliente_id=sel_cliente)

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

    # Exclude campaigns that have digital placement lines (Google/Meta Ads integrations)
    digital_channels = ["google", "youtube", "display", "search", "meta"]
    digital_campaign_ids = (
        PlacementLine.objects.filter(
            media_channel__in=digital_channels,
            campaign__cliente_id=cliente_id,
        )
        .values_list("campaign_id", flat=True)
        .distinct()
    )
    campaigns = (
        Campaign.objects.filter(cliente_id=cliente_id, media_type=Campaign.MediaType.OFFLINE)
        .exclude(id__in=digital_campaign_ids)
        .select_related("cliente")
        .order_by("-created_at")
    )

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
            y, m = current.year, current.month
            current = date_type(y + 1, 1, 1) if m == 12 else date_type(y, m + 1, 1)

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
    # Se admin selecionou cliente no sidebar, pula a página intermediária
    sel_cliente = selected_cliente_id(request)
    if sel_cliente:
        return redirect("web:uploads_midia_campanhas", cliente_id=sel_cliente)

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
            "user_is_admin": effective_role(request) != "cliente",
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
        file_name = meta.get("original_name", "") or (primary_asset.file.name if primary_asset.file else "")
        if "video" in content_type:
            media_type = "video"
        elif "audio" in content_type:
            media_type = "audio"
        elif "image" in content_type:
            media_type = "image"
        elif piece.type == "html5" or "html" in content_type:
            # ZIP HTML5 banners cannot be rendered inline — show download prompt
            if "zip" in content_type or file_name.lower().endswith(".zip"):
                media_type = "html5_zip"
            else:
                media_type = "html5"
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
            "active": "pecas_criativos",
            "page_title": piece.title,
            "role": effective_role(request),
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
def api_piece_delete_assets(request: HttpRequest, piece_id: int) -> JsonResponse:
    """Delete all assets from a piece (keep the piece itself)."""
    if request.method != "POST":
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    piece = Piece.objects.filter(id=piece_id).first()
    if not piece:
        return JsonResponse({"error": "piece_not_found"}, status=404)
    count = piece.assets.count()
    piece.assets.all().delete()
    return JsonResponse({"ok": True, "deleted": count})


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
    if "type" in data and data["type"] in ["video", "audio", "image", "html5"]:
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


@login_required
@require_admin
def api_piece_create(request: HttpRequest, campaign_id: int) -> HttpResponse:
    """API para criar uma nova peça na campanha."""
    if request.method != "POST":
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    campaign = Campaign.objects.filter(id=campaign_id).first()
    if campaign is None:
        return JsonResponse({"error": "campaign_not_found"}, status=404)

    import json as _json
    try:
        data = _json.loads(request.body)
    except _json.JSONDecodeError:
        return JsonResponse({"error": "invalid_json"}, status=400)

    code = (data.get("code") or "").strip()
    title = (data.get("title") or "").strip()
    piece_type = data.get("type", "image")
    duration = 0
    try:
        duration = int(data.get("duration_sec", 0))
    except (ValueError, TypeError):
        pass

    if not code or not title:
        return JsonResponse({"error": "code and title are required"}, status=400)

    if piece_type not in ["video", "audio", "image", "html5"]:
        piece_type = "image"

    if Piece.objects.filter(campaign=campaign, code=code).exists():
        return JsonResponse({"error": f"Ja existe uma peca com o codigo '{code}' nesta campanha."}, status=400)

    piece = Piece.objects.create(
        campaign=campaign,
        code=code,
        title=title,
        type=piece_type,
        duration_sec=duration,
    )

    AuditLog.log(
        AuditLog.EventType.PIECE_CREATED,
        request=request,
        details={"piece_id": piece.id, "code": code, "campaign": campaign.name},
    )

    return JsonResponse({
        "ok": True,
        "piece": {
            "id": piece.id,
            "code": piece.code,
            "title": piece.title,
            "type": piece.type,
            "duration_sec": piece.duration_sec,
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


# ---------------------------------------------------------------------------
# Google Ads integration views
# ---------------------------------------------------------------------------


@login_required
@require_admin
def gads_auth_url(request: HttpRequest) -> HttpResponse:
    """Generate Google OAuth authorization URL and redirect."""
    from integrations.services.google_ads import get_authorization_url

    cliente_id = request.GET.get("cliente_id", "")
    customer_id = request.GET.get("customer_id", "")
    # Encode both in state as "cliente_id:customer_id"
    state = f"{cliente_id}:{customer_id}"
    url = get_authorization_url(state=state)
    return redirect(url)


@login_required
@require_admin
def gads_callback(request: HttpRequest) -> HttpResponse:
    """Handle the OAuth callback from Google."""
    import logging
    from integrations.services.google_ads import exchange_code
    from integrations.models import GoogleAdsAccount

    logger = logging.getLogger("web.gads")
    code = request.GET.get("code", "")
    state = request.GET.get("state", "")  # "cliente_id:customer_id"
    error = request.GET.get("error", "")

    if error:
        logger.warning("Google OAuth error: %s", error)
        request.session["gads_error"] = f"Google recusou a autorização: {error}"
        return redirect("web:integracoes")

    if not code:
        return redirect("web:integracoes")

    # Parse state — format: "cliente_id:customer_id"
    parts = state.split(":", 1)
    raw_cliente_id = parts[0] if parts else ""
    raw_customer_id = parts[1] if len(parts) > 1 else ""

    cliente_id = int(raw_cliente_id) if raw_cliente_id.isdigit() else None
    if not cliente_id:
        request.session["gads_error"] = "Cliente não identificado no retorno do OAuth."
        return redirect("web:integracoes")

    cliente = Cliente.objects.filter(id=cliente_id).first()
    if not cliente:
        request.session["gads_error"] = "Cliente não encontrado."
        return redirect("web:integracoes")

    customer_id = raw_customer_id.strip()
    if not customer_id:
        request.session["gads_error"] = "Customer ID do Google Ads não informado."
        return redirect("web:integracoes")

    # Exchange authorization code for tokens
    try:
        tokens = exchange_code(code)
        logger.info("Token exchange OK for cliente=%s customer_id=%s", cliente_id, customer_id)
    except Exception as exc:
        logger.exception("Token exchange failed: %s", exc)
        request.session["gads_error"] = f"Erro ao trocar código OAuth: {exc}"
        return redirect("web:integracoes")

    # Validate that the customer ID is accessible with these credentials
    from integrations.services.google_ads import list_accessible_customers
    accessible = list_accessible_customers(tokens["access_token"])
    cid_clean = customer_id.replace("-", "")
    if accessible and cid_clean not in accessible:
        formatted = [f"{c[:3]}-{c[3:6]}-{c[6:]}" for c in accessible]
        request.session["gads_error"] = (
            f"O Customer ID {customer_id} nao esta acessivel com esta conta Google. "
            f"Contas acessiveis: {', '.join(formatted)}"
        )
        return redirect("web:integracoes")

    # Save the account with the manually-provided Customer ID
    obj, created = GoogleAdsAccount.objects.get_or_create(
        cliente=cliente,
        customer_id=customer_id,
        defaults={
            "descriptive_name": f"Google Ads — {cliente.nome}",
            "token_expiry": tokens.get("expiry"),
            "is_active": True,
        },
    )
    obj.access_token = tokens["access_token"]
    obj.refresh_token = tokens["refresh_token"]
    obj.token_expiry = tokens.get("expiry")
    obj.is_active = True
    obj.save()

    # Remove any leftover "pending" placeholder for this client
    GoogleAdsAccount.objects.filter(cliente=cliente, customer_id="pending").delete()

    request.session["gads_success"] = (
        f"Conta Google Ads {customer_id} conectada com sucesso para {cliente.nome}."
    )
    return redirect("web:integracoes")


@login_required
@require_admin
def gads_disconnect(request: HttpRequest, account_id: int) -> HttpResponse:
    """Disconnect (deactivate) a Google Ads account."""
    from integrations.models import GoogleAdsAccount

    if request.method == "POST":
        account = GoogleAdsAccount.objects.filter(id=account_id).first()
        if account:
            account.is_active = False
            account.save(update_fields=["is_active", "updated_at"])
    return redirect("web:integracoes")


@login_required
@require_admin
def gads_sync(request: HttpRequest, account_id: int) -> HttpResponse:
    """Trigger a manual sync for a Google Ads account."""
    from integrations.models import GoogleAdsAccount
    from integrations.services.google_ads import full_sync

    if request.method == "POST":
        account = GoogleAdsAccount.objects.filter(id=account_id, is_active=True).first()
        if account:
            log = full_sync(account, days=180)
            if log.status == "success":
                request.session["gads_success"] = (
                    f"Sync concluido: {log.campaigns_synced} campanhas, "
                    f"{log.metrics_synced} metricas (ultimos 180 dias)."
                )
            else:
                request.session["gads_error"] = (
                    f"Erro no sync: {log.error_message}"
                )
    return redirect("web:integracoes")


@login_required
@require_admin
def gads_clear_logs(request: HttpRequest) -> HttpResponse:
    """Clear all sync logs."""
    from integrations.models import SyncLog

    if request.method == "POST":
        count, _ = SyncLog.objects.all().delete()
        request.session["gads_success"] = f"{count} registros de log removidos."
    return redirect("web:integracoes")


# ---------------------------------------------------------------------------
# Meta Ads views
# ---------------------------------------------------------------------------


@login_required
@require_admin
def mads_auth_url(request: HttpRequest) -> HttpResponse:
    """Generate Meta OAuth authorization URL and redirect."""
    from integrations.services.meta_ads import get_authorization_url

    cliente_id = request.GET.get("cliente_id", "")
    ad_account_id = request.GET.get("ad_account_id", "")
    state = f"{cliente_id}:{ad_account_id}"
    url = get_authorization_url(state=state)
    return redirect(url)


@login_required
@require_admin
def mads_callback(request: HttpRequest) -> HttpResponse:
    """Handle the OAuth callback from Meta."""
    import logging
    from integrations.services.meta_ads import exchange_code
    from integrations.models import MetaAdsAccount

    logger = logging.getLogger("web.mads")
    code = request.GET.get("code", "")
    state = request.GET.get("state", "")  # "cliente_id:ad_account_id"
    error = request.GET.get("error", "")
    error_reason = request.GET.get("error_reason", "")

    if error:
        logger.warning("Meta OAuth error: %s (%s)", error, error_reason)
        request.session["mads_error"] = f"Meta recusou a autorizacao: {error_reason or error}"
        return redirect("web:integracoes")

    if not code:
        return redirect("web:integracoes")

    # Parse state — format: "cliente_id:ad_account_id"
    parts = state.split(":", 1)
    raw_cliente_id = parts[0] if parts else ""
    raw_ad_account_id = parts[1] if len(parts) > 1 else ""

    cliente_id = int(raw_cliente_id) if raw_cliente_id.isdigit() else None
    if not cliente_id:
        request.session["mads_error"] = "Cliente nao identificado no retorno do OAuth."
        return redirect("web:integracoes")

    cliente = Cliente.objects.filter(id=cliente_id).first()
    if not cliente:
        request.session["mads_error"] = "Cliente nao encontrado."
        return redirect("web:integracoes")

    ad_account_id = raw_ad_account_id.strip()
    if not ad_account_id:
        request.session["mads_error"] = "Ad Account ID do Meta Ads nao informado."
        return redirect("web:integracoes")

    # Exchange code for long-lived token
    try:
        tokens = exchange_code(code)
        logger.info("Meta token exchange OK for cliente=%s ad_account=%s", cliente_id, ad_account_id)
    except Exception as exc:
        logger.exception("Meta token exchange failed: %s", exc)
        request.session["mads_error"] = f"Erro ao trocar codigo OAuth: {exc}"
        return redirect("web:integracoes")

    from datetime import timedelta as _td

    # Save the account
    obj, created = MetaAdsAccount.objects.get_or_create(
        cliente=cliente,
        ad_account_id=ad_account_id,
        defaults={
            "descriptive_name": f"Meta Ads — {cliente.nome}",
            "token_expiry": timezone.now() + _td(seconds=tokens.get("expires_in", 3600)),
            "is_active": True,
        },
    )
    obj.access_token = tokens["access_token"]
    obj.token_expiry = timezone.now() + _td(seconds=tokens.get("expires_in", 3600))
    obj.is_active = True
    obj.save()

    request.session["mads_success"] = (
        f"Conta Meta Ads {ad_account_id} conectada com sucesso para {cliente.nome}."
    )
    return redirect("web:integracoes")


@login_required
@require_admin
def mads_disconnect(request: HttpRequest, account_id: int) -> HttpResponse:
    """Disconnect (deactivate) a Meta Ads account."""
    from integrations.models import MetaAdsAccount

    if request.method == "POST":
        account = MetaAdsAccount.objects.filter(id=account_id).first()
        if account:
            account.is_active = False
            account.save(update_fields=["is_active", "updated_at"])
    return redirect("web:integracoes")


@login_required
@require_admin
def mads_sync(request: HttpRequest, account_id: int) -> HttpResponse:
    """Trigger a manual sync for a Meta Ads account."""
    from integrations.models import MetaAdsAccount
    from integrations.services.meta_ads import full_sync

    if request.method == "POST":
        account = MetaAdsAccount.objects.filter(id=account_id, is_active=True).first()
        if account:
            log = full_sync(account, days=180)
            if log.status == "success":
                request.session["mads_success"] = (
                    f"Sync concluido: {log.campaigns_synced} campanhas, "
                    f"{log.metrics_synced} metricas (ultimos 180 dias)."
                )
            else:
                request.session["mads_error"] = (
                    f"Erro no sync: {log.error_message}"
                )
    return redirect("web:integracoes")


@login_required
@require_admin
def mads_clear_logs(request: HttpRequest) -> HttpResponse:
    """Clear all Meta Ads sync logs."""
    from integrations.models import MetaSyncLog

    if request.method == "POST":
        count, _ = MetaSyncLog.objects.all().delete()
        request.session["mads_success"] = f"{count} registros de log removidos."
    return redirect("web:integracoes")


@login_required
@require_admin
def gads_clear_data(request: HttpRequest) -> HttpResponse:
    """Delete all synced Google Ads data (PlacementLine + PlacementDay cascade)."""
    if request.method == "POST":
        google_channels = ["google", "youtube", "display", "search"]
        lines = PlacementLine.objects.filter(
            media_channel__in=google_channels,
            external_ref__gt="",
        )
        count = lines.count()
        lines.delete()
        # Remove auto-created parent campaigns (empty after purge)
        Campaign.objects.filter(
            name__startswith="Google Ads - ",
            placement_lines__isnull=True,
        ).delete()
        request.session["gads_success"] = (
            f"Dados Google Ads removidos: {count} linhas de veiculacao e metricas associadas."
        )
    return redirect("web:integracoes")


@login_required
@require_admin
def mads_clear_data(request: HttpRequest) -> HttpResponse:
    """Delete all synced Meta Ads data (PlacementLine + PlacementDay cascade)."""
    if request.method == "POST":
        lines = PlacementLine.objects.filter(
            media_channel="meta",
            external_ref__gt="",
        )
        count = lines.count()
        lines.delete()
        Campaign.objects.filter(
            name__startswith="Meta Ads - ",
            placement_lines__isnull=True,
        ).delete()
        request.session["mads_success"] = (
            f"Dados Meta Ads removidos: {count} linhas de veiculacao e metricas associadas."
        )
    return redirect("web:integracoes")


@login_required
def api_campaign_drilldown(request: HttpRequest, line_id: int) -> JsonResponse:
    """Return ad groups and ads for a campaign line (drill-down)."""
    from django.db.models import Sum
    from campaigns.models import AdGroup, Ad

    line = PlacementLine.objects.filter(id=line_id).first()
    if not line:
        return JsonResponse({"ok": False, "error": "not_found"}, status=404)

    date_from = request.GET.get("date_from", "")
    date_to = request.GET.get("date_to", "")

    ad_groups = []
    for ag in line.ad_groups.order_by("name"):
        days_qs = ag.days.all()
        if date_from:
            days_qs = days_qs.filter(date__gte=date_from)
        if date_to:
            days_qs = days_qs.filter(date__lte=date_to)
        stats = days_qs.aggregate(imp=Sum("impressions"), clk=Sum("clicks"), cst=Sum("cost"))
        imp = stats["imp"] or 0
        clk = stats["clk"] or 0
        cst = float(stats["cst"] or 0)

        ads_list = []
        for ad in ag.ads.order_by("name"):
            ad_days = ad.days.all()
            if date_from:
                ad_days = ad_days.filter(date__gte=date_from)
            if date_to:
                ad_days = ad_days.filter(date__lte=date_to)
            ad_stats = ad_days.aggregate(imp=Sum("impressions"), clk=Sum("clicks"), cst=Sum("cost"))
            ad_imp = ad_stats["imp"] or 0
            ad_clk = ad_stats["clk"] or 0
            ad_cst = float(ad_stats["cst"] or 0)
            ads_list.append({
                "id": ad.id,
                "name": ad.name or ad.headline or f"Ad #{ad.external_ref}",
                "type": ad.get_ad_type_display(),
                "status": ad.get_status_display(),
                "final_url": ad.final_url,
                "impressions": ad_imp,
                "clicks": ad_clk,
                "ctr": round((ad_clk / ad_imp * 100), 2) if ad_imp > 0 else 0,
                "cost": round(ad_cst, 2),
                "cpc": round((ad_cst / ad_clk), 2) if ad_clk > 0 else 0,
            })

        ad_groups.append({
            "id": ag.id,
            "name": ag.name,
            "status": ag.get_status_display(),
            "impressions": imp,
            "clicks": clk,
            "ctr": round((clk / imp * 100), 2) if imp > 0 else 0,
            "cost": round(cst, 2),
            "cpc": round((cst / clk), 2) if clk > 0 else 0,
            "ads_count": len(ads_list),
            "ads": ads_list,
        })

    # Fetch creative assets linked to this placement line
    creatives = []
    for pc in line.placement_creatives.select_related("piece").all():
        piece = pc.piece
        assets = []
        for asset in piece.assets.all():
            asset_url = ""
            if asset.file:
                try:
                    asset_url = asset.file.url
                except ValueError:
                    pass
            assets.append({
                "id": asset.id,
                "file_url": asset_url,
                "preview_url": asset.preview_url,
                "metadata": asset.metadata or {},
            })
        creatives.append({
            "id": piece.id,
            "code": piece.code,
            "title": piece.title,
            "type": piece.get_type_display(),
            "type_raw": piece.type,
            "status": piece.get_status_display(),
            "notes": piece.notes,
            "assets": assets,
        })

    return JsonResponse({
        "ok": True,
        "campaign": line.channel or line.property_text,
        "ad_groups_count": len(ad_groups),
        "ad_groups": ad_groups,
        "creatives": creatives,
        "creatives_count": len(creatives),
    })


@login_required
def api_veiculacao_data(request: HttpRequest) -> JsonResponse:
    """API endpoint for veiculação chart data (JSON)."""
    cliente_id = effective_cliente_id(request)
    if not cliente_id and is_admin(request.user):
        cliente_id = selected_cliente_id(request)

    platform = request.GET.get("platform", "all")
    google_channels = ["google", "youtube", "display", "search"]
    meta_channels = ["meta"]
    if platform == "google":
        channels = google_channels
    elif platform == "meta":
        channels = meta_channels
    else:
        channels = google_channels + meta_channels
    lines_qs = PlacementLine.objects.filter(media_channel__in=channels)
    if cliente_id:
        lines_qs = lines_qs.filter(campaign__cliente_id=cliente_id)

    line_ids = list(lines_qs.values_list("id", flat=True))

    date_from = request.GET.get("date_from", "")
    date_to = request.GET.get("date_to", "")
    days_qs = PlacementDay.objects.filter(placement_line_id__in=line_ids)
    if date_from:
        days_qs = days_qs.filter(date__gte=date_from)
    if date_to:
        days_qs = days_qs.filter(date__lte=date_to)

    daily = list(
        days_qs.values("date")
        .annotate(
            impressions=Sum("impressions"),
            clicks=Sum("clicks"),
            cost=Sum("cost"),
        )
        .order_by("date")
    )

    for d in daily:
        d["date"] = str(d["date"])
        d["cost"] = float(d["cost"] or 0)
        d["impressions"] = d["impressions"] or 0
        d["clicks"] = d["clicks"] or 0

    return JsonResponse({"daily": daily})


# ── Financial integration views ───────────────────────────────────────────────

@login_required
def campaign_financeiro(request: HttpRequest, campaign_id: int) -> HttpResponse:
    """Exibe o dashboard financeiro da campanha (6 módulos)."""
    from django.db.models import Sum

    campaign = Campaign.objects.filter(id=campaign_id).select_related("cliente").first()
    if campaign is None:
        return redirect("web:campanhas")

    role = effective_role(request)

    try:
        fs = campaign.financial_summary
    except Exception:
        fs = None

    # Cliente só acessa se client_visible estiver habilitado
    if role == "cliente" and (not fs or not fs.client_visible):
        return redirect("web:contract_done", campaign_id=campaign.id)

    efficiencies = list(campaign.media_efficiencies.order_by("channel_type", "veiculo"))
    pi_controls = list(campaign.pi_controls.order_by("vencimento"))
    region_investments = list(campaign.region_investments.order_by("order"))

    # Build chart data for split by channel
    channel_labels = []
    channel_values = []
    if fs and fs.data_by_channel:
        for ch, data in fs.data_by_channel.items():
            label_map = {
                "tv_aberta": "TV Aberta", "paytv": "Pay TV", "radio": "Rádio",
                "jornal": "Jornal", "digital": "Digital", "ooh": "OOH",
            }
            v = data.get("valor_liquido") or data.get("valor_bruto")
            if v:
                channel_labels.append(label_map.get(ch, ch))
                channel_values.append(float(v))

    # Monthly investment chart data
    monthly_labels = []
    monthly_values = []
    if fs and fs.monthly_investment:
        for item in fs.monthly_investment:
            monthly_labels.append(item.get("month", ""))
            monthly_values.append(float(item.get("valor") or 0))

    # PI alerts: count overdue / due soon
    from datetime import date
    today = date.today()
    pi_overdue = sum(1 for pi in pi_controls if pi.vencimento and pi.vencimento < today and pi.status == "pendente")
    pi_due_soon = sum(1 for pi in pi_controls if pi.vencimento and today <= pi.vencimento <= date(today.year, today.month + 1 if today.month < 12 else 1, today.day) and pi.status == "pendente")

    # Distinct values for table filters
    meio_options = sorted(set(e.channel_type for e in efficiencies if e.channel_type))
    veiculo_options = sorted(set(e.veiculo for e in efficiencies if e.veiculo))

    import json as _json
    return render(request, "web/campaign_financial.html", {
        "active": "dashboard",
        "page_title": f"Financeiro — {campaign.name}",
        "cliente": campaign.cliente,
        "campaign": campaign,
        "fs": fs,
        "efficiencies": efficiencies,
        "pi_controls": pi_controls,
        "region_investments": region_investments,
        "channel_labels_json": _json.dumps(channel_labels),
        "channel_values_json": _json.dumps(channel_values),
        "monthly_labels_json": _json.dumps(monthly_labels),
        "monthly_values_json": _json.dumps(monthly_values),
        "pi_overdue": pi_overdue,
        "pi_due_soon": pi_due_soon,
        "meio_options": meio_options,
        "veiculo_options": veiculo_options,
        "role": role,
        "visibility": (fs.visibility if fs else {}) or {},
        "visibility_json": _json.dumps((fs.visibility if fs else {}) or {}),
        "client_visible": fs.client_visible if fs else False,
    })


@login_required
@require_admin
def campaign_financial_upload(request: HttpRequest, campaign_id: int) -> HttpResponse:
    """Upload e importação de planilha financeira."""
    from django.core.files.base import ContentFile

    campaign = Campaign.objects.filter(id=campaign_id).select_related("cliente").first()
    if campaign is None:
        return redirect("web:campanhas")

    form_errors = ""
    result = None

    if request.method == "POST":
        action = request.POST.get("_action") or "validate"

        if action == "import":
            upload_id = request.POST.get("upload_id")
            upload = FinancialUpload.objects.filter(id=upload_id, campaign=campaign).first()
            if upload is None:
                form_errors = "Upload não encontrado."
            else:
                parsed = parse_financial_xlsx(upload.file)
                if parsed.get("ok"):
                    import_result = import_financial_data(campaign=campaign, parsed=parsed)
                    upload.summary = parsed
                    upload.save(update_fields=["summary"])
                    AuditLog.log(
                        AuditLog.EventType.MEDIA_PLAN_UPLOADED,
                        user=request.user,
                        details={"type": "financial", "upload_id": upload.id, "campaign_id": campaign.id},
                    )
                    return redirect("web:campaign_financeiro", campaign_id=campaign.id)
                else:
                    form_errors = "; ".join(parsed.get("errors") or ["Falha ao importar."])
                    result = {"upload_id": upload_id, "errors": parsed.get("errors", [])}
        else:
            # validate: save file, run parse preview
            xlsx = request.FILES.get("xlsx_file")
            if xlsx is None or not xlsx.name.endswith(".xlsx"):
                form_errors = "Selecione um arquivo .xlsx válido."
            else:
                upload = FinancialUpload.objects.create(campaign=campaign, file=xlsx, summary={})
                parsed = parse_financial_xlsx(upload.file)
                sheets_found = parsed.get("sheets_found") or []
                eff_rows = parsed.get("media_efficiencies") or []
                pi_rows = parsed.get("pi_controls") or []
                region_rows = parsed.get("region_investments") or []
                resumo = parsed.get("resumo_meios") or {}

                # Build per-sheet detail for selection UI.
                # Only RESUMO DE MEIOS * and CUSTO GERAÇÃO * are financial tabs.
                # Everything else (COVER, TV ABERTA, RÁDIO, JORNAL, DIGITAL, etc.)
                # belongs to the media plan upload and must come locked here.
                from campaigns.financial_xlsx_worker import _norm
                sheet_details = {}

                resumo_sheets = [s for s in sheets_found if "resumo" in _norm(s) and "meios" in _norm(s)]
                geracao_sheets = [s for s in sheets_found if "custo" in _norm(s) and "geracao" in _norm(s)]
                geracao_total = len(parsed.get("custo_geracao") or [])

                # Distribute eff_rows count evenly across resumo sheets (parser merges them).
                eff_per_resumo = (len(eff_rows) // len(resumo_sheets)) if resumo_sheets else 0
                # Distribute geração count similarly.
                ger_per_sheet = (geracao_total // len(geracao_sheets)) if geracao_sheets else 0

                for s in sheets_found:
                    if s in resumo_sheets:
                        sheet_details[s] = {
                            "name": s,
                            "rows": eff_per_resumo,
                            "type": "Resumo de Meios",
                            "is_financial": True,
                        }
                    elif s in geracao_sheets:
                        sheet_details[s] = {
                            "name": s,
                            "rows": ger_per_sheet,
                            "type": "Custo Geração",
                            "is_financial": True,
                        }
                    else:
                        sheet_details[s] = {
                            "name": s,
                            "rows": 0,
                            "type": "",
                            "is_financial": False,
                        }

                upload.summary = {
                    "ok": bool(parsed.get("ok")),
                    "errors": parsed.get("errors", []),
                    "sheets_found": sheets_found,
                    "sheet_details": sheet_details,
                    "pi_count": len(pi_rows),
                    "eff_count": len(eff_rows),
                    "region_count": len(region_rows),
                    "channels": len(resumo),
                }
                upload.save(update_fields=["summary"])
                result = dict(upload.summary)
                result["upload_id"] = upload.id

    return render(request, "web/campaign_financial_upload.html", {
        "active": "dashboard",
        "page_title": "Upload Financeiro",
        "cliente": campaign.cliente,
        "campaign": campaign,
        "form_errors": form_errors,
        "result": result,
    })


@login_required
@require_admin
def campaign_financial_delete(request: HttpRequest, campaign_id: int) -> HttpResponse:
    """Deleta todos os dados financeiros de uma campanha."""
    from campaigns.models import FinancialSummary, MediaEfficiency, PIControl

    if request.method != "POST":
        return redirect("web:campaign_financeiro", campaign_id=campaign_id)

    campaign = Campaign.objects.filter(id=campaign_id).select_related("cliente").first()
    if campaign is None:
        return redirect("web:campanhas")

    # Delete all financial data
    FinancialUpload.objects.filter(campaign=campaign).delete()
    FinancialSummary.objects.filter(campaign=campaign).delete()
    MediaEfficiency.objects.filter(campaign=campaign).delete()
    PIControl.objects.filter(campaign=campaign).delete()
    RegionInvestment.objects.filter(campaign=campaign).delete()

    AuditLog.log(
        AuditLog.EventType.MEDIA_PLAN_UPLOADED,
        user=request.user,
        details={"type": "financial_delete", "campaign_id": campaign.id},
    )

    return redirect("web:campaign_financeiro", campaign_id=campaign.id)


@csrf_exempt
@login_required
@require_admin
def api_efficiency_detail(request: HttpRequest, eff_id: int) -> JsonResponse:
    """GET = detail, PUT/PATCH = update, DELETE = delete a MediaEfficiency row."""
    from campaigns.models import MediaEfficiency
    from decimal import Decimal, InvalidOperation

    eff = MediaEfficiency.objects.filter(id=eff_id).first()
    if eff is None:
        return JsonResponse({"error": "Not found"}, status=404)

    if request.method == "GET":
        return JsonResponse({
            "id": eff.id,
            "channel_type": eff.channel_type,
            "veiculo": eff.veiculo,
            "programa": eff.programa,
            "praca": eff.praca,
            "insercoes": eff.insercoes,
            "trp": float(eff.trp) if eff.trp else None,
            "cpp": float(eff.cpp) if eff.cpp else None,
            "custo_tabela": float(eff.custo_tabela) if eff.custo_tabela else None,
            "custo_negociado": float(eff.custo_negociado) if eff.custo_negociado else None,
            "impactos": eff.impactos,
            "cpm": float(eff.cpm) if eff.cpm else None,
            "ia_pct": float(eff.ia_pct) if eff.ia_pct else None,
            "formato": eff.formato,
            "circulacao": eff.circulacao,
            "valor": float(eff.valor) if eff.valor else None,
        })

    if request.method == "DELETE":
        campaign_id = eff.campaign_id
        eff.delete()
        return JsonResponse({"ok": True, "campaign_id": campaign_id})

    if request.method in ("PUT", "PATCH"):
        import json as _json
        try:
            data = _json.loads(request.body)
        except _json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        def _dec(v):
            if v is None or v == "":
                return None
            try:
                return Decimal(str(v))
            except InvalidOperation:
                return None

        for field in ("veiculo", "programa", "praca", "formato", "channel_type"):
            if field in data:
                setattr(eff, field, str(data[field]).strip())
        for field in ("insercoes", "impactos", "circulacao"):
            if field in data:
                v = data[field]
                setattr(eff, field, int(v) if v is not None and v != "" else None)
        for field in ("trp", "cpp", "custo_tabela", "custo_negociado", "cpm", "ia_pct", "valor"):
            if field in data:
                setattr(eff, field, _dec(data[field]))
        eff.save()
        return JsonResponse({"ok": True, "id": eff.id})

    return JsonResponse({"error": "Method not allowed"}, status=405)


@login_required
@require_admin
def api_financial_summary(request: HttpRequest, campaign_id: int) -> JsonResponse:
    """GET/PATCH FinancialSummary for a campaign. Creates if not exists on PATCH."""
    from campaigns.models import FinancialSummary
    from decimal import Decimal, InvalidOperation
    import json as _json

    campaign = Campaign.objects.filter(id=campaign_id).first()
    if campaign is None:
        return JsonResponse({"error": "Campaign not found"}, status=404)

    DECIMAL_FIELDS = (
        "total_valor_tabela", "total_valor_negociado", "total_desembolso",
        "desconto_pct", "grp_pct", "cobertura_pct", "frequencia_eficaz",
    )
    JSON_FIELDS = ("data_by_channel", "monthly_investment")

    if request.method == "GET":
        fs = getattr(campaign, "financial_summary", None)
        if fs is None:
            return JsonResponse({"exists": False})
        data = {"exists": True}
        for f in DECIMAL_FIELDS:
            v = getattr(fs, f, None)
            data[f] = float(v) if v is not None else None
        for f in JSON_FIELDS:
            data[f] = getattr(fs, f, None)
        return JsonResponse(data)

    if request.method in ("PUT", "PATCH"):
        try:
            body = _json.loads(request.body)
        except _json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        fs, created = FinancialSummary.objects.get_or_create(campaign=campaign)

        def _dec(v):
            if v is None or v == "":
                return None
            try:
                return Decimal(str(v))
            except InvalidOperation:
                return None

        for f in DECIMAL_FIELDS:
            if f in body:
                setattr(fs, f, _dec(body[f]))
        for f in JSON_FIELDS:
            if f in body:
                setattr(fs, f, body[f])

        # Auto-calculate desconto if both tabela and desembolso present
        if fs.total_valor_tabela and fs.total_desembolso and fs.total_valor_tabela > 0:
            if "desconto_pct" not in body or body.get("desconto_pct") is None:
                fs.desconto_pct = Decimal(str(
                    round((1 - float(fs.total_desembolso) / float(fs.total_valor_tabela)) * 100, 2)
                ))

        fs.save()
        return JsonResponse({"ok": True, "created": created})

    return JsonResponse({"error": "Method not allowed"}, status=405)


@login_required
@require_admin
def api_financial_visibility(request: HttpRequest, campaign_id: int) -> JsonResponse:
    """Toggle visibility of financial fields/sections for client view."""
    from campaigns.models import FinancialSummary
    import json as _json

    campaign = Campaign.objects.filter(id=campaign_id).first()
    if campaign is None:
        return JsonResponse({"error": "Not found"}, status=404)

    fs, _ = FinancialSummary.objects.get_or_create(campaign=campaign)

    if request.method == "GET":
        return JsonResponse({
            "client_visible": fs.client_visible,
            "visibility": fs.visibility or {},
        })

    if request.method in ("PUT", "PATCH"):
        try:
            data = _json.loads(request.body)
        except _json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        if "client_visible" in data:
            fs.client_visible = bool(data["client_visible"])
        if "visibility" in data:
            current = fs.visibility or {}
            current.update(data["visibility"])
            fs.visibility = current
        fs.save(update_fields=["client_visible", "visibility"])
        AuditLog.log(
            AuditLog.EventType.VISIBILITY_CHANGED,
            request=request,
            details={"campaign_id": campaign_id, "client_visible": fs.client_visible, "changes": data},
        )
        return JsonResponse({"ok": True, "client_visible": fs.client_visible, "visibility": fs.visibility})

    return JsonResponse({"error": "Method not allowed"}, status=405)


@login_required
def api_search_campaigns(request: HttpRequest) -> JsonResponse:
    """Search campaigns by name, return JSON results."""
    q = request.GET.get("q", "").strip()
    if len(q) < 2:
        return JsonResponse({"results": []})

    role = effective_role(request)
    qs = Campaign.objects.select_related("cliente").order_by("-created_at")

    if role == "cliente":
        cliente_id = effective_cliente_id(request)
        if cliente_id:
            qs = qs.filter(cliente_id=cliente_id)
    else:
        sel = selected_cliente_id(request)
        if sel:
            qs = qs.filter(cliente_id=sel)

    qs = qs.filter(name__icontains=q)[:15]

    results = []
    for c in qs:
        results.append({
            "id": c.id,
            "name": c.name,
            "cliente": c.cliente.nome if c.cliente else "",
            "status": c.status,
            "media_type": c.media_type,
            "start_date": c.start_date.strftime("%d/%m/%Y") if c.start_date else "",
            "end_date": c.end_date.strftime("%d/%m/%Y") if c.end_date else "",
            "url": f"/contratos/upload/{c.id}/concluido/",
        })
    return JsonResponse({"results": results})


# ── User Profile ──────────────────────────────────────────────────────────────

@login_required
def user_profile(request: HttpRequest) -> HttpResponse:
    """Página de perfil e configurações do usuário."""
    from accounts.models import User
    from django.contrib.auth import update_session_auth_hash

    user = request.user
    success_msg = ""
    error_msg = ""

    if request.method == "POST":
        section = request.POST.get("_section", "info")

        if section == "avatar":
            import io, json as _json
            from PIL import Image
            from django.core.files.base import ContentFile

            avatar_file = request.FILES.get("avatar")
            crop_data = request.POST.get("crop_data", "")
            if avatar_file:
                try:
                    img = Image.open(avatar_file)
                    if img.mode in ("RGBA", "P"):
                        img = img.convert("RGB")
                    # Apply crop if provided
                    if crop_data:
                        try:
                            cd = _json.loads(crop_data)
                            # Crop values are ratios 0-1
                            w, h = img.size
                            left = int(cd.get("x", 0) * w)
                            top = int(cd.get("y", 0) * h)
                            right = left + int(cd.get("width", 1) * w)
                            bottom = top + int(cd.get("height", 1) * h)
                            img = img.crop((left, top, right, bottom))
                        except (ValueError, KeyError):
                            pass
                    # Resize to 256x256
                    img = img.resize((256, 256), Image.LANCZOS if hasattr(Image, "LANCZOS") else Image.ANTIALIAS)
                    buf = io.BytesIO()
                    img.save(buf, format="JPEG", quality=85)
                    buf.seek(0)
                    fname = f"avatar_{user.pk}.jpg"
                    user.avatar.save(fname, ContentFile(buf.read()), save=True)
                    success_msg = "Foto atualizada com sucesso."
                except Exception as e:
                    error_msg = f"Erro ao processar imagem: {e}"
            else:
                error_msg = "Selecione uma imagem."

        elif section == "info":
            user.first_name = request.POST.get("first_name", "").strip()
            user.last_name = request.POST.get("last_name", "").strip()
            user.email = request.POST.get("email", "").strip()
            new_username = request.POST.get("username", "").strip()
            if new_username and new_username != user.username:
                if User.objects.filter(username=new_username).exclude(pk=user.pk).exists():
                    error_msg = "Este nome de usuário já está em uso."
                else:
                    user.username = new_username
            if not error_msg:
                user.save(update_fields=["first_name", "last_name", "email", "username"])
                success_msg = "Informações atualizadas com sucesso."

        elif section == "password":
            current = request.POST.get("current_password", "")
            new_pw = request.POST.get("new_password", "")
            confirm = request.POST.get("confirm_password", "")
            if not user.check_password(current):
                error_msg = "Senha atual incorreta."
            elif len(new_pw) < 6:
                error_msg = "A nova senha deve ter pelo menos 6 caracteres."
            elif new_pw != confirm:
                error_msg = "As senhas não conferem."
            else:
                user.set_password(new_pw)
                user.save(update_fields=["password"])
                update_session_auth_hash(request, user)
                success_msg = "Senha alterada com sucesso."

    role = effective_role(request)
    return render(request, "web/user_profile.html", {
        "active": "",
        "page_title": "Meu Perfil",
        "profile_user": user,
        "role": role,
        "success_msg": success_msg,
        "error_msg": error_msg,
    })


# ── AI Executive Report API ──────────────────────────────────────────────────

@login_required
def api_ai_insights(request: HttpRequest) -> JsonResponse:
    """Return AI-generated insights/alerts/recommendations via AJAX (non-blocking page load)."""
    from django.db.models import Sum
    from web.services.ai_analytics import generate_analytics_insights, persist_ai_insights

    cliente_id = effective_cliente_id(request)
    if not cliente_id and is_admin(request.user):
        cliente_id = selected_cliente_id(request)
    if not cliente_id:
        return JsonResponse({"ok": False, "error": "Selecione um cliente"})

    date_from = request.GET.get("date_from", "")
    date_to = request.GET.get("date_to", "")

    # Compute the same metrics the analytics view computes
    google_channels = ["google", "search", "display", "youtube", "shopping", "pmax"]
    meta_channels = ["meta", "facebook", "instagram"]
    lines_qs = PlacementLine.objects.filter(campaign__cliente_id=cliente_id)
    line_ids = list(lines_qs.values_list("id", flat=True))
    if not line_ids:
        return JsonResponse({"ok": False, "error": "Sem dados"})

    days_qs = PlacementDay.objects.filter(placement_line_id__in=line_ids)
    if date_from:
        days_qs = days_qs.filter(date__gte=date_from)
    if date_to:
        days_qs = days_qs.filter(date__lte=date_to)

    stats = days_qs.aggregate(total_imp=Sum("impressions"), total_clk=Sum("clicks"), total_cost=Sum("cost"))
    total_imp = stats["total_imp"] or 0
    total_clk = stats["total_clk"] or 0
    total_cost = float(stats["total_cost"] or 0)
    global_ctr = round((total_clk / total_imp * 100), 2) if total_imp > 0 else 0
    global_cpc = round((total_cost / total_clk), 2) if total_clk > 0 else 0
    cpm = round((total_cost / total_imp * 1000), 2) if total_imp > 0 else 0

    BENCH_CTR, BENCH_CPC, BENCH_CPM = 2.0, 3.50, 15.00

    ai_context = {
        "total_imp": total_imp, "total_clk": total_clk,
        "global_ctr": global_ctr, "cpc": global_cpc, "cpm": cpm,
        "total_cost": round(total_cost, 2),
        "date_from": date_from, "date_to": date_to,
        "benchmarks": {"ctr": BENCH_CTR, "cpc": BENCH_CPC, "cpm": BENCH_CPM},
    }

    ai_result = generate_analytics_insights(ai_context, cliente_id=cliente_id or 0)
    if not ai_result:
        return JsonResponse({"ok": False, "error": "IA indisponível"})

    # Persist
    try:
        persist_ai_insights(cliente_id, date_from, date_to, ai_result)
    except Exception:
        pass

    return JsonResponse({
        "ok": True,
        "insights": ai_result.get("insights", []),
        "alerts": ai_result.get("alerts", []),
        "recommendations": ai_result.get("recommendations", []),
        "executive_summary": ai_result.get("executive_summary", ""),
    })


@login_required
def api_ai_executive_report(request: HttpRequest) -> JsonResponse:
    """Generate an AI-powered executive report via AJAX."""
    from web.services.ai_analytics import generate_executive_report

    cliente_id = effective_cliente_id(request)
    if not cliente_id and is_admin(request.user):
        cliente_id = selected_cliente_id(request)

    if not cliente_id:
        return JsonResponse({"error": "Selecione um cliente."}, status=400)

    date_from = request.GET.get("date_from", "")
    date_to = request.GET.get("date_to", "")

    # Quick aggregate for context
    google_channels = ["google", "youtube", "display", "search"]
    meta_channels = ["meta"]
    all_channels = google_channels + meta_channels

    lines_qs = PlacementLine.objects.filter(
        media_channel__in=all_channels, campaign__cliente_id=cliente_id,
    )
    line_ids = list(lines_qs.values_list("id", flat=True))
    days_qs = PlacementDay.objects.filter(placement_line_id__in=line_ids)
    if date_from:
        days_qs = days_qs.filter(date__gte=date_from)
    if date_to:
        days_qs = days_qs.filter(date__lte=date_to)

    from django.db.models import Sum
    stats = days_qs.aggregate(
        total_imp=Sum("impressions"), total_clk=Sum("clicks"), total_cost=Sum("cost"),
    )
    total_imp = stats["total_imp"] or 0
    total_clk = stats["total_clk"] or 0
    total_cost = float(stats["total_cost"] or 0)
    global_ctr = round((total_clk / total_imp * 100), 2) if total_imp > 0 else 0
    global_cpc = round((total_cost / total_clk), 2) if total_clk > 0 else 0
    cpm = round((total_cost / total_imp * 1000), 2) if total_imp > 0 else 0

    context = {
        "total_imp": total_imp, "total_clk": total_clk,
        "global_ctr": global_ctr, "cpc": global_cpc, "cpm": cpm,
        "total_cost": round(total_cost, 2),
        "date_from": date_from, "date_to": date_to,
        "benchmarks": {"ctr": 2.0, "cpc": 1.50, "cpm": 15.0},
    }

    report = generate_executive_report(context, cliente_id=cliente_id)
    if report is None:
        return JsonResponse({"error": "Não foi possível gerar o relatório. Verifique a chave ANTHROPIC_API_KEY."}, status=500)

    return JsonResponse({"report": report})


@login_required
def api_ai_status(request: HttpRequest) -> JsonResponse:
    """Check AI service status (force refresh by clearing cache)."""
    from django.core.cache import cache as _cache
    _cache.delete("ai:status")
    from web.services.ai_analytics import check_ai_status
    status = check_ai_status()
    return JsonResponse(status)


@login_required
@require_admin
def api_send_ai_email(request: HttpRequest) -> JsonResponse:
    """Send the latest AI insights to the current user's email."""
    from django.core.mail import send_mail as _send_mail
    from django.core.cache import cache as _cache
    from django.template.loader import render_to_string

    user = request.user
    if not user.email:
        return JsonResponse({"ok": False, "error": "Nenhum e-mail cadastrado no seu perfil."}, status=400)

    # Find cached AI insights for this client
    cliente_id = effective_cliente_id(request)
    if not cliente_id and is_admin(request.user):
        cliente_id = selected_cliente_id(request)

    if not cliente_id:
        return JsonResponse({"ok": False, "error": "Selecione um cliente primeiro."}, status=400)

    # Try to get from DB (most recent AIInsight)
    from accounts.models import AIInsight
    recent = AIInsight.objects.filter(
        cliente_id=cliente_id, insight_type="insight", dismissed=False
    ).order_by("-created_at")[:10]

    if not recent.exists():
        return JsonResponse({"ok": False, "error": "Nenhum insight gerado ainda. Acesse o Analytics primeiro."}, status=404)

    # Build email
    cliente_name = ""
    try:
        cliente_obj = Cliente.objects.get(id=cliente_id)
        cliente_name = cliente_obj.nome
    except Cliente.DoesNotExist:
        pass

    insights_list = []
    for ins in recent:
        insights_list.append({
            "title": ins.title,
            "text": ins.text,
            "type": ins.metadata.get("type", "info"),
        })

    # Get alerts and recommendations too
    alerts_recent = list(AIInsight.objects.filter(
        cliente_id=cliente_id, insight_type="alert", dismissed=False
    ).order_by("-created_at").values("title", "text", "severity")[:5])

    recs_recent = list(AIInsight.objects.filter(
        cliente_id=cliente_id, insight_type="recommendation", dismissed=False
    ).order_by("-created_at").values("title", "text", "metadata")[:5])

    # Plain text email
    lines = [f"Relatório de Insights — {cliente_name}", "=" * 50, ""]

    if insights_list:
        lines.append("INSIGHTS")
        lines.append("-" * 30)
        for i, ins in enumerate(insights_list, 1):
            emoji = {"positive": "+", "negative": "!", "warning": "~", "info": "i"}.get(ins["type"], "-")
            lines.append(f"  [{emoji}] {ins['title']}")
            lines.append(f"      {ins['text']}")
            lines.append("")

    if alerts_recent:
        lines.append("ALERTAS")
        lines.append("-" * 30)
        for a in alerts_recent:
            sev = (a.get("severity") or "info").upper()
            lines.append(f"  [{sev}] {a['title']}")
            lines.append(f"      {a['text']}")
            lines.append("")

    if recs_recent:
        lines.append("RECOMENDAÇÕES")
        lines.append("-" * 30)
        for r in recs_recent:
            lines.append(f"  > {r['title']}")
            lines.append(f"    {r['text']}")
            lines.append("")

    lines.extend(["", "—", "Oracli AI • Relatório gerado automaticamente", "DashMonitor • dashmonitor.com.br"])

    body = "\n".join(lines)
    subject = f"[Oracli AI] Insights — {cliente_name}"

    try:
        _send_mail(
            subject=subject,
            message=body,
            from_email=None,  # uses DEFAULT_FROM_EMAIL
            recipient_list=[user.email],
            fail_silently=False,
        )
    except Exception as e:
        return JsonResponse({"ok": False, "error": f"Erro ao enviar e-mail: {str(e)}"}, status=500)

    return JsonResponse({"ok": True, "email": user.email, "insights_count": len(insights_list)})


@login_required
@require_admin
def api_send_whatsapp(request: HttpRequest) -> JsonResponse:
    """Send the current AI report via WhatsApp to the selected client."""
    from django.db.models import Sum
    from web.services.whatsapp import send_whatsapp, build_report_message

    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "POST required"}, status=405)

    cliente_id = effective_cliente_id(request)
    if not cliente_id and is_admin(request.user):
        cliente_id = selected_cliente_id(request)
    if not cliente_id:
        return JsonResponse({"ok": False, "error": "Selecione um cliente"})

    from accounts.models import Cliente as _Cl
    cliente = _Cl.objects.filter(id=cliente_id).first()
    if not cliente:
        return JsonResponse({"ok": False, "error": "Cliente não encontrado"})
    if not cliente.whatsapp:
        return JsonResponse({"ok": False, "error": f"WhatsApp não configurado para {cliente.nome}. Edite o cliente e preencha o campo WhatsApp."})

    # Compute metrics
    line_ids = list(PlacementLine.objects.filter(campaign__cliente_id=cliente_id).values_list("id", flat=True))
    days_qs = PlacementDay.objects.filter(placement_line_id__in=line_ids)
    stats = days_qs.aggregate(total_imp=Sum("impressions"), total_clk=Sum("clicks"), total_cost=Sum("cost"))
    total_imp = stats["total_imp"] or 0
    total_clk = stats["total_clk"] or 0
    total_cost = float(stats["total_cost"] or 0)
    global_ctr = round((total_clk / total_imp * 100), 2) if total_imp > 0 else 0
    global_cpc = round((total_cost / total_clk), 2) if total_clk > 0 else 0
    cpm = round((total_cost / total_imp * 1000), 2) if total_imp > 0 else 0

    # Get AI summary from latest insights if available
    ai_summary = ""
    ai_rec = ""
    try:
        from accounts.models import AIInsight
        latest = AIInsight.objects.filter(cliente_id=cliente_id, insight_type="executive_summary").order_by("-created_at").first()
        if latest:
            ai_summary = latest.text
        latest_rec = AIInsight.objects.filter(cliente_id=cliente_id, insight_type="recommendation").order_by("-created_at").first()
        if latest_rec:
            ai_rec = latest_rec.text
    except Exception:
        pass

    msg = build_report_message(
        cliente_nome=cliente.nome,
        total_imp=total_imp, total_clk=total_clk,
        global_ctr=global_ctr, global_cpc=global_cpc,
        cpm=cpm, total_cost=total_cost,
        ai_summary=ai_summary, ai_recommendation=ai_rec,
    )

    result = send_whatsapp(cliente.whatsapp, msg)
    if result.get("ok"):
        return JsonResponse({"ok": True, "phone": cliente.whatsapp, "provider": result.get("provider", "")})
    return JsonResponse({"ok": False, "error": result.get("error", "Falha no envio")})


@login_required
@require_admin
def api_ai_webhook(request: HttpRequest) -> JsonResponse:
    """Return the latest AI insights as structured JSON for webhook/integration consumption."""
    cliente_id = effective_cliente_id(request)
    if not cliente_id and is_admin(request.user):
        cliente_id = selected_cliente_id(request)

    if not cliente_id:
        return JsonResponse({"ok": False, "error": "Selecione um cliente."}, status=400)

    from accounts.models import AIInsight
    insights = list(AIInsight.objects.filter(
        cliente_id=cliente_id, dismissed=False
    ).order_by("-created_at").values("insight_type", "title", "text", "severity", "metadata", "created_at")[:30])

    cliente_name = ""
    try:
        cliente_name = Cliente.objects.get(id=cliente_id).nome
    except Cliente.DoesNotExist:
        pass

    payload = {
        "ok": True,
        "source": "Oracli AI",
        "cliente": cliente_name,
        "cliente_id": cliente_id,
        "generated_at": insights[0]["created_at"].isoformat() if insights else None,
        "insights": [i for i in insights if i["insight_type"] == "insight"],
        "alerts": [i for i in insights if i["insight_type"] == "alert"],
        "recommendations": [i for i in insights if i["insight_type"] == "recommendation"],
        "total": len(insights),
    }
    return JsonResponse(payload)
