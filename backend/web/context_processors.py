from accounts.models import Alert, Cliente

from .authz import effective_cliente_id, effective_role, is_admin


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

    return {
        "nav_mode": nav_mode,
        "nav_cliente": nav_cliente,
        "impersonating_cliente": impersonating_cliente,
        "is_true_admin": is_true_admin,
        "alertas_nao_lidos": alertas_nao_lidos,
        "alertas_pendentes": alertas_pendentes,
        "sidebar_clientes": sidebar_clientes,
        "sidebar_selected_cliente_id": sidebar_selected_cliente_id,
    }
