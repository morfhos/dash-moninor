from __future__ import annotations

from typing import Callable, TypeVar

from django.contrib.auth.models import AbstractBaseUser
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect


def is_admin(user: AbstractBaseUser) -> bool:
    """Verifica se o usuário é admin ou colaborador (acesso ao painel administrativo)."""
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    role = getattr(user, "role", "")
    return role in ("admin", "colaborador")


def is_true_admin(user: AbstractBaseUser) -> bool:
    """Retorna True apenas para superuser ou role == 'admin'."""
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return getattr(user, "role", "") == "admin"


def is_cliente(user: AbstractBaseUser) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    return getattr(user, "role", "") == "cliente"


def effective_role(request: HttpRequest) -> str:
    if not request.user.is_authenticated:
        return ""
    if is_admin(request.user):
        return "cliente" if request.session.get("impersonate_cliente_id") else "admin"
    return "cliente"


def effective_cliente_id(request: HttpRequest) -> int | None:
    if not request.user.is_authenticated:
        return None
    if is_admin(request.user):
        return request.session.get("impersonate_cliente_id")
    return getattr(request.user, "cliente_id", None)


def selected_cliente_id(request: HttpRequest) -> int | None:
    """Returns the admin's globally-selected client ID from the sidebar dropdown.

    Unlike effective_cliente_id(), this does NOT change effective_role() to 'cliente'.
    Returns None if no client is selected, user is not admin, or already impersonating.
    """
    if not request.user.is_authenticated:
        return None
    if not is_admin(request.user):
        return None
    if request.session.get("impersonate_cliente_id"):
        return None
    return request.session.get("selected_cliente_id")


T = TypeVar("T", bound=Callable[..., HttpResponse])


def require_admin(view: T) -> T:
    def _wrapped(request: HttpRequest, *args, **kwargs):
        if not is_admin(request.user) or request.session.get("impersonate_cliente_id"):
            return redirect("web:dashboard")
        return view(request, *args, **kwargs)

    return _wrapped  # type: ignore[return-value]


def require_true_admin(view: T) -> T:
    """Permite acesso apenas para admin real (exclui colaboradores)."""
    def _wrapped(request: HttpRequest, *args, **kwargs):
        if not is_true_admin(request.user) or request.session.get("impersonate_cliente_id"):
            return redirect("web:dashboard")
        return view(request, *args, **kwargs)

    return _wrapped  # type: ignore[return-value]


def require_cliente_view(view: T) -> T:
    def _wrapped(request: HttpRequest, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("web:login")
        if effective_role(request) != "cliente" or not effective_cliente_id(request):
            return redirect("web:clientes")
        return view(request, *args, **kwargs)

    return _wrapped  # type: ignore[return-value]
