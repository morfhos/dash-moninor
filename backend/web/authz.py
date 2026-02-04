from __future__ import annotations

from typing import Callable, TypeVar

from django.contrib.auth.models import AbstractBaseUser
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect


def is_admin(user: AbstractBaseUser) -> bool:
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


T = TypeVar("T", bound=Callable[..., HttpResponse])


def require_admin(view: T) -> T:
    def _wrapped(request: HttpRequest, *args, **kwargs):
        if not is_admin(request.user) or request.session.get("impersonate_cliente_id"):
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
