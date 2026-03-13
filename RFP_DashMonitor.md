# RFP — DashMonitor: Plataforma de Gestão de Campanhas e Mídia

**Documento:** Requisição de Proposta (RFP)
**Versão:** 1.0
**Data:** Março de 2026
**Confidencialidade:** Restrito

---

## Sumário

1. [Visão Geral](#1-visão-geral)
2. [Contexto e Problema de Negócio](#2-contexto-e-problema-de-negócio)
3. [Escopo do Sistema Atual](#3-escopo-do-sistema-atual)
4. [Arquitetura Técnica](#4-arquitetura-técnica)
5. [Módulos Funcionais Detalhados](#5-módulos-funcionais-detalhados)
6. [Integrações Externas](#6-integrações-externas)
7. [Segurança e Controle de Acesso](#7-segurança-e-controle-de-acesso)
8. [Infraestrutura e Implantação](#8-infraestrutura-e-implantação)
9. [Requisitos Não-Funcionais](#9-requisitos-não-funcionais)
10. [Entregáveis Esperados](#10-entregáveis-esperados)
11. [Critérios de Avaliação](#11-critérios-de-avaliação)
12. [Glossário](#12-glossário)

---

## 1. Visão Geral

O **DashMonitor** é uma plataforma web multi-tenant de gestão de campanhas publicitárias e monitoramento de mídia. A plataforma centraliza o planejamento, a execução e a análise de campanhas de mídia para agências e seus clientes, integrando canais digitais (Google Ads, Meta Ads) e tradicionais (TV, Rádio, OOH, Jornal).

O sistema é voltado para agências de publicidade que precisam gerenciar múltiplos clientes, planos de mídia, peças criativas e relatórios de desempenho em um único ambiente centralizado.

**Público-alvo:**
- **Administradores / Colaboradores da Agência** — gerenciam clientes, campanhas, planos de mídia, integrações e usuários.
- **Clientes das Agências** — acessam dashboards, relatórios, veiculação e alertas de suas próprias campanhas.

---

## 2. Contexto e Problema de Negócio

As agências de publicidade historicamente operam com ferramentas fragmentadas: planilhas Excel para planos de mídia, e-mails para aprovação de peças, múltiplos painéis de plataformas de anúncio (Google, Meta), e relatórios manuais para clientes. Esse fluxo gera retrabalho, falta de rastreabilidade e dificulta a transparência com o cliente.

O DashMonitor resolve esses problemas ao:

- **Centralizar** o plano de mídia, as peças criativas, os contratos e os relatórios em um único sistema.
- **Importar automaticamente** planos de mídia via planilhas XLSX.
- **Sincronizar métricas** diretamente das plataformas digitais (Google Ads e Meta Ads) sem intervenção manual.
- **Oferecer ao cliente** um portal exclusivo com visão de suas campanhas, veiculações e indicadores em tempo real.
- **Registrar auditoria completa** de todas as ações do sistema para rastreabilidade e conformidade.

---

## 3. Escopo do Sistema Atual

### 3.1 Visão Funcional de Alto Nível

| Módulo | Descrição |
|--------|-----------|
| Gestão de Clientes | Cadastro, configuração e isolamento multi-tenant de clientes |
| Gestão de Campanhas | Criação, edição, controle de status e segmentação de campanhas |
| Plano de Mídia | Importação via XLSX, linhas de veiculação por canal e canal |
| Peças Criativas | Upload e gerenciamento de arquivos (vídeo, imagem, áudio, HTML5) |
| Veiculação | Registro diário de inserções, custos e métricas por praça |
| Integrações Digitais | Google Ads (OAuth + sync) e Meta Ads (OAuth + sync) |
| Relatórios e Analytics | Dashboards consolidados, gráficos, filtros avançados |
| Alertas | Sistema de notificações da agência para os clientes |
| Auditoria | Log completo de eventos do sistema |
| Gestão de Usuários | Perfis, permissões e controle de acesso por cliente |
| Contratos | Upload e gestão de contratos por campanha |
| Timeline | Visualização temporal das campanhas |

---

## 4. Arquitetura Técnica

### 4.1 Stack Tecnológica

| Camada | Tecnologia |
|--------|-----------|
| Backend | Python 3.8+, Django 4.2 |
| Banco de dados | SQLite (desenvolvimento), PostgreSQL (produção) |
| Frontend | HTML5, CSS3, Vanilla JavaScript, Chart.js |
| Autenticação | Django Auth com modelo de usuário customizado |
| APIs Externas | Google Ads REST API v23, Meta Graph API v22.0 |
| Processamento de Arquivos | openpyxl (XLSX), ffprobe (metadados de vídeo) |
| Segurança de Tokens | `django.core.signing` (criptografia simétrica) |
| Servidor | Qualquer servidor WSGI/ASGI compatível (Gunicorn, uWSGI) |

### 4.2 Estrutura de Aplicações Django

```
backend/
├── dashmonitor_django/       # Configurações do projeto (settings, urls, wsgi)
├── accounts/                 # Usuários, clientes, auditoria, alertas
├── campaigns/                # Campanhas, peças, linhas de veiculação, métricas
├── integrations/             # Google Ads e Meta Ads (modelos, serviços, comandos)
├── web/                      # Views, formulários, templates, roteamento URL
├── static/                   # CSS, JS, imagens estáticas
├── media/                    # Arquivos carregados (peças, contratos, logos)
└── templates/web/            # 41 templates HTML
```

### 4.3 Fluxo de Dados

```
[Planilha XLSX] ──▶ import_media_plan_xlsx ──▶ PlacementLine + PlacementDay
[Google Ads API] ──▶ sync_google_ads ──────────▶ PlacementLine + PlacementDay
[Meta Ads API] ───▶ sync_meta_ads ─────────────▶ PlacementLine + PlacementDay
[Upload de Arquivo] ▶ CreativeAsset ────────────▶ ffprobe ──▶ Piece.duration
```

---

## 5. Módulos Funcionais Detalhados

### 5.1 Módulo de Gestão de Clientes

**Objetivo:** Gerenciar os clientes da agência e garantir isolamento completo de dados (multi-tenant).

**Funcionalidades:**
- Cadastro de clientes com nome, CNPJ, slug único e logotipo.
- Ativação/desativação de clientes.
- Página de detalhe com resumo de campanhas, usuários e status de integração.
- Login personalizado por cliente: cada cliente pode ter uma URL de login com sua própria identidade visual (`/login/<slug>/`).
- Seletor de cliente no painel administrativo (sidebar dropdown) para navegar entre clientes sem sair do sistema.

**Modelos de dados:**
- `Cliente` — nome, slug, CNPJ, ativo, logo, timestamps

---

### 5.2 Módulo de Gestão de Campanhas

**Objetivo:** Centralizar o ciclo de vida das campanhas publicitárias.

**Funcionalidades:**
- Criação de campanhas com nome, datas, timezone, tipo de mídia (online/offline) e orçamento total.
- Controle de status: `RASCUNHO → ATIVA → PAUSADA → FINALIZADA → ARQUIVADA`.
- Cálculo automático de estado em tempo real (`LIVE_NOW`, `SCHEDULED`, `ENDED`) com base na data/hora atual e no timezone configurado.
- Alocação percentual de orçamento por região com cores customizáveis.
- Vinculação automática com peças criativas e linhas de veiculação.
- Exclusão com confirmação e log de auditoria.
- Visualização agrupada por cliente.

**Modelos de dados:**
- `Campaign` — cliente, nome, datas, timezone, orçamento, status, tipo de mídia, criado_por
- `RegionInvestment` — campanha, região, percentual, ordem, cor

**Controle de Status (runtime_state):**
```
se now < start_date  → SCHEDULED
se start_date ≤ now ≤ end_date → LIVE_NOW
se now > end_date    → ENDED
```

---

### 5.3 Módulo de Plano de Mídia

**Objetivo:** Estruturar as linhas de veiculação e os registros diários de inserção/custo.

**Funcionalidades:**
- Importação de plano de mídia via planilha XLSX com detecção automática do tipo de mídia.
- Substituição ou acumulação de dados existentes (`replace_existing`).
- Cadastro manual de linhas de veiculação por canal de mídia.
- Registro diário de inserções, custo, impressões e cliques por linha.
- Suporte a 12 canais de mídia:

| Canal | Tipo |
|-------|------|
| TV Aberta | Offline |
| TV Paga (Pay TV) | Offline |
| Rádio | Offline |
| OOH (Out of Home) | Offline |
| Jornal | Offline |
| META (Facebook/Instagram) | Online |
| Google (Search/Display) | Online |
| YouTube | Online |
| Display | Online |
| Search | Online |
| Social | Online |
| Outros | Online/Offline |

**Modelos de dados:**
- `PlacementLine` — campanha, tipo, canal, mercado, emissora, programa, formato, duração, external_ref, datas
- `PlacementDay` — linha, data, inserções, custo, impressões, cliques

---

### 5.4 Módulo de Peças Criativas

**Objetivo:** Gerenciar os arquivos criativos das campanhas e vinculá-los às veiculações.

**Funcionalidades:**
- Upload de arquivos critativos (vídeo, imagem, áudio, HTML5).
- Extração automática de metadados via `ffprobe` (duração, codec, resolução).
- Cálculo de checksum SHA-256 para deduplicação de arquivos.
- Detecção automática do tipo de peça pelo nome do arquivo.
- Aprovação e arquivamento de peças (`PENDENTE → APROVADA → ARQUIVADA`).
- Matriz de vinculação (peça × linha de veiculação) com peso opcional para rotação.
- Preview de peças HTML5 via iframe e visualização de imagens/vídeos.
- Metadados armazenados: nome original, tipo MIME, tamanho em bytes, duração.

**Modelos de dados:**
- `Piece` — campanha, código, título, duração, tipo, status, notas
- `CreativeAsset` — peça, arquivo, preview_url, thumb_url, checksum, metadata (JSON)
- `PlacementCreative` — linha_veiculação, peça, peso

---

### 5.5 Módulo de Veiculação

**Objetivo:** Exibir ao cliente e à agência os dados de veiculação consolidados e filtrados.

**Funcionalidades:**
- Visualização de veiculações por campanha, canal, data e período.
- Filtros por canal de mídia (TV, Rádio, OOH, Digital etc.).
- Sub-views dedicadas para veiculação Google Ads e Meta Ads.
- Exibição de métricas: inserções, impressões, cliques, custo e CTR.
- Gráficos interativos via Chart.js.
- API JSON interna para renderização dinâmica de gráficos (`/api/veiculacao-data/`).

---

### 5.6 Módulo de Contratos

**Objetivo:** Centralizar o upload e controle de contratos por campanha.

**Funcionalidades:**
- Wizard de upload em dois passos (seleção de cliente → seleção de campanha → upload).
- Upload de múltiplos arquivos de contrato por campanha.
- Histórico de uploads com data e usuário responsável.
- Log de auditoria automático ao realizar upload.

**Modelos de dados:**
- `ContractUpload` — campanha, arquivo
- `MediaPlanUpload` — campanha, arquivo, resumo (JSON)

---

### 5.7 Módulo de Relatórios e Analytics

**Objetivo:** Fornecer visibilidade de performance das campanhas com dados consolidados.

**Funcionalidades:**
- Dashboard principal do cliente com KPIs e status de campanha.
- Relatórios por cliente e por campanha.
- Relatório consolidado cross-campaign.
- Analytics avançado com gráficos de séries temporais e indicadores de desempenho.
- Painel "DashOn" — dashboard premium com métricas estendidas.
- Filtros por período, canal e campanha.
- Timeline visual das campanhas com status em tempo real.

---

### 5.8 Módulo de Alertas

**Objetivo:** Comunicação formal da agência para o cliente dentro da plataforma.

**Funcionalidades:**
- Criação de alertas com título, mensagem e nível de prioridade.

| Prioridade | Uso |
|-----------|-----|
| BAIXA | Informações gerais |
| NORMAL | Comunicações padrão |
| ALTA | Avisos importantes |
| URGENTE | Ações imediatas necessárias |

- Badge de notificação com contagem de não lidos (animação de sino).
- Modal de alertas pendentes exibido automaticamente.
- Rastreamento de leitura: data, hora e usuário que leu.
- Histórico completo de alertas enviados.

**Modelos de dados:**
- `Alert` — título, mensagem, prioridade, cliente, enviado_por, lido, lido_em, lido_por

---

### 5.9 Módulo de Auditoria

**Objetivo:** Manter rastreabilidade completa de todas as ações críticas do sistema.

**Eventos Rastreados:**

| Categoria | Eventos |
|-----------|---------|
| Autenticação | LOGIN, LOGOUT, LOGIN_FAILED |
| Campanhas | CAMPAIGN_CREATED, CAMPAIGN_UPDATED, CAMPAIGN_DELETED |
| Peças | PIECE_CREATED, PIECE_DELETED |
| Assets | ASSET_UPLOADED |
| Usuários | USER_CREATED, USER_UPDATED, USER_DELETED |
| Clientes | CLIENTE_CREATED, CLIENTE_UPDATED |
| Uploads | MEDIA_PLAN_UPLOADED, CONTRACT_UPLOADED |

**Dados Capturados por Evento:**
- Usuário responsável
- Cliente afetado
- Endereço IP
- User-Agent do browser
- Timestamp com índice no banco
- Detalhes em JSON (contexto específico de cada evento)

**Interface de Visualização:**
- Filtros por tipo de evento, usuário, cliente e período
- Paginação de resultados
- Exportação de logs

---

### 5.10 Módulo de Usuários e Permissões

**Objetivo:** Controlar o acesso ao sistema por perfil e por cliente.

**Perfis de Acesso:**

| Perfil | Nível de Acesso |
|--------|----------------|
| ADMIN | Acesso total ao sistema, incluindo criação de usuários e configurações |
| COLABORADOR | Acesso administrativo sem permissão de operações destrutivas |
| CLIENTE | Acesso restrito ao portal do cliente (apenas seus dados) |

**Funcionalidades:**
- Criação e edição de usuários por perfil.
- Vinculação obrigatória de usuários CLIENTE a um cliente específico.
- Impersonação: admins podem visualizar o sistema como um cliente específico sem fazer logout (`Entrar como Cliente`).
- Funções adicionais: `VIEWER` (somente leitura).
- Controle de senha e dados de acesso.
- Login personalizado por slug do cliente.

**Decorators de Proteção de Views:**
- `@require_admin` — exige perfil ADMIN ou COLABORADOR
- `@require_true_admin` — exige perfil ADMIN ou superusuário
- `@require_cliente_view` — exige perfil CLIENTE

---

## 6. Integrações Externas

### 6.1 Google Ads

**Protocolo:** OAuth 2.0 + REST API (não gRPC)
**API Version:** v23
**Endpoint:** `https://googleads.googleapis.com/v23/customers/{cid}/googleAds:search`

**Fluxo de Autorização:**
1. Agência gera URL de consentimento via `gads_auth_url`.
2. Usuário autoriza no Google (`offline_access`).
3. Callback captura `code` e troca por `access_token` + `refresh_token`.
4. Tokens armazenados criptografados com `django.core.signing`.

**Sincronização:**
- Busca campanhas ativas do Google Ads e vincula a `PlacementLine` via `external_ref`.
- Busca métricas diárias (impressões, cliques, custo) e persiste em `PlacementDay`.
- Renovação automática de token expirado antes de cada sync.
- Comando de linha: `python manage.py sync_google_ads [--cliente-id=X] [--days=N]`
- Sync manual via interface web: botão "Sincronizar Agora".

**Configurações Requeridas:**
```env
GOOGLE_ADS_CLIENT_ID=
GOOGLE_ADS_CLIENT_SECRET=
GOOGLE_ADS_DEVELOPER_TOKEN=
GOOGLE_ADS_REDIRECT_URI=
```

**Pré-requisitos:**
- OAuth 2.0 Client ID (aplicação Web) no Google Cloud Console.
- Developer Token com acesso **Basic** no Google Ads.

---

### 6.2 Meta Ads (Facebook / Instagram)

**Protocolo:** OAuth 2.0 + Meta Graph API REST
**API Version:** v22.0
**Escopo:** `ads_read`

**Fluxo de Autorização:**
1. Agência gera URL do Facebook Login dialog.
2. Usuário autoriza.
3. Callback: token de curta duração → troca por token de longa duração (~60 dias).
4. Token armazenado criptografado com `django.core.signing`.

**Sincronização:**
- Busca campanhas da conta de anúncios e vincula a `PlacementLine` (canal META).
- Busca insights diários (impressões, cliques, custo) e persiste em `PlacementDay`.
- Comando de linha: `python manage.py sync_meta_ads [--cliente-id=X] [--days=N]`

**Configurações Requeridas:**
```env
META_ADS_APP_ID=
META_ADS_APP_SECRET=
META_ADS_REDIRECT_URI=
```

**Pré-requisitos:**
- App em developers.facebook.com com produto "Marketing API" habilitado.

---

### 6.3 Gerenciamento de Logs de Sincronização

Para ambas as integrações, o sistema mantém:
- `SyncLog` / `MetaSyncLog` com status (`RUNNING`, `SUCCESS`, `ERROR`), timestamps e contagem de registros sincronizados.
- Interface de visualização dos logs de sync.
- Ação de limpar logs de sync.
- Ação de limpar dados de veiculação sincronizados.

---

## 7. Segurança e Controle de Acesso

### 7.1 Autenticação
- Autenticação padrão Django via sessão.
- Login geral (`/login/`) e login de marca (`/login/<slug>/`).
- Opção "lembrar-me" configurável.
- Registro de tentativas de login (inclusive falhas) no AuditLog.

### 7.2 Isolamento Multi-Tenant
- Cada usuário CLIENTE está vinculado a exatamente um `Cliente`.
- Todos os dados (campanhas, peças, veiculações, alertas) são filtrados por `cliente_id` em todas as queries.
- Impersonação de admins é controlada por sessão, sem alterar o perfil real do usuário.

### 7.3 Criptografia de Tokens
- Tokens de OAuth (Google e Meta) são criptografados em repouso usando `django.core.signing` com a `SECRET_KEY` do Django.
- Nenhum token é armazenado em texto plano no banco de dados.

### 7.4 Proteção de Views
- Todos os endpoints verificam papel (role) via decorators ou funções helper.
- `effective_role(request)` e `effective_cliente_id(request)` centralizam a lógica de autorização.
- `X_FRAME_OPTIONS = SAMEORIGIN` permite preview de HTML5 por iframe do mesmo domínio.

### 7.5 CSRF
- Proteção CSRF padrão do Django em todos os formulários.

---

## 8. Infraestrutura e Implantação

### 8.1 Variáveis de Ambiente

| Variável | Descrição |
|----------|-----------|
| `DJANGO_SECRET_KEY` | Chave secreta do Django |
| `DJANGO_DEBUG` | True/False |
| `DJANGO_USE_POSTGRES` | Habilitar PostgreSQL |
| `DATABASE_URL` | URL de conexão com banco de dados |
| `GOOGLE_ADS_CLIENT_ID` | OAuth Google Ads |
| `GOOGLE_ADS_CLIENT_SECRET` | OAuth Google Ads |
| `GOOGLE_ADS_DEVELOPER_TOKEN` | Token de desenvolvedor |
| `GOOGLE_ADS_REDIRECT_URI` | URL de callback OAuth |
| `META_ADS_APP_ID` | ID do App Meta |
| `META_ADS_APP_SECRET` | Segredo do App Meta |
| `META_ADS_REDIRECT_URI` | URL de callback OAuth |

### 8.2 Armazenamento de Arquivos

| Tipo | Caminho |
|------|---------|
| Peças criativas | `media/campaigns/assets/` |
| Contratos | `media/campaigns/contracts/` |
| Planos de mídia | `media/campaigns/media_plans/` |
| Logos de clientes | `media/clientes/logos/` |

### 8.3 Dependências de Sistema
- `ffprobe` (parte do pacote `ffmpeg`) — necessário para extração de metadados de vídeo.
- Python 3.8+
- pip packages: Django 4.2, openpyxl, (ver `requirements.txt`)

### 8.4 Banco de Dados
- **Desenvolvimento:** SQLite3 (`db.sqlite3`)
- **Produção:** PostgreSQL (recomendado), configurável via env var `DJANGO_USE_POSTGRES=1`

### 8.5 Implantação Recomendada
- Servidor WSGI: Gunicorn ou uWSGI
- Proxy reverso: Nginx
- Coleta de estáticos: `python manage.py collectstatic`
- Migrations: `python manage.py migrate`

---

## 9. Requisitos Não-Funcionais

### 9.1 Performance
- Queries de dashboard devem responder em menos de 2 segundos para até 100 campanhas ativas.
- Upload de planilha XLSX com até 500 linhas deve ser processado em menos de 10 segundos.
- Sync com Google Ads ou Meta Ads para 30 dias de dados deve completar em menos de 60 segundos por conta.

### 9.2 Usabilidade
- Interface responsiva compatível com desktop (resolução mínima 1280×768).
- Navegação clara com sidebar fixa e breadcrumbs de contexto.
- Feedback visual imediato em operações de upload e sync (loading, sucesso, erro).

### 9.3 Manutenibilidade
- Código Python seguindo PEP 8.
- Templates Django com blocos bem definidos (`{% block content %}`).
- Funções de autorização centralizadas em `web/authz.py`.
- Logs de auditoria como mecanismo central de rastreabilidade.

### 9.4 Escalabilidade
- Banco PostgreSQL em produção para suportar crescimento de dados.
- Armazenamento de arquivos compatível com soluções de objeto (S3-compatible) via substituição do backend de `DEFAULT_FILE_STORAGE`.
- Suporte a múltiplos workers via servidor WSGI.

### 9.5 Disponibilidade
- Sem dependência de serviços externos para funcionamento das funcionalidades offline.
- Integrações com Google/Meta degradam graciosamente (sync falha sem afetar o sistema principal).

---

## 10. Entregáveis Esperados

Para propostas de **desenvolvimento, manutenção ou extensão** do sistema, espera-se:

### 10.1 Documentação Técnica
- [ ] Diagrama de arquitetura atualizado.
- [ ] Documentação de API (endpoints JSON internos).
- [ ] Guia de instalação e configuração de ambiente.
- [ ] Documentação dos modelos de dados com relacionamentos.

### 10.2 Código-Fonte
- [ ] Repositório Git com histórico de commits organizado.
- [ ] `requirements.txt` atualizado e versionado.
- [ ] Migrations Django aplicadas e sem conflitos.
- [ ] Testes automatizados (unitários e de integração) com cobertura mínima de 70%.

### 10.3 Infraestrutura
- [ ] Scripts de deploy (Docker Compose ou equivalente).
- [ ] Configuração de variáveis de ambiente documentada.
- [ ] Configuração de cron jobs para sync automático das integrações.

### 10.4 Qualidade
- [ ] Revisão de segurança (OWASP Top 10).
- [ ] Revisão de performance das queries principais.
- [ ] Plano de backup e recuperação de dados.

---

## 11. Critérios de Avaliação

As propostas recebidas serão avaliadas com base nos seguintes critérios:

| Critério | Peso |
|----------|------|
| Aderência técnica ao stack existente (Django, Python, Vanilla JS) | 25% |
| Qualidade da proposta técnica e entendimento do sistema | 20% |
| Experiência comprovada com sistemas multi-tenant | 15% |
| Experiência com integrações OAuth (Google Ads, Meta Ads) | 15% |
| Prazo e cronograma de entrega | 10% |
| Custo total | 10% |
| Suporte pós-entrega e SLA | 5% |

---

## 12. Glossário

| Termo | Definição |
|-------|-----------|
| **Campanha** | Conjunto de veiculações e peças de uma ação publicitária |
| **Peça Criativa** | Arquivo de mídia (vídeo, imagem, áudio, HTML5) usado em uma campanha |
| **Linha de Veiculação** | Registro de uma inserção em um canal de mídia específico |
| **PlacementDay** | Registro diário de métricas de uma linha de veiculação |
| **Multi-tenant** | Arquitetura onde múltiplos clientes compartilham a mesma instância com isolamento de dados |
| **Impersonação** | Capacidade de um administrador de visualizar o sistema como um cliente sem trocar de conta |
| **external_ref** | Identificador externo (ID de campanha no Google ou Meta) usado para vincular dados sincronizados |
| **AuditLog** | Registro imutável de eventos do sistema com metadados de rastreabilidade |
| **XLSX Import** | Importação de plano de mídia via planilha Excel (.xlsx) |
| **runtime_state** | Estado calculado em tempo real da campanha (ao vivo, agendada, encerrada) |
| **OAuth 2.0** | Protocolo de autorização delegada para acesso a APIs externas |
| **CTR** | Click-Through Rate — taxa de cliques por impressão |
| **OOH** | Out of Home — mídia exterior (outdoors, painéis, busdoor) |
| **DashOn** | Módulo de dashboard premium com funcionalidades estendidas |

---

*Este documento descreve o estado atual do sistema DashMonitor e deve ser usado como referência base para propostas de manutenção, evolução ou re-implementação da plataforma.*

*Dúvidas sobre este documento podem ser direcionadas ao responsável técnico do projeto.*
