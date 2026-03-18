# Arquitetura de Produção — DashMonitor

**Versão:** 1.0
**Data:** Março de 2026
**Público:** Time técnico responsável pelo deploy e operação

---

## Sumário

1. [Visão Geral da Stack](#1-visão-geral-da-stack)
2. [Diagrama de Arquitetura](#2-diagrama-de-arquitetura)
3. [Camada de Rede — Cloudflare + Nginx](#3-camada-de-rede--cloudflare--nginx)
4. [Aplicação — Gunicorn](#4-aplicação--gunicorn)
5. [Banco de Dados — PostgreSQL + PgBouncer](#5-banco-de-dados--postgresql--pgbouncer)
6. [Cache e Sessões — Redis](#6-cache-e-sessões--redis)
7. [Tarefas Assíncronas — Celery + Celery Beat](#7-tarefas-assíncronas--celery--celery-beat)
8. [Armazenamento de Arquivos — Media Files](#8-armazenamento-de-arquivos--media-files)
9. [E-mail Transacional](#9-e-mail-transacional)
10. [Segurança e Isolamento Multi-tenant](#10-segurança-e-isolamento-multi-tenant)
11. [Variáveis de Ambiente](#11-variáveis-de-ambiente)
12. [Deploy com Docker Compose](#12-deploy-com-docker-compose)
13. [Monitoramento e Observabilidade](#13-monitoramento-e-observabilidade)
14. [Backup e Recuperação](#14-backup-e-recuperação)
15. [Checklist de Go-Live](#15-checklist-de-go-live)

---

## 1. Visão Geral da Stack

| Camada | Tecnologia | Justificativa |
|--------|-----------|---------------|
| CDN / WAF | Cloudflare (free tier) | DDoS, SSL automático, cache de estáticos |
| Proxy reverso | Nginx 1.24+ | Serve `/static/` e `/media/` sem passar pelo Django |
| Aplicação | Gunicorn (sync workers) | Simples, estável, suficiente para Django síncrono |
| Framework | Django 4.2 + Python 3.11 | Stack atual do projeto |
| Banco primário | PostgreSQL 16 | ACID, suporte a JSON, índices compostos |
| Pool de conexões | PgBouncer 1.22 | Evita esgotar conexões com crescimento de tenants |
| Cache / Sessões | Redis 7 | Sessões persistentes entre restarts, cache de queryset |
| Filas / Tarefas | Celery 5 + Celery Beat | Sync Google/Meta Ads assíncrono, envio de e-mail |
| Broker de filas | Redis 7 (DB 1) | Mesmo Redis, banco separado |
| Object Storage | S3-compatible (Cloudflare R2 ou AWS S3) | Media files escalável, sem disco local |
| SSL | Let's Encrypt via Certbot | Certificado gratuito, renovação automática |

---

## 2. Diagrama de Arquitetura

```
                     ┌──────────────────────────────┐
  Usuário  ────────▶ │  Cloudflare                   │
  Browser            │  • CDN para /static/           │
                     │  • WAF / Rate Limiting         │
                     │  • SSL termination automático  │
                     └──────────────┬───────────────-┘
                                    │ HTTPS
                     ┌──────────────▼───────────────-┐
                     │  Nginx (porta 443/80)           │
                     │  • Serve /static/ diretamente  │
                     │  • Serve /media/ diretamente   │
                     │  • Proxy para Gunicorn          │
                     │  • gzip, headers de segurança  │
                     └──────┬────────────────────────-┘
                            │ HTTP (127.0.0.1:8000)
           ┌────────────────▼─────────────────────────┐
           │  Gunicorn  (4–8 workers sync)             │
           │  • preload_app = True                     │
           │  • max_requests = 1000 (evita memory leak)│
           └────────────────┬─────────────────────────┘
                            │
           ┌────────────────▼─────────────────────────┐
           │  Django 4.2 Application                   │
           │  • web, campaigns, accounts, integrations │
           └──────┬──────────────┬────────────────────-┘
                  │              │
     ┌────────────▼──┐  ┌────────▼──────────────────┐
     │  PgBouncer    │  │  Redis 7                   │
     │  porta 6432   │  │  DB 0 → cache/sessões      │
     └──────┬────────┘  │  DB 1 → Celery broker      │
            │           └────────────────────────────┘
     ┌──────▼────────┐
     │  PostgreSQL 16│
     │  (primário)   │
     └──────┬────────┘
            │  streaming replication
     ┌──────▼────────┐
     │  PostgreSQL   │  ← consultas de relatórios
     │  (réplica RO) │    e analytics (fase 2)
     └───────────────┘

  ┌─────────────────────────────────────────────────┐
  │  Celery Worker  (processo separado)              │
  │  • sync_google_ads  (a cada 1h)                  │
  │  • sync_meta_ads    (a cada 1h)                  │
  │  • envio de e-mails (imediato, async)            │
  └─────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────┐
  │  Celery Beat  (agendador, processo separado)     │
  │  • dispara as tarefas periódicas                 │
  └─────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────┐
  │  S3 / Cloudflare R2  (object storage)            │
  │  • campaigns/assets/   (peças criativas)         │
  │  • campaigns/contracts/ (contratos)              │
  │  • clientes/logos/      (logos de clientes)      │
  └─────────────────────────────────────────────────┘
```

---

## 3. Camada de Rede — Cloudflare + Nginx

### 3.1 Cloudflare

- Ative o proxy (laranja) para o registro A do domínio.
- SSL/TLS mode: **Full (strict)**.
- Ative **"Always Use HTTPS"**.
- Cache Rules: cache agressivo para `/static/*` (1 mês), bypass para tudo mais.
- Rate Limiting (plano gratuito): 10.000 req / 10 min por IP — suficiente para início.
- Adicione ao `ALLOWED_HOSTS` do Django apenas o domínio real (não `*`).
- Configure `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")` no Django
  para que `request.is_secure()` funcione atrás do Cloudflare.

### 3.2 Nginx

```nginx
# /etc/nginx/sites-available/dashmonitor
upstream gunicorn {
    server 127.0.0.1:8000;
    keepalive 32;
}

# Redireciona HTTP → HTTPS
server {
    listen 80;
    server_name app.seudominio.com.br;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name app.seudominio.com.br;

    # SSL — gerenciado pelo Certbot
    ssl_certificate     /etc/letsencrypt/live/app.seudominio.com.br/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/app.seudominio.com.br/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;
    ssl_session_cache   shared:SSL:10m;
    ssl_session_timeout 10m;

    # Headers de segurança
    add_header X-Frame-Options        "SAMEORIGIN"  always;
    add_header X-Content-Type-Options "nosniff"     always;
    add_header Referrer-Policy        "same-origin" always;

    # Logs
    access_log /var/log/nginx/dashmonitor_access.log;
    error_log  /var/log/nginx/dashmonitor_error.log;

    # Arquivos estáticos — servidos diretamente, sem tocar no Django
    location /static/ {
        alias /app/backend/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, immutable";
        gzip_static on;
    }

    # Arquivos de mídia (uploads dos usuários)
    location /media/ {
        alias /app/backend/media/;
        expires 7d;
        add_header Cache-Control "public";

        # Bloqueia execução de qualquer script dentro de /media/
        location ~* \.(php|py|pl|sh|rb|cgi)$ {
            deny all;
        }
    }

    # Aplicação Django
    location / {
        proxy_pass         http://gunicorn;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_redirect     off;
        proxy_buffering    on;
        proxy_buffer_size  8k;
        proxy_buffers      8 8k;

        client_max_body_size  100M;   # Uploads de planilhas e assets
        proxy_read_timeout    120s;
        proxy_connect_timeout 10s;
    }
}
```

> **Renovação SSL automática:**
> ```bash
> certbot --nginx -d app.seudominio.com.br
> # Certbot adiciona um cron/systemd timer automático
> ```

---

## 4. Aplicação — Gunicorn

### 4.1 Configuração

```python
# /app/gunicorn.conf.py
import multiprocessing

bind             = "127.0.0.1:8000"
workers          = multiprocessing.cpu_count() * 2 + 1  # ex: 4 vCPUs → 9 workers
worker_class     = "sync"          # Django é síncrono; sync é mais estável
threads          = 1
max_requests     = 1000            # recicla o worker após N requests (evita memory leak)
max_requests_jitter = 200          # jitter para evitar restart simultâneo de todos
timeout          = 60              # mata worker que travar por 60s
keepalive        = 5
preload_app      = True            # carrega Django 1x antes de forkar (economiza RAM)

accesslog  = "/var/log/gunicorn/dashmonitor_access.log"
errorlog   = "/var/log/gunicorn/dashmonitor_error.log"
loglevel   = "info"

# Graceful restart: workers novos iniciam antes de matar os velhos
graceful_timeout = 30
```

### 4.2 Systemd Service

```ini
# /etc/systemd/system/dashmonitor.service
[Unit]
Description=DashMonitor Gunicorn
After=network.target postgresql.service redis.service

[Service]
Type=notify
User=dashmonitor
Group=dashmonitor
WorkingDirectory=/app/backend
EnvironmentFile=/app/.env
ExecStart=/app/venv/bin/gunicorn dashmonitor_django.wsgi:application -c /app/gunicorn.conf.py
ExecReload=/bin/kill -s HUP $MAINPID
KillMode=mixed
TimeoutStopSec=5
PrivateTmp=true
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
systemctl enable dashmonitor
systemctl start dashmonitor

# Deploy sem downtime (reload graceful):
systemctl reload dashmonitor
```

---

## 5. Banco de Dados — PostgreSQL + PgBouncer

### 5.1 Por que PgBouncer é obrigatório

Cada worker do Gunicorn mantém uma conexão ao PostgreSQL. Com:
- 9 workers × N deploys = dezenas de conexões abertas permanentemente.
- Cada conexão do PostgreSQL consome ~5 MB de RAM no servidor.
- Sem pool, ao crescer para 50+ tenants ativos simultâneos, o banco esgota conexões.

PgBouncer atua como proxy: a aplicação abre 1.000 "conexões" ao PgBouncer, mas ele repassa apenas 20–30 conexões reais ao PostgreSQL.

### 5.2 Configuração do PgBouncer

```ini
# /etc/pgbouncer/pgbouncer.ini
[databases]
dashmonitor = host=127.0.0.1 port=5432 dbname=dashmonitor

[pgbouncer]
listen_addr         = 127.0.0.1
listen_port         = 6432
auth_type           = md5
auth_file           = /etc/pgbouncer/userlist.txt

pool_mode           = transaction   # OBRIGATÓRIO com Django (não usar session mode)
max_client_conn     = 500           # conexões que chegam da aplicação
default_pool_size   = 25            # conexões reais que abre no PostgreSQL
min_pool_size       = 5
reserve_pool_size   = 5
reserve_pool_timeout= 3

server_lifetime     = 3600          # recicla conexões a cada 1h
server_idle_timeout = 300
client_idle_timeout = 0

log_connections     = 0             # desliga em produção (verboso)
log_disconnections  = 0
stats_period        = 60
```

```txt
# /etc/pgbouncer/userlist.txt  (senha em md5 ou scram)
"dashmonitor_app" "md5<hash>"
```

### 5.3 Django settings para PgBouncer

```python
# settings.py — IMPORTANTE: CONN_MAX_AGE = 0 com transaction pool mode
DATABASES = {
    "default": {
        "ENGINE":   "django.db.backends.postgresql",
        "NAME":     os.environ.get("POSTGRES_DB", "dashmonitor"),
        "USER":     os.environ.get("POSTGRES_USER", "dashmonitor_app"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
        "HOST":     os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        "PORT":     os.environ.get("POSTGRES_PORT", "6432"),  # PgBouncer
        "CONN_MAX_AGE": 0,   # NÃO usar persistent connections com PgBouncer transaction mode
        "OPTIONS": {
            "connect_timeout": 5,
        },
    }
}
```

### 5.4 PostgreSQL — postgresql.conf (servidor 8 GB RAM)

```ini
# Memória
shared_buffers            = 2GB       # 25% da RAM
effective_cache_size      = 6GB       # estimativa do cache do SO
work_mem                  = 32MB      # por operação de sort/hash (cuidado: multiplica por conexões)
maintenance_work_mem      = 512MB     # para VACUUM, CREATE INDEX

# WAL e checkpoint
wal_level                 = replica   # habilita streaming replication
checkpoint_completion_target = 0.9
wal_buffers               = 64MB
max_wal_size              = 2GB
min_wal_size              = 512MB

# Replication (para réplica futura)
max_wal_senders           = 3
wal_keep_size             = 1GB
hot_standby               = on

# Conexões (o PgBouncer protege este limite)
max_connections           = 100

# Logging de queries lentas
log_min_duration_statement = 500    # loga queries acima de 500ms
log_checkpoints            = on
log_lock_waits             = on

# Autovacuum agressivo para tabelas de alto volume (PlacementDay, AuditLog)
autovacuum_vacuum_scale_factor  = 0.01   # vacuum com 1% de dead rows (padrão 20%)
autovacuum_analyze_scale_factor = 0.005
```

### 5.5 Índices implementados

Os índices abaixo foram adicionados via migration (`0006_perf_indexes`, `0008_perf_indexes`):

| Tabela | Índice | Query beneficiada |
|--------|--------|------------------|
| `campaigns_campaign` | `(cliente_id, status)` | Dashboard, lista de campanhas por cliente |
| `campaigns_campaign` | `(cliente_id, start_date, end_date)` | Timeline, runtime_state |
| `campaigns_placementline` | `(campaign_id, media_channel)` | Veiculação com filtro de canal |
| `campaigns_placementline` | `external_ref` | Sync Google/Meta (lookup por ID externo) |
| `campaigns_placementday` | `date` | Relatórios por período |
| `accounts_alert` | `(cliente_id, lido, -criado_em)` | Context processor (toda request) |
| `accounts_auditlog` | `(event_type, created_at)` | Logs de auditoria com filtro |
| `accounts_auditlog` | `(user_id, created_at)` | Logs por usuário |

> **Nota:** Django já cria índice automático para todos os campos `ForeignKey`.
> Os índices acima cobrem colunas *não-FK* usadas em filtros frequentes.

---

## 6. Cache e Sessões — Redis

### 6.1 Instalação e configuração

```bash
# Ubuntu/Debian
apt install redis-server

# redis.conf — ajustes mínimos de produção
maxmemory 512mb
maxmemory-policy allkeys-lru    # descarta chaves menos usadas quando cheio
save ""                         # desabilita persistência RDB (cache é volátil)
appendonly no
bind 127.0.0.1                  # apenas localhost
requirepass <senha-forte>
```

### 6.2 Django settings

```python
# requirements.txt — adicionar:
# django-redis>=5.4,<6.0

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": os.environ.get("REDIS_URL", "redis://:senha@127.0.0.1:6379/0"),
        "TIMEOUT": 300,
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "SOCKET_CONNECT_TIMEOUT": 5,
            "SOCKET_TIMEOUT": 5,
            "IGNORE_EXCEPTIONS": True,   # cache miss silencioso se Redis cair
        },
        "KEY_PREFIX": "dm",
    }
}

# Sessões no Redis (sobrevivem a restart do Gunicorn)
SESSION_ENGINE     = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "default"
SESSION_COOKIE_AGE  = 86400 * 7      # 7 dias
SESSION_COOKIE_SECURE   = True        # apenas HTTPS
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE      = True
```

### 6.3 O que cachear (exemplos práticos)

```python
from django.core.cache import cache

# Sidebar de clientes — consultada em TODA request autenticada
SIDEBAR_CLIENTES_KEY = "sidebar:clientes:all"

def get_clientes_sidebar():
    data = cache.get(SIDEBAR_CLIENTES_KEY)
    if data is None:
        data = list(
            Cliente.objects.filter(ativo=True)
            .order_by("nome")
            .values("id", "nome", "slug", "logo")
        )
        cache.set(SIDEBAR_CLIENTES_KEY, data, timeout=300)
    return data

# Invalida ao criar/editar/desativar um cliente:
def invalidar_cache_clientes():
    cache.delete(SIDEBAR_CLIENTES_KEY)
```

> **Regra geral:** Cachear dados que mudam raramente e são lidos com alta frequência.
> Não cachear dados financeiros ou de relatórios sem TTL muito curto (30–60s).

---

## 7. Tarefas Assíncronas — Celery + Celery Beat

### 7.1 Por que Celery

O sync com Google Ads e Meta Ads pode levar 30–60 segundos por conta. Se rodar dentro de uma requisição HTTP, o usuário fica bloqueado e o worker do Gunicorn fica preso. Com Celery, o sync roda em background sem impactar a UX.

### 7.2 Instalação

```
# requirements.txt — adicionar:
celery>=5.3,<6.0
django-celery-beat>=2.6,<3.0   # para agendamento via banco (opcional)
```

### 7.3 Configuração

```python
# backend/dashmonitor_django/celery.py
from celery import Celery
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dashmonitor_django.settings")

app = Celery("dashmonitor")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
```

```python
# backend/dashmonitor_django/__init__.py
from .celery import app as celery_app
__all__ = ("celery_app",)
```

```python
# settings.py
CELERY_BROKER_URL         = os.environ.get("REDIS_URL_CELERY", "redis://:senha@127.0.0.1:6379/1")
CELERY_RESULT_BACKEND     = os.environ.get("REDIS_URL_CELERY", "redis://:senha@127.0.0.1:6379/1")
CELERY_TASK_SERIALIZER    = "json"
CELERY_RESULT_SERIALIZER  = "json"
CELERY_ACCEPT_CONTENT     = ["json"]
CELERY_TIMEZONE           = "America/Sao_Paulo"
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT    = 300   # mata task após 5 min (evita travamento)

# Agendamento de tarefas periódicas
CELERY_BEAT_SCHEDULE = {
    "sync-google-ads": {
        "task":     "integrations.tasks.sync_all_google_ads",
        "schedule": 3600.0,   # a cada 1 hora
    },
    "sync-meta-ads": {
        "task":     "integrations.tasks.sync_all_meta_ads",
        "schedule": 3600.0,
    },
}
```

### 7.4 Tasks de sync

```python
# backend/integrations/tasks.py
from celery import shared_task
from integrations.models import GoogleAdsAccount, MetaAdsAccount
from integrations.services.google_ads import GoogleAdsService
from integrations.services.meta_ads import MetaAdsService


@shared_task(bind=True, max_retries=2, default_retry_delay=300)
def sync_all_google_ads(self):
    for account in GoogleAdsAccount.objects.filter(is_active=True):
        try:
            svc = GoogleAdsService(account)
            svc.full_sync(account, days=7)
        except Exception as exc:
            self.retry(exc=exc)


@shared_task(bind=True, max_retries=2, default_retry_delay=300)
def sync_all_meta_ads(self):
    for account in MetaAdsAccount.objects.filter(is_active=True):
        try:
            svc = MetaAdsService(account)
            svc.full_sync(account, days=7)
        except Exception as exc:
            self.retry(exc=exc)
```

### 7.5 Systemd Services

```ini
# /etc/systemd/system/dashmonitor-celery.service
[Unit]
Description=DashMonitor Celery Worker
After=network.target redis.service postgresql.service

[Service]
Type=forking
User=dashmonitor
Group=dashmonitor
WorkingDirectory=/app/backend
EnvironmentFile=/app/.env
ExecStart=/app/venv/bin/celery -A dashmonitor_django worker \
    --loglevel=info \
    --concurrency=2 \
    --logfile=/var/log/celery/worker.log \
    --pidfile=/var/run/celery/worker.pid \
    --detach
ExecStop=/app/venv/bin/celery multi stopwait worker \
    --pidfile=/var/run/celery/worker.pid
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```ini
# /etc/systemd/system/dashmonitor-celerybeat.service
[Unit]
Description=DashMonitor Celery Beat
After=network.target redis.service

[Service]
Type=simple
User=dashmonitor
Group=dashmonitor
WorkingDirectory=/app/backend
EnvironmentFile=/app/.env
ExecStart=/app/venv/bin/celery -A dashmonitor_django beat \
    --loglevel=info \
    --logfile=/var/log/celery/beat.log \
    --schedule=/var/run/celery/celerybeat-schedule
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

---

## 8. Armazenamento de Arquivos — Media Files

### 8.1 Problema com disco local

Arquivos salvos em `/media/` no disco da VM:
- Não sobrevivem a um redeploy se o container/VM for recriado.
- Não escalam horizontalmente (2 instâncias Django não compartilham disco).
- Não têm backup automático.

### 8.2 Solução: Cloudflare R2 (ou AWS S3)

Cloudflare R2 é S3-compatible e tem **zero custo de egress** (ao contrário do S3).

```
# requirements.txt — adicionar:
django-storages[s3]>=1.14,<2.0
boto3>=1.34,<2.0
```

```python
# settings.py
USE_S3 = os.environ.get("USE_S3", "false").lower() in {"1", "true", "yes"}

if USE_S3:
    DEFAULT_FILE_STORAGE  = "storages.backends.s3boto3.S3Boto3Storage"
    STATICFILES_STORAGE   = "storages.backends.s3boto3.S3StaticStorage"  # opcional

    AWS_ACCESS_KEY_ID      = os.environ.get("S3_ACCESS_KEY_ID", "")
    AWS_SECRET_ACCESS_KEY  = os.environ.get("S3_SECRET_ACCESS_KEY", "")
    AWS_STORAGE_BUCKET_NAME= os.environ.get("S3_BUCKET_NAME", "dashmonitor")
    AWS_S3_ENDPOINT_URL    = os.environ.get("S3_ENDPOINT_URL", "")  # R2: https://<id>.r2.cloudflarestorage.com
    AWS_S3_REGION_NAME     = os.environ.get("S3_REGION_NAME", "auto")
    AWS_S3_FILE_OVERWRITE  = False
    AWS_DEFAULT_ACL        = None
    AWS_QUERYSTRING_AUTH   = True   # URLs assinadas (arquivos privados)
    AWS_S3_SIGNATURE_VERSION = "s3v4"

    MEDIA_URL = f"{AWS_S3_ENDPOINT_URL}/{AWS_STORAGE_BUCKET_NAME}/"
```

---

## 9. E-mail Transacional

### 9.1 Provedor recomendado

Para envio confiável (recuperação de senha, alertas):

| Provedor | Free tier | Recomendação |
|----------|-----------|--------------|
| **Resend** | 3.000 emails/mês | Melhor DX, API moderna |
| **Mailgun** | 100 emails/dia | Clássico, confiável |
| **SendGrid** | 100 emails/dia | Popular, bom deliverability |
| **Amazon SES** | 62.000/mês (se EC2) | Barato em escala |

### 9.2 Configuração SMTP

```python
# settings.py — produção
EMAIL_BACKEND      = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST         = os.environ.get("EMAIL_HOST", "smtp.resend.com")
EMAIL_PORT         = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_USE_TLS      = True
EMAIL_HOST_USER    = os.environ.get("EMAIL_HOST_USER", "resend")
EMAIL_HOST_PASSWORD= os.environ.get("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "DashMonitor <noreply@seudominio.com.br>")
SERVER_EMAIL       = DEFAULT_FROM_EMAIL
```

> **IMPORTANTE:** Configure SPF, DKIM e DMARC no DNS do domínio remetente.
> Sem esses registros, os e-mails caem em spam.

---

## 10. Segurança e Isolamento Multi-tenant

### 10.1 Modelo de isolamento atual

O DashMonitor usa **Row-Level Isolation por aplicação**: todas as queries Django filtram
por `cliente_id` via `effective_cliente_id(request)`. Não usa PostgreSQL Row-Level Security (RLS)
— o isolamento é garantido pela camada de aplicação.

```
Usuário CLIENTE A  →  views.py filtra por cliente_id=A  →  vê apenas dados do A
Usuário CLIENTE B  →  views.py filtra por cliente_id=B  →  vê apenas dados do B
ADMIN              →  pode ver todos (com impersonação por sessão)
```

### 10.2 Checklist de isolamento

- [x] `effective_cliente_id()` centraliza a lógica — não duplicar nos views
- [x] `@require_admin` / `@require_true_admin` protegem rotas administrativas
- [x] Impersonação via `session["impersonate_cliente_id"]` — não altera role real
- [x] Tokens OAuth (Google/Meta) criptografados com `django.core.signing`
- [ ] **Pendente:** `api_piece_update` e `api_upload_piece_asset` precisam de verificação de cliente (ver seção 10.3)

### 10.3 Correções pendentes nos endpoints de API

Dois endpoints foram identificados sem verificação de isolamento de tenant:

```python
# web/views.py — api_piece_update: adicionar verificação
@login_required
def api_piece_update(request, piece_id):
    piece = get_object_or_404(Piece, id=piece_id)
    cliente_id = effective_cliente_id(request)
    # Verifica que a peça pertence ao cliente do usuário (ou admin)
    if not is_admin(request.user) and piece.campaign.cliente_id != cliente_id:
        return JsonResponse({"error": "Sem permissão"}, status=403)
    # ... resto da view

# web/views.py — api_upload_piece_asset: mesma verificação
@login_required
def api_upload_piece_asset(request, piece_id):
    piece = get_object_or_404(Piece, id=piece_id)
    cliente_id = effective_cliente_id(request)
    if not is_admin(request.user) and piece.campaign.cliente_id != cliente_id:
        return JsonResponse({"error": "Sem permissão"}, status=403)
    # ... resto da view
```

### 10.4 Django Security Settings (produção)

```python
# settings.py — adicionar em produção
DEBUG                     = False
ALLOWED_HOSTS             = [os.environ.get("ALLOWED_HOSTS", "app.seudominio.com.br")]

# HTTPS
SECURE_SSL_REDIRECT           = True
SECURE_HSTS_SECONDS           = 31536000   # 1 ano
SECURE_HSTS_INCLUDE_SUBDOMAINS= True
SECURE_HSTS_PRELOAD           = True
SECURE_PROXY_SSL_HEADER       = ("HTTP_X_FORWARDED_PROTO", "https")

# Cookies
SESSION_COOKIE_SECURE   = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE      = True
CSRF_COOKIE_HTTPONLY    = True
CSRF_TRUSTED_ORIGINS    = [f"https://{os.environ.get('ALLOWED_HOSTS', 'app.seudominio.com.br')}"]

# Clicks
X_FRAME_OPTIONS = "SAMEORIGIN"   # já configurado (necessário para preview HTML5)
```

---

## 11. Variáveis de Ambiente

Arquivo `/app/.env` no servidor (nunca versionar):

```env
# ── Aplicação ────────────────────────────────────────────────────────────────
DJANGO_SECRET_KEY=<string aleatória de 64+ chars — gere com: python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())">
DJANGO_DEBUG=false
ALLOWED_HOSTS=app.seudominio.com.br

# ── Banco de dados ───────────────────────────────────────────────────────────
DJANGO_USE_POSTGRES=true
POSTGRES_DB=dashmonitor
POSTGRES_USER=dashmonitor_app
POSTGRES_PASSWORD=<senha forte, nunca igual ao dev>
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=6432            # PgBouncer — NÃO mudar para 5432

# ── Redis ────────────────────────────────────────────────────────────────────
REDIS_URL=redis://:senha@127.0.0.1:6379/0
REDIS_URL_CELERY=redis://:senha@127.0.0.1:6379/1

# ── E-mail ───────────────────────────────────────────────────────────────────
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.resend.com
EMAIL_PORT=587
EMAIL_USE_TLS=true
EMAIL_HOST_USER=resend
EMAIL_HOST_PASSWORD=<api-key-do-provedor>
DEFAULT_FROM_EMAIL=DashMonitor <noreply@seudominio.com.br>

# ── Google Ads ───────────────────────────────────────────────────────────────
GOOGLE_ADS_CLIENT_ID=<id>.apps.googleusercontent.com
GOOGLE_ADS_CLIENT_SECRET=<secret>
GOOGLE_ADS_DEVELOPER_TOKEN=<token>
GOOGLE_ADS_REDIRECT_URI=https://app.seudominio.com.br/integracoes/google-ads/callback/

# ── Meta Ads ─────────────────────────────────────────────────────────────────
META_ADS_APP_ID=<app-id>
META_ADS_APP_SECRET=<secret>
META_ADS_REDIRECT_URI=https://app.seudominio.com.br/integracoes/meta-ads/callback/

# ── Object Storage (S3/R2) ───────────────────────────────────────────────────
USE_S3=true
S3_ACCESS_KEY_ID=<access-key>
S3_SECRET_ACCESS_KEY=<secret-key>
S3_BUCKET_NAME=dashmonitor-media
S3_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
S3_REGION_NAME=auto
```

---

## 12. Deploy com Docker Compose

### 12.1 Estrutura de arquivos

```
dashmonitor/
├── docker-compose.yml
├── docker-compose.override.yml   # overrides locais (gitignored)
├── Dockerfile
├── .env                          # gitignored
├── nginx/
│   └── dashmonitor.conf
└── backend/
    ├── gunicorn.conf.py
    └── ...
```

### 12.2 Dockerfile

```dockerfile
FROM python:3.11-slim

# Dependências de sistema (ffprobe para metadados de vídeo)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .

# Coleta estáticos no build
RUN python manage.py collectstatic --noinput

EXPOSE 8000
CMD ["gunicorn", "dashmonitor_django.wsgi:application", "-c", "gunicorn.conf.py"]
```

### 12.3 docker-compose.yml

```yaml
version: "3.9"

services:
  web:
    build: .
    restart: unless-stopped
    env_file: .env
    volumes:
      - media_files:/app/backend/media    # remover quando usar S3
    depends_on:
      - postgres
      - redis
      - pgbouncer
    expose:
      - "8000"

  celery_worker:
    build: .
    restart: unless-stopped
    env_file: .env
    command: celery -A dashmonitor_django worker --loglevel=info --concurrency=2
    depends_on:
      - postgres
      - redis

  celery_beat:
    build: .
    restart: unless-stopped
    env_file: .env
    command: celery -A dashmonitor_django beat --loglevel=info
    depends_on:
      - redis

  postgres:
    image: postgres:16-alpine
    restart: unless-stopped
    env_file: .env
    environment:
      POSTGRES_DB:       ${POSTGRES_DB}
      POSTGRES_USER:     ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./postgres/postgresql.conf:/etc/postgresql/postgresql.conf
    command: postgres -c config_file=/etc/postgresql/postgresql.conf

  pgbouncer:
    image: edoburu/pgbouncer:1.22
    restart: unless-stopped
    env_file: .env
    environment:
      DATABASE_URL: postgres://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}
      POOL_MODE:    transaction
      MAX_CLIENT_CONN: 500
      DEFAULT_POOL_SIZE: 25
    depends_on:
      - postgres

  redis:
    image: redis:7-alpine
    restart: unless-stopped
    command: >
      redis-server
      --maxmemory 512mb
      --maxmemory-policy allkeys-lru
      --requirepass ${REDIS_PASSWORD}
    volumes:
      - redis_data:/data

  nginx:
    image: nginx:1.24-alpine
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/dashmonitor.conf:/etc/nginx/conf.d/default.conf:ro
      - static_files:/app/staticfiles:ro
      - media_files:/app/media:ro
      - /etc/letsencrypt:/etc/letsencrypt:ro
    depends_on:
      - web

volumes:
  postgres_data:
  redis_data:
  media_files:
  static_files:
```

### 12.4 Comandos de deploy

```bash
# Primeiro deploy
docker compose up -d --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py collectstatic --noinput
docker compose exec web python manage.py createsuperuser

# Redeploy sem downtime
docker compose build web celery_worker celery_beat
docker compose up -d --no-deps web celery_worker celery_beat

# Verificar saúde
docker compose ps
docker compose logs web --tail=50
docker compose logs celery_worker --tail=50
```

---

## 13. Monitoramento e Observabilidade

### 13.1 Logs estruturados

```python
# settings.py
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{asctime} {levelname} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "file_error": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": "/var/log/dashmonitor/error.log",
            "maxBytes": 10 * 1024 * 1024,  # 10 MB
            "backupCount": 5,
            "formatter": "verbose",
        },
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django": {"handlers": ["console", "file_error"], "level": "WARNING", "propagate": False},
        "django.request": {"handlers": ["file_error"], "level": "ERROR", "propagate": False},
        "integrations": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}
```

### 13.2 Health check endpoint

```python
# web/views.py — adicionar
def health_check(request):
    """Endpoint para balanceadores e uptime monitors."""
    from django.db import connection
    try:
        connection.ensure_connection()
        db_ok = True
    except Exception:
        db_ok = False
    status = 200 if db_ok else 503
    return JsonResponse({"status": "ok" if db_ok else "degraded", "db": db_ok}, status=status)

# urls.py
path("health/", views.health_check, name="health_check"),
```

### 13.3 Uptime e alertas (ferramentas gratuitas)

| Ferramenta | Uso | Free tier |
|-----------|-----|-----------|
| **UptimeRobot** | Ping `/health/` a cada 5 min, alerta por e-mail | 50 monitores |
| **Sentry** | Captura exceções Python em produção | 5.000 erros/mês |
| **Grafana Cloud** | Dashboards de métricas | 50 GB logs/mês |
| **pganalyze** | Análise de queries PostgreSQL lentas | 1 banco grátis |

#### Sentry (recomendado como primeiro passo)

```
# requirements.txt
sentry-sdk[django]>=1.40,<2.0
```

```python
# settings.py
import sentry_sdk
if not DEBUG:
    sentry_sdk.init(
        dsn=os.environ.get("SENTRY_DSN", ""),
        traces_sample_rate=0.1,   # captura 10% das transações para performance
        send_default_pii=False,   # não envia dados pessoais
    )
```

---

## 14. Backup e Recuperação

### 14.1 Backup do banco de dados

```bash
#!/bin/bash
# /etc/cron.d/dashmonitor-backup — roda às 3h da manhã
0 3 * * * dashmonitor /app/scripts/backup_db.sh >> /var/log/dashmonitor/backup.log 2>&1
```

```bash
#!/bin/bash
# /app/scripts/backup_db.sh
set -e
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backups/postgres"
BACKUP_FILE="$BACKUP_DIR/dashmonitor_$DATE.sql.gz"

mkdir -p "$BACKUP_DIR"

# Dump comprimido
PGPASSWORD="$POSTGRES_PASSWORD" pg_dump \
    -h 127.0.0.1 -p 5432 \
    -U "$POSTGRES_USER" "$POSTGRES_DB" \
    | gzip > "$BACKUP_FILE"

# Mantém últimos 30 dias
find "$BACKUP_DIR" -name "*.sql.gz" -mtime +30 -delete

# Upload para S3/R2 (opcional mas recomendado)
# aws s3 cp "$BACKUP_FILE" "s3://$S3_BUCKET_NAME/backups/"

echo "Backup criado: $BACKUP_FILE ($(du -sh $BACKUP_FILE | cut -f1))"
```

### 14.2 Restore

```bash
# Restore completo
gunzip -c /backups/postgres/dashmonitor_20260301_030000.sql.gz \
    | PGPASSWORD="$POSTGRES_PASSWORD" psql -h 127.0.0.1 -U "$POSTGRES_USER" "$POSTGRES_DB"
```

### 14.3 Backup de media files

Se usar S3/R2: o próprio object storage é durável (replicação automática 3×).

Se usar disco local:
```bash
# Sincroniza /media/ para bucket S3 diariamente
0 4 * * * dashmonitor aws s3 sync /app/backend/media/ s3://dashmonitor-media/media/ --delete
```

---

## 15. Checklist de Go-Live

### Infraestrutura
- [ ] Domínio apontando para o servidor (A record)
- [ ] Cloudflare ativo com proxy + SSL Full Strict
- [ ] Certificado SSL gerado via Certbot
- [ ] Nginx configurado e testado (`nginx -t`)
- [ ] PgBouncer rodando e conectando ao PostgreSQL
- [ ] Redis rodando com senha e bind em 127.0.0.1

### Aplicação
- [ ] `DEBUG=False` em produção
- [ ] `ALLOWED_HOSTS` contém apenas o domínio real
- [ ] `SECRET_KEY` única e segura (nunca a chave de desenvolvimento)
- [ ] Todas as migrations aplicadas (`python manage.py migrate`)
- [ ] Estáticos coletados (`python manage.py collectstatic`)
- [ ] Gunicorn rodando via systemd com restart automático
- [ ] Celery worker + beat rodando via systemd
- [ ] Health check `/health/` retornando 200

### Segurança
- [ ] `SESSION_COOKIE_SECURE=True` e `CSRF_COOKIE_SECURE=True`
- [ ] `SECURE_SSL_REDIRECT=True`
- [ ] `SECURE_HSTS_SECONDS` configurado
- [ ] `api_piece_update` e `api_upload_piece_asset` com verificação de tenant
- [ ] Tokens OAuth salvos criptografados (já implementado)
- [ ] Arquivo `.env` com permissão `chmod 600`
- [ ] Usuário do banco sem permissão de superuser (`GRANT` apenas nas tabelas necessárias)

### Dados e E-mail
- [ ] Superusuário criado (`createsuperuser`)
- [ ] E-mail transacional testado (recuperação de senha funcionando)
- [ ] SPF, DKIM e DMARC configurados no DNS do domínio remetente
- [ ] Backup automático do banco configurado e testado

### Monitoramento
- [ ] UptimeRobot monitorando `/health/`
- [ ] Sentry configurado com DSN de produção
- [ ] Logs do Gunicorn e Nginx com rotação configurada (`logrotate`)

---

*Documento mantido pelo time técnico do DashMonitor.*
*Atualizar sempre que houver mudanças de infraestrutura.*
