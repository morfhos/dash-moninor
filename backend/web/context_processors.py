from accounts.models import Cliente

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

    return {
        "nav_mode": nav_mode,
        "nav_cliente": nav_cliente,
        "impersonating_cliente": impersonating_cliente,
        "is_true_admin": is_true_admin,
    }
