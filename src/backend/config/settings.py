"""Compass settings for email authentication and the first PostgreSQL ERD section."""
import os
from pathlib import Path
from secrets import token_urlsafe

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
REPOSITORY_ROOT = BASE_DIR.parent.parent
# BASE_DIR is src/backend; repository assets live two levels above it.
# Local development shares root .env with Compose; shell values take precedence.
load_dotenv(REPOSITORY_ROOT / ".env", override=False, interpolate=False)
DEBUG = os.environ.get("DJANGO_DEBUG", "true").lower() in {"true", "1"}
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured("DJANGO_SECRET_KEY is required when debug is disabled.")
    SECRET_KEY = token_urlsafe(50)  # Temporary local key, never a deployment secret.
# Hostnames this Django instance accepts; this does not configure network binding.
ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]").split(",")
    if host.strip()
]

# Django's built-in components plus our feature apps. Registration alone does
# not create tables or expose routes such as /admin/ or /accounts/login/.
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core.apps.CoreConfig",
    "accounts.apps.AccountsConfig",
]
# Middleware wraps requests in this order and responses in reverse order.
# Sessions must precede authentication so it can resolve a session's user.
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
# DIRS finds project-wide templates; APP_DIRS finds templates inside each app.
# Context processors make request, auth, and message objects available to them.
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# The first ERD section is now configured against the local Compose database.
# Credentials stay in the ignored .env or process environment, not in source.
if not os.environ.get("POSTGRES_PASSWORD"):
    raise ImproperlyConfigured("Set POSTGRES_PASSWORD in the root .env or environment.")
DATABASES = {"default": {
    "ENGINE": "django.db.backends.postgresql",
    "NAME": os.environ.get("POSTGRES_DB", "compass"),
    "USER": os.environ.get("POSTGRES_USER", "compass"),
    "PASSWORD": os.environ["POSTGRES_PASSWORD"],
    "HOST": os.environ.get("POSTGRES_HOST", "127.0.0.1"),
    "PORT": os.environ.get("POSTGRES_PORT", "5432"),
}}
AUTH_USER_MODEL = "accounts.Account"
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "accounts:profile"
LOGOUT_REDIRECT_URL = "accounts:login"
LOGIN_FAILURE_LIMIT = 10
LOGIN_FAILURE_WINDOW = 300
# Suitable for this single-process local demo. Use a shared cache for deployment.
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
# Default key type for future models; these ERD entities explicitly use UUIDs.
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
# Used by account password-validation flows, including demo account setup.
# Trusted setup commands invoke these before creating demo account passwords.
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": f"django.contrib.auth.password_validation.{validator}"}
    for validator in [
        "UserAttributeSimilarityValidator", "MinimumLengthValidator",
        "CommonPasswordValidator", "NumericPasswordValidator",
    ]
]
LANGUAGE_CODE = "en-us"
# Display/localization timezone; USE_TZ keeps Django datetimes timezone-aware.
TIME_ZONE = "America/Chicago"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
# collectstatic output is generated here; edit source assets rather than this dir.
STATIC_ROOT = REPOSITORY_ROOT / "staticfiles"
# Keep draft assets available alongside conventional app-owned static files.
STATICFILES_DIRS = [
    ("draft/css", REPOSITORY_ROOT / "frontend" / "css"),
    ("draft/js", REPOSITORY_ROOT / "frontend" / "js"),
]
# Non-debug session/CSRF cookies require HTTPS; deployment needs further configuration.
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"
# Development email prints to the console instead of sending real messages.
MAILERS = {"default": {"BACKEND": "django.core.mail.backends.console.EmailBackend"}}
