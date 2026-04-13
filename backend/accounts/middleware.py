"""
Lightweight middleware to capture the current request in thread-local storage.
Used by audit signals to associate model changes with the requesting user.
"""
import threading

_thread_locals = threading.local()


def get_current_request():
    """Get the current request from thread-local storage."""
    return getattr(_thread_locals, "request", None)


def get_current_user():
    """Get the current authenticated user from thread-local storage."""
    request = get_current_request()
    if request and hasattr(request, "user") and request.user.is_authenticated:
        return request.user
    return None


class CurrentRequestMiddleware:
    """Store the current request in thread-local for audit logging."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _thread_locals.request = request
        try:
            return self.get_response(request)
        finally:
            _thread_locals.request = None
