# Como Rodar o DashMonitor Localmente

Guia completo para configurar e executar o projeto em ambiente de desenvolvimento.

---

## Pré-requisitos

Antes de começar, instale as ferramentas abaixo:

| Ferramenta | Versão mínima | Download |
|-----------|--------------|---------|
| Python | 3.11+ | https://python.org/downloads |
| Git | qualquer | https://git-scm.com |
| ffmpeg (inclui ffprobe) | qualquer | https://ffmpeg.org/download.html |
| Node.js *(opcional — só para editar o frontend Vue)* | 18+ | https://nodejs.org |

> **ffmpeg é obrigatório** para o upload de arquivos de vídeo (extrai duração e metadados).
> Sem ele, o upload de peças de vídeo vai falhar.

### Verificar instalações

```bash
python --version       # Python 3.11.x
git --version
ffprobe -version       # deve aparecer versão do ffmpeg
node --version         # opcional
```

---

## 1. Clonar o repositório

```bash
git clone <url-do-repositorio>
cd dashmonitor
```

---

## 2. Criar e ativar o ambiente virtual

```bash
# Criar o virtualenv dentro da pasta do projeto
python -m venv venv
```

**Ativar:**

```bash
# Windows (PowerShell)
venv\Scripts\Activate.ps1

# Windows (CMD)
venv\Scripts\activate.bat

# macOS / Linux
source venv/bin/activate
```

Você verá `(venv)` no início do terminal quando estiver ativo.

---

## 3. Instalar dependências Python

```bash
cd backend
pip install -r requirements.txt
```

> Se aparecer erro no `psycopg2-binary`: não se preocupe se for usar SQLite.
> O pacote ainda instala — o Django vai usar SQLite por padrão.

---

## 4. Configurar variáveis de ambiente

O arquivo `.env` fica dentro de `backend/`. Copie o exemplo:

```bash
# ainda dentro de backend/
cp .env.example .env
```

O `.env` padrão já vem configurado para **SQLite** (sem precisar de PostgreSQL local).
Para rodar com SQLite (recomendado para dev), basta **remover ou comentar** a linha `DJANGO_USE_POSTGRES=1`:

```env
# backend/.env — configuração mínima para desenvolvimento com SQLite

# Deixe comentado para usar SQLite (mais simples):
# DJANGO_USE_POSTGRES=1

# Preencha apenas se for usar integrações:
GOOGLE_ADS_CLIENT_ID=
GOOGLE_ADS_CLIENT_SECRET=
GOOGLE_ADS_DEVELOPER_TOKEN=
META_ADS_APP_ID=
META_ADS_APP_SECRET=
```

> As integrações com Google Ads e Meta Ads funcionam sem as chaves configuradas —
> você só não conseguirá fazer o fluxo OAuth e o sync. Tudo mais funciona normalmente.

---

## 5. Criar o banco de dados e aplicar migrations

```bash
# certifique-se de estar em backend/ com o venv ativo
python manage.py migrate
```

Você verá as migrations sendo aplicadas. Um arquivo `db.sqlite3` será criado em `backend/`.

---

## 6. Criar o superusuário (admin)

```bash
python manage.py createsuperuser
```

Informe username, e-mail (pode deixar em branco) e senha.

---

## 7. (Opcional) Carregar dados de exemplo

Se houver fixtures ou dados de demonstração:

```bash
python manage.py loaddata fixtures/demo.json
```

Se não houver fixtures, crie os dados manualmente após o login:
- Acesse `/administracao/clientes/` para criar clientes
- Acesse `/administracao/usuarios/` para criar usuários por cliente

---

## 8. Rodar o servidor de desenvolvimento

```bash
python manage.py runserver
```

Acesse no browser: **http://localhost:8000**

| URL | Descrição |
|-----|-----------|
| `http://localhost:8000/login/` | Login geral (admin/colaborador) |
| `http://localhost:8000/login/<slug>/` | Login personalizado por cliente |
| `http://localhost:8000/administracao/` | Painel administrativo |
| `http://localhost:8000/dashboard/` | Portal do cliente |

---

## 9. (Opcional) Usar PostgreSQL local

Se preferir PostgreSQL em vez de SQLite, instale o PostgreSQL 14+ e crie o banco:

```sql
-- no psql como superusuário:
CREATE DATABASE dashmonitor;
CREATE USER dashmonitor_app WITH PASSWORD 'dashmonitor';
GRANT ALL PRIVILEGES ON DATABASE dashmonitor TO dashmonitor_app;
```

Edite `backend/.env`:

```env
DJANGO_USE_POSTGRES=1
POSTGRES_DB=dashmonitor
POSTGRES_USER=dashmonitor_app
POSTGRES_PASSWORD=dashmonitor
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
```

Depois aplique as migrations:

```bash
python manage.py migrate
python manage.py createsuperuser
```

---

## 10. (Opcional) Frontend Vue — editar o `src/`

O frontend Vue (`src/`) é usado para componentes visuais e o `src/styles.css` global.
O Django já inclui o `src/` como `STATICFILES_DIRS`, então o CSS já carrega automaticamente
via `runserver`. Você só precisa rodar o Vite se quiser editar os componentes Vue com hot-reload:

```bash
# na raiz do projeto (onde está o package.json)
npm install
npm run dev
```

O Vite sobe em `http://localhost:5173` (frontend standalone).
Para o sistema Django completo, continue usando `http://localhost:8000`.

---

## Estrutura de pastas relevante

```
dashmonitor/
├── backend/                  ← raiz do Django
│   ├── manage.py
│   ├── .env                  ← suas variáveis locais (não versionar)
│   ├── .env.example          ← template de variáveis
│   ├── requirements.txt
│   ├── db.sqlite3            ← banco SQLite (gerado após migrate)
│   ├── media/                ← uploads dos usuários (gerado automaticamente)
│   ├── static/               ← CSS/JS estáticos do Django
│   ├── accounts/             ← app: usuários, clientes, auditoria
│   ├── campaigns/            ← app: campanhas, peças, veiculação
│   ├── integrations/         ← app: Google Ads e Meta Ads
│   ├── web/                  ← app: views, templates, URLs
│   └── dashmonitor_django/   ← configurações do projeto
├── src/                      ← componentes Vue + styles.css global
├── package.json              ← dependências Node (Vite + Vue)
└── venv/                     ← ambiente virtual Python (não versionar)
```

---

## Comandos úteis do dia a dia

```bash
# Rodar o servidor
python manage.py runserver

# Criar migration após alterar um model
python manage.py makemigrations
python manage.py migrate

# Abrir shell interativo do Django
python manage.py shell

# Sincronizar Google Ads manualmente (precisa de credenciais no .env)
python manage.py sync_google_ads --days=7

# Sincronizar Meta Ads manualmente
python manage.py sync_meta_ads --days=7

# Limpar banco e recriar do zero
rm backend/db.sqlite3
python manage.py migrate
python manage.py createsuperuser

# Ver todas as URLs registradas
python manage.py show_urls   # requer django-extensions, ou:
python manage.py shell -c "from django.urls import get_resolver; [print(p) for p in get_resolver().url_patterns]"
```

---

## Problemas comuns

### `ModuleNotFoundError: No module named 'xyz'`
O virtualenv não está ativo ou o `pip install` não rodou.
```bash
source venv/bin/activate   # ou venv\Scripts\activate no Windows
pip install -r backend/requirements.txt
```

### `django.db.utils.OperationalError: no such table`
Migrations não foram aplicadas.
```bash
python manage.py migrate
```

### Upload de vídeo falha com erro de ffprobe
O `ffmpeg` não está instalado ou não está no PATH.
- **Windows:** Baixe em https://ffmpeg.org/download.html, extraia e adicione a pasta `bin/` ao PATH do sistema.
- **macOS:** `brew install ffmpeg`
- **Linux:** `sudo apt install ffmpeg`

Teste: `ffprobe -version`

### Erro de permissão no PowerShell ao ativar venv
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Login redireciona em loop
Verifique se o superusuário foi criado com `python manage.py createsuperuser`.

### `CSRF verification failed` ao fazer login
O servidor foi reiniciado e a sessão antiga ficou inválida. Limpe os cookies do browser para `localhost:8000`.

### Porta 8000 já em uso
```bash
python manage.py runserver 8001
# ou matar o processo:
# Windows:  netstat -ano | findstr :8000  →  taskkill /PID <pid> /F
# Linux/Mac: lsof -ti:8000 | xargs kill
```

---

## Resumo rápido (após o primeiro setup)

```bash
cd dashmonitor/backend
source ../venv/bin/activate      # Windows: ..\venv\Scripts\activate
python manage.py runserver
# → http://localhost:8000
```

É isso.
