import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BASE_DIR.parent

def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


_load_dotenv(BASE_DIR / ".env")
_load_dotenv(BASE_DIR / ".env.example")

SECRET_KEY = "dev-secret-key"
DEBUG = True
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "accounts",
    "campaigns",
    "integrations",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "web",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# Permite iframes do mesmo domínio (necessário para preview de peças HTML5)
X_FRAME_OPTIONS = "SAMEORIGIN"

ROOT_URLCONF = "dashmonitor_django.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "web.context_processors.nav_context",
            ],
        },
    }
]

WSGI_APPLICATION = "dashmonitor_django.wsgi.application"
ASGI_APPLICATION = "dashmonitor_django.asgi.application"

USE_POSTGRES = os.environ.get("DJANGO_USE_POSTGRES", "").lower() in {"1", "true", "yes"}
if USE_POSTGRES:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("POSTGRES_DB", "dashmonitor"),
            "USER": os.environ.get("POSTGRES_USER", "dashmonitor"),
            "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "dashmonitor"),
            "HOST": os.environ.get("POSTGRES_HOST", "127.0.0.1"),
            "PORT": os.environ.get("POSTGRES_PORT", "5432"),
            "CONN_MAX_AGE": 60,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [
    BASE_DIR / "static",
    REPO_DIR / "src",
]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/administracao/"
LOGOUT_REDIRECT_URL = "/login/"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# --- Google Ads Integration ---
GOOGLE_ADS_CLIENT_ID = os.environ.get("GOOGLE_ADS_CLIENT_ID", "")
GOOGLE_ADS_CLIENT_SECRET = os.environ.get("GOOGLE_ADS_CLIENT_SECRET", "")
GOOGLE_ADS_DEVELOPER_TOKEN = os.environ.get("GOOGLE_ADS_DEVELOPER_TOKEN", "")
GOOGLE_ADS_REDIRECT_URI = os.environ.get(
    "GOOGLE_ADS_REDIRECT_URI",
    "http://localhost:8000/integracoes/google-ads/callback/",
)

# --- Meta Ads Integration ---
META_ADS_APP_ID = os.environ.get("META_ADS_APP_ID", "")
META_ADS_APP_SECRET = os.environ.get("META_ADS_APP_SECRET", "")
META_ADS_REDIRECT_URI = os.environ.get(
    "META_ADS_REDIRECT_URI",
    "http://localhost:8000/integracoes/meta-ads/callback/",
)

# --- E-mail ---
# Em produção, configure as variáveis abaixo para usar SMTP.
# Em desenvolvimento, os e-mails são exibidos no console.
EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend",
)
EMAIL_HOST = os.environ.get("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "true").lower() in {"1", "true", "yes"}
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "DashMonitor <noreply@dashmonitor.com.br>")

# Token de recuperação de senha expira em 24 horas
PASSWORD_RESET_TIMEOUT = 86400
