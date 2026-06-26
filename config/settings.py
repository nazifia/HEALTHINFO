import os
from datetime import timedelta
from pathlib import Path

from celery.schedules import crontab
from corsheaders.defaults import default_headers as default_cors_headers
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("SECRET_KEY", "dev-insecure-change-me-0123456789-abcdef")
DEBUG = os.getenv("DEBUG", "1") == "1"
BASE_DOMAIN = os.getenv("BASE_DOMAIN", "health.local")

# Dev: wildcard. Prod (DEBUG=0): require explicit ALLOWED_HOSTS, no wildcard fallback.
_hosts_default = "*" if DEBUG else ""
ALLOWED_HOSTS = [h.strip() for h in os.getenv("ALLOWED_HOSTS", _hosts_default).split(",") if h.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "django_filters",
    "drf_spectacular",
    "rest_framework_simplejwt.token_blacklist",
    "apps.tenants",
    "apps.accounts",
    "apps.catalog",
    "apps.governance",
    "apps.ai",
    "apps.analytics",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "config.cors.ModeAwareCorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Resolves request.tenant from header/subdomain and binds it for the request.
    "apps.tenants.middleware.TenantMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

# CORS: dev-open vs prod-locked is toggled at runtime by ModeAwareCorsMiddleware
# (admin: Governance -> Runtime config), not the startup DEBUG flag. Dev reflects
# any Origin; prod allows only this explicit list (comma-separated env).
CORS_ALLOWED_ORIGINS = [
    o.strip() for o in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",") if o.strip()
]
# Custom tenant header the mobile/web client sends.
CORS_ALLOW_HEADERS = list(default_cors_headers) + ["x-tenant-id"]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]

# Dev defaults to sqlite. Set DB_HOST to use a server DB.
# DB_ENGINE selects the backend: "postgresql" (default) or "mysql".
# Note: pgvector (semantic search / RAG) requires postgresql.
if os.getenv("DB_HOST"):
    _engine = os.getenv("DB_ENGINE", "postgresql")
    _default_port = "3306" if _engine == "mysql" else "5432"
    DATABASES = {
        "default": {
            "ENGINE": f"django.db.backends.{_engine}",
            "NAME": os.getenv("DB_NAME", "health"),
            "USER": os.getenv("DB_USER", "health"),
            "PASSWORD": os.getenv("DB_PASSWORD", "health"),
            "HOST": os.getenv("DB_HOST"),
            "PORT": os.getenv("DB_PORT", _default_port),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
    # Don't let DRF hijack ?format= for renderer negotiation — views read it
    # themselves to switch JSON/CSV (otherwise ?format=csv 404s, no csv renderer).
    "URL_FORMAT_OVERRIDE": None,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "config.responses.envelope_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.ScopedRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {"search": "60/min"},
}

SIMPLE_JWT = {"ACCESS_TOKEN_LIFETIME": timedelta(minutes=60)}

# --- AI / RAG -------------------------------------------------------------
# Embedding dimension is fixed at migration time. 1536 = OpenAI
# text-embedding-3-small. The "fake" provider pads/truncates to match, so the
# stack runs with no API key in dev/tests.
EMBED_DIM = 1536
AI_EMBED_PROVIDER = os.getenv("AI_EMBED_PROVIDER", "fake")  # fake | openai
AI_EMBED_MODEL = os.getenv("AI_EMBED_MODEL", "text-embedding-3-small")
# Claude model for RAG synthesis; without ANTHROPIC_API_KEY we return
# retrieval-only results (still useful, no fabrication).
AI_GEN_MODEL = os.getenv("AI_GEN_MODEL", "claude-haiku-4-5-20251001")

# --- Celery ---------------------------------------------------------------
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", CELERY_BROKER_URL)
# In dev (DEBUG) run tasks inline so no Redis broker is needed; override per-env.
CELERY_TASK_ALWAYS_EAGER = os.getenv("CELERY_TASK_ALWAYS_EAGER", "1" if DEBUG else "0") == "1"
CELERY_TASK_EAGER_PROPAGATES = True
# Fire-and-forget tracking must never block a request. When the broker is down,
# .delay() should raise fast (caught by analytics' best-effort guard), not retry
# the connection 20x and hang the view for ~minutes.
CELERY_BROKER_TRANSPORT_OPTIONS = {"socket_connect_timeout": 1, "socket_timeout": 1}
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = False
CELERY_TASK_PUBLISH_RETRY = False
CELERY_BROKER_CONNECTION_RETRY = False
CELERY_BROKER_CONNECTION_MAX_RETRIES = 0
CELERY_RESULT_BACKEND_ALWAYS_RETRY = False  # don't retry a dead result backend 20x
CELERY_BEAT_SCHEDULE = {
    "nightly-reindex": {
        "task": "apps.ai.tasks.reindex_all",
        "schedule": crontab(hour=3, minute=0),
    },
    "weekly-tenant-report": {
        "task": "apps.analytics.tasks.weekly_tenant_report",
        "schedule": crontab(hour=4, minute=0, day_of_week="mon"),
    },
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Health Knowledge Platform API",
    "VERSION": "0.1.0",
    "DISCLAIMER": "Educational information only, not medical advice.",
}
