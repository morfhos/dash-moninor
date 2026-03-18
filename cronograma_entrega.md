# Cronograma de Entrega — DashMonitor
## 20 Dias Úteis | Projeto em Fase Final

**Cliente:** ___________________________
**Contrato:** ___________________________
**Data de início:** _____ / _____ / 2026
**Data de entrega final:** _____ / _____ / 2026
**Responsável técnico:** ___________________________
**Versão do documento:** 1.0

---

## Visão Geral das Fases

| Fase | Período | Dias Úteis | Foco |
|------|---------|------------|------|
| **Fase 1** — Infraestrutura e Ambiente | Semana 1 | D1 – D4 | Servidor, banco, domínio, e-mail |
| **Fase 2** — Backend e Segurança | Semana 1–2 | D4 – D8 | Auth, recuperação de senha, tenant, API |
| **Fase 3** — Importação de Dados | Semana 2 | D8 – D11 | Campanhas reais, integrações Google/Meta |
| **Fase 4** — Frontend e UX | Semana 3 | D12 – D15 | Refinamento de interface, responsividade |
| **Fase 5** — QA e Homologação | Semana 4 | D16 – D18 | Testes, ajustes, validação com cliente |
| **Fase 6** — Go-Live e Handoff | Semana 4 | D19 – D20 | Deploy final, treinamento, documentação |

---

## Detalhamento por Dia

### FASE 1 — Infraestrutura e Ambiente de Produção
> **Objetivo:** Servidor provisionado, banco de dados estável, domínio com SSL, e-mail configurado.

---

#### D1 — Provisionamento do Servidor e DNS

**Manhã**
- [ ] Contratar e provisionar VPS (recomendado: 4 vCPU / 8 GB RAM / 80 GB SSD — DigitalOcean, Hetzner ou AWS EC2)
- [ ] Configurar acesso SSH com chave pública (desabilitar acesso por senha)
- [ ] Criar usuário de deploy `dashmonitor` (sem sudo irrestrito)
- [ ] Instalar pacotes base: Python 3.11, Nginx, PostgreSQL 16, Redis 7, ffmpeg, certbot, git

**Tarde**
- [ ] Apontar DNS do domínio para o IP do servidor (registro A)
- [ ] Ativar proxy Cloudflare (laranja) + configurar SSL Full Strict
- [ ] Gerar certificado SSL via Certbot (`certbot --nginx -d app.seudominio.com.br`)
- [ ] Testar acesso HTTPS ao servidor (página 502 esperada — Nginx ativo, app ainda não)

**Entregável do dia:** Servidor online, domínio com HTTPS ativo.

---

#### D2 — Banco de Dados e Pool de Conexões

**Manhã**
- [ ] Criar banco PostgreSQL 16: `dashmonitor`, usuário `dashmonitor_app` (sem superuser)
- [ ] Ajustar `postgresql.conf` com parâmetros de produção (shared_buffers, work_mem, autovacuum)
- [ ] Instalar e configurar PgBouncer 1.22 (transaction pool mode, porta 6432)
- [ ] Testar conexão Django → PgBouncer → PostgreSQL com `CONN_MAX_AGE=0`

**Tarde**
- [ ] Configurar Redis 7 (senha, bind 127.0.0.1, maxmemory 512 MB)
- [ ] Instalar PgBouncer e validar `pgbouncer.ini`
- [ ] Criar arquivo `.env` de produção no servidor (permissão 600)
- [ ] Validar variáveis de ambiente com `python manage.py check --deploy`

**Entregável do dia:** Banco + pool + cache rodando, Django conectando com sucesso.

---

#### D3 — Deploy da Aplicação

**Manhã**
- [ ] Clonar repositório no servidor (`/app/`)
- [ ] Criar e ativar virtualenv, instalar `requirements.txt`
- [ ] Executar `python manage.py migrate` — validar criação de todas as tabelas
- [ ] Executar `python manage.py collectstatic`
- [ ] Criar superusuário inicial

**Tarde**
- [ ] Configurar `gunicorn.conf.py` com workers adequados ao servidor
- [ ] Criar e habilitar service systemd para Gunicorn
- [ ] Configurar Nginx com proxy para Gunicorn + servir `/static/` e `/media/`
- [ ] Testar acesso completo: HTTPS → Nginx → Gunicorn → Django → PostgreSQL

**Entregável do dia:** Aplicação acessível via HTTPS com login funcionando.

---

#### D4 — E-mail e Celery

**Manhã**
- [ ] Configurar provedor SMTP (Resend ou Mailgun — conta gratuita para início)
- [ ] Configurar registros SPF, DKIM e DMARC no DNS do domínio remetente
- [ ] Testar envio de e-mail via `python manage.py shell`: `send_mail(...)`
- [ ] Validar entrega na caixa de entrada (não spam)

**Tarde**
- [ ] Instalar Celery + `django-celery-beat` + `django-redis`
- [ ] Criar `backend/dashmonitor_django/celery.py` com config de produção
- [ ] Criar tasks: `sync_all_google_ads`, `sync_all_meta_ads`
- [ ] Configurar `CELERY_BEAT_SCHEDULE` (sync a cada 1h)
- [ ] Criar e habilitar services systemd para `celery_worker` e `celery_beat`
- [ ] Validar tasks executando: `celery -A dashmonitor_django inspect active`

**Entregável do dia:** E-mail transacional funcionando. Celery pronto para sync assíncrono.

---

### FASE 2 — Backend e Segurança
> **Objetivo:** Sistema de recuperação de senha completo (admin + cliente), isolamento multi-tenant auditado, endpoints protegidos.

---

#### D5 — Recuperação de Senha (Fluxo Admin/Colaborador)

**Manhã**
- [ ] Implementar view `password_reset_request` (formulário de solicitação por e-mail)
- [ ] Implementar view `password_reset_confirm` (formulário com nova senha via token)
- [ ] Implementar view `password_reset_complete` (confirmação de sucesso)
- [ ] Criar templates: `password_reset_request.html`, `password_reset_confirm.html`, `password_reset_complete.html`
- [ ] Registrar URLs: `/recuperar-senha/`, `/recuperar-senha/confirmar/<uidb64>/<token>/`

**Tarde**
- [ ] Criar template de e-mail HTML: `email/password_reset.html` com link seguro
- [ ] Criar template de e-mail TEXT: `email/password_reset.txt` (fallback)
- [ ] Configurar `PASSWORD_RESET_TIMEOUT = 3600` (token expira em 1h)
- [ ] Adicionar link "Esqueceu a senha?" no `login.html`
- [ ] Testar fluxo completo: solicitar → receber e-mail → redefinir → logar

**Entregável do dia:** Recuperação de senha admin/colaborador funcional e testada.

---

#### D6 — Recuperação de Senha (Fluxo Cliente Multi-brand)

**Manhã**
- [ ] Implementar view `password_reset_request_cliente` — recebe `slug` do cliente na URL
- [ ] Validar que o e-mail informado pertence a um usuário do cliente correto (isolamento de tenant)
- [ ] Criar template `password_reset_request_cliente.html` com logo e identidade visual do cliente
- [ ] Registrar URL: `/login/<slug>/recuperar-senha/`
- [ ] Adicionar link "Esqueceu a senha?" no `login_cliente.html`

**Tarde**
- [ ] Criar template de e-mail personalizado por cliente (inclui nome/logo do cliente)
- [ ] Testar que usuário do Cliente A não consegue redefinir senha usando URL de Cliente B
- [ ] Testar que o token é inválido após uso (one-time use)
- [ ] Testar que o token expira após 1h
- [ ] Adicionar evento `PASSWORD_RESET_REQUESTED` e `PASSWORD_RESET_COMPLETED` no `AuditLog`

**Entregável do dia:** Recuperação de senha multi-brand com isolamento de tenant validado.

---

#### D7 — Segurança e Isolamento Multi-tenant

**Manhã**
- [ ] Corrigir `api_piece_update`: adicionar verificação de `cliente_id` antes de permitir edição
- [ ] Corrigir `api_upload_piece_asset`: mesma verificação de tenant
- [ ] Auditar todos os endpoints da `web/urls.py` que recebem IDs nos parâmetros (verificar se validam posse do objeto)
- [ ] Criar helper `assert_owns_campaign(request, campaign)` para centralizar verificação

**Tarde**
- [ ] Adicionar `SECURE_SSL_REDIRECT=True`, `SECURE_HSTS_SECONDS`, headers de segurança no `settings.py`
- [ ] Validar `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `CSRF_TRUSTED_ORIGINS`
- [ ] Rodar `python manage.py check --deploy` — resolver todos os avisos
- [ ] Implementar endpoint `/health/` para monitoramento (retorna status do banco)
- [ ] Testar tentativa de acesso cruzado de tenant (usuário A acessando ID de campanha do B → deve retornar 403)

**Entregável do dia:** Zero vulnerabilidades de isolamento. Checklist `--deploy` limpo.

---

#### D8 — API, Índices e Performance

**Manhã**
- [ ] Aplicar migrations de índices de performance (`0006_perf_indexes`, `0008_perf_indexes`) em produção
- [ ] Verificar com `EXPLAIN ANALYZE` as queries das 3 views mais acessadas (dashboard, veiculação, relatórios)
- [ ] Adicionar `select_related` e `prefetch_related` onde houver N+1 queries detectadas
- [ ] Ativar `django-debug-toolbar` em staging para medir queries antes/depois

**Tarde**
- [ ] Implementar cache Redis para sidebar de clientes (context_processor `nav_context`)
- [ ] Implementar cache Redis para contagem de alertas não lidos (cache por cliente, TTL 60s)
- [ ] Configurar Sentry em produção (instalar SDK, configurar DSN, testar captura de exceção)
- [ ] Configurar UptimeRobot para monitorar `/health/` a cada 5 minutos

**Entregável do dia:** Performance de queries validada. Monitoramento ativo.

---

### FASE 3 — Importação de Dados
> **Objetivo:** Campanhas reais dos clientes importadas, integrações Google/Meta autorizadas e sincronizando.

---

#### D9 — Criação de Clientes e Usuários Reais

**Manhã**
- [ ] Criar os clientes reais no sistema (com logo, CNPJ e slug corretos)
- [ ] Criar usuários de cada cliente (CLIENTE role) com senhas temporárias
- [ ] Criar usuários da agência (ADMIN/COLABORADOR) com senhas definitivas
- [ ] Testar login de cada usuário (admin e cliente) em produção
- [ ] Validar isolamento: cada cliente vê apenas seus dados

**Tarde**
- [ ] Verificar e ajustar logos dos clientes (resolução, formato, tamanho)
- [ ] Configurar alertas de boas-vindas para os clientes
- [ ] Testar fluxo de recuperação de senha por e-mail para cada tipo de usuário
- [ ] Documentar credenciais de acesso para entrega ao cliente (PDF criptografado)

**Entregável do dia:** Todos os usuários e clientes reais cadastrados e validados.

---

#### D10 — Importação de Campanhas via XLSX

**Manhã**
- [ ] Receber planilhas de mídia reais do cliente
- [ ] Validar formato das planilhas (estrutura de colunas compatível com o parser)
- [ ] Ajustar mapeamento de colunas no `parse_media_plan_xlsx()` se necessário
- [ ] Importar campanhas do Cliente 1: validar PlacementLines e PlacementDays criados

**Tarde**
- [ ] Importar campanhas dos demais clientes
- [ ] Validar totais: comparar soma de inserções/custo da planilha com o banco
- [ ] Importar peças criativas (assets) via interface de upload
- [ ] Validar extração de metadados via ffprobe (duração dos vídeos)
- [ ] Configurar vinculação peça × linha (matriz de link)

**Entregável do dia:** Campanhas históricas e atuais importadas no sistema.

---

#### D11 — Integrações Google Ads e Meta Ads

**Manhã**
- [ ] Configurar OAuth App Google Ads no Google Cloud Console (URL de callback de produção)
- [ ] Realizar fluxo de autorização OAuth Google Ads em produção para cada conta
- [ ] Executar primeiro sync manual: `celery -A dashmonitor_django call integrations.tasks.sync_all_google_ads`
- [ ] Validar PlacementLines e PlacementDays sincronizados do Google Ads

**Tarde**
- [ ] Configurar App Meta Ads no developers.facebook.com (URL de callback de produção)
- [ ] Realizar fluxo de autorização OAuth Meta Ads para cada conta
- [ ] Executar primeiro sync manual Meta Ads
- [ ] Validar métricas (impressões, cliques, custo) sincronizadas
- [ ] Confirmar que Celery Beat está agendando syncs automáticos a cada 1h
- [ ] Validar logs de sync na interface de integrações

**Entregável do dia:** Google Ads e Meta Ads sincronizando automaticamente a cada hora.

---

### FASE 4 — Frontend e UX
> **Objetivo:** Interface polida, responsiva, com feedbacks visuais e experiência do cliente refinada.

---

#### D12 — Templates de Recuperação de Senha e E-mail

**Manhã**
- [ ] Finalizar visual dos templates de recuperação de senha (admin e cliente)
- [ ] Estilizar e-mail HTML de recuperação de senha (responsivo, logo, cores da marca)
- [ ] Validar renderização do e-mail nos principais clientes de e-mail (Gmail, Outlook)
- [ ] Testar em dispositivo móvel (formulários de login e recuperação)

**Tarde**
- [ ] Refinar template `login_cliente.html`: fundo com gradiente, logo centralizada, tipografia
- [ ] Adicionar animação de loading no botão "Entrar" durante submissão
- [ ] Adicionar feedback visual de erro (campo inválido com borda vermelha + mensagem)
- [ ] Testar fluxo completo de login → dashboard em mobile

**Entregável do dia:** Login e recuperação de senha com visual finalizado e responsivo.

---

#### D13 — Dashboard do Cliente

**Manhã**
- [ ] Revisar `dashboard.html`: stat cards com dados reais, formatação de valores monetários
- [ ] Implementar formatação BR: `R$ 1.234.567,89` em todos os campos de custo
- [ ] Validar cards de status das campanhas (LIVE_NOW, SCHEDULED, ENDED) com cores corretas
- [ ] Testar dashboard com dados reais dos clientes importados

**Tarde**
- [ ] Refinar gráficos Chart.js (cores, legendas, tooltips em PT-BR)
- [ ] Implementar loading skeleton nos gráficos enquanto dados carregam via AJAX
- [ ] Adicionar mensagem "Nenhuma campanha ativa" para clientes sem campanhas
- [ ] Validar modal de alertas: exibição, marcação como lido, badge de contagem

**Entregável do dia:** Dashboard do cliente com dados reais e visual refinado.

---

#### D14 — Veiculação, Relatórios e Timeline

**Manhã**
- [ ] Revisar `veiculacao.html`: filtros, tabela de inserções, métricas online (impressões, CTR)
- [ ] Validar dados de veiculação sincronizados do Google Ads e Meta (sub-views dedicadas)
- [ ] Testar filtros por data e canal em produção com dados reais
- [ ] Revisar `timeline_campanhas.html`: exibição temporal correta, status de cada campanha

**Tarde**
- [ ] Revisar `relatorios_campanhas.html`: totais corretos, exportação ou impressão
- [ ] Revisar `relatorios_consolidado.html`: cross-campaign metrics
- [ ] Testar `analytics.html` com dados reais (gráficos de série temporal)
- [ ] Validar `dashon.html` (dashboard premium) com dados reais

**Entregável do dia:** Módulos de veiculação, relatórios e analytics validados com dados reais.

---

#### D15 — Painel Administrativo e UX Geral

**Manhã**
- [ ] Revisar `admin_home.html`: overview geral com contagens reais de clientes e campanhas
- [ ] Testar sidebar: seletor de cliente, navegação entre módulos
- [ ] Testar impersonação de cliente: entrar como → visualizar → sair → estado correto restaurado
- [ ] Revisar `logs_auditoria.html`: filtros funcionando, paginação, eventos dos dias anteriores

**Tarde**
- [ ] Testar `integracoes.html`: status das contas Google/Meta, botões de sync e desconectar
- [ ] Revisar `campaign_link_matrix.html`: matriz peça × veiculação responsiva
- [ ] Testar upload de contrato (wizard em 2 passos) e import de XLSX em produção
- [ ] Revisão geral de responsividade em 1280px, 1440px e mobile (fallback)

**Entregável do dia:** Painel administrativo completo e revisado. UX sem regressões.

---

### FASE 5 — QA e Homologação
> **Objetivo:** Sistema validado pelo cliente. Bugs críticos corrigidos. Aprovação formal registrada.

---

#### D16 — QA Interno (Time Técnico)

**Manhã**
- [ ] Executar checklist de segurança completo (seção 10 do `arquitetura_de_producao.md`)
- [ ] Testar todos os fluxos de autenticação: login, logout, recuperação de senha (admin e cliente)
- [ ] Testar isolamento de tenant: usuário de Cliente A tentando acessar dados do B → 403
- [ ] Testar expiração de token de recuperação de senha (> 1h)

**Tarde**
- [ ] Testar importação XLSX com planilha intencionalmente malformada (tratar erros)
- [ ] Testar upload de arquivo acima do limite (100 MB) — validar mensagem de erro
- [ ] Testar sync Google Ads com token expirado — validar renovação automática
- [ ] Testar sync Meta Ads com token expirado — validar renovação automática
- [ ] Registrar e priorizar bugs encontrados

**Entregável do dia:** Relatório de bugs internos com prioridades.

---

#### D17 — Correção de Bugs e Ajustes

**Manhã**
- [ ] Corrigir todos os bugs críticos (P1: impede uso) e altos (P2: compromete funcionalidade)
- [ ] Re-testar fluxos afetados pelas correções

**Tarde**
- [ ] Corrigir bugs médios (P3: incomoda mas não bloqueia) e ajustes de UX do cliente
- [ ] Realizar smoke test completo pós-correções
- [ ] Preparar ambiente de homologação para acesso do cliente (URL, credenciais, guia rápido)

**Entregável do dia:** Ambiente estável. Zero bugs P1/P2.

---

#### D18 — Homologação com o Cliente

**Manhã**
- [ ] Apresentar sistema ao cliente com acesso guiado (videoconferência ou presencial)
- [ ] Percorrer com o cliente: login, dashboard, veiculação, relatórios, alertas
- [ ] Validar dados importados: cliente confirma que campanhas e métricas estão corretas
- [ ] Testar recuperação de senha ao vivo com e-mail real do cliente

**Tarde**
- [ ] Coletar feedback do cliente (lista de ajustes finais)
- [ ] Priorizar e estimar ajustes solicitados
- [ ] Implementar ajustes de homologação (pequenos — max. 4h de trabalho nesta fase)
- [ ] Obter aprovação formal por escrito (e-mail ou assinatura em ata de homologação)

**Entregável do dia:** Ata de homologação assinada. Lista de ajustes finais acordada.

---

### FASE 6 — Go-Live e Handoff
> **Objetivo:** Sistema em produção final. Cliente treinado. Documentação entregue. Suporte inicial ativo.

---

#### D19 — Go-Live Oficial

**Manhã**
- [ ] Executar checklist de go-live completo (`arquitetura_de_producao.md`, seção 15)
- [ ] Validar backups automáticos: executar backup manual e testar restore
- [ ] Confirmar Celery Beat executando syncs automáticos
- [ ] Confirmar monitoramento UptimeRobot ativo e alertas de e-mail configurados
- [ ] Confirmar Sentry capturando exceções em produção

**Tarde**
- [ ] Comunicar go-live ao cliente com URL definitiva
- [ ] Trocar senhas temporárias para senhas definitivas (orientar cada usuário)
- [ ] Conduzir sessão de treinamento: usuário admin da agência (1–2h)
- [ ] Conduzir sessão de treinamento: usuários cliente (30–45 min por cliente)
- [ ] Disponibilizar gravação do treinamento

**Entregável do dia:** Sistema em produção. Usuários treinados. Acessos definitivos entregues.

---

#### D20 — Documentação e Handoff

**Manhã**
- [ ] Entregar `arquitetura_de_producao.md` revisado com dados reais do servidor
- [ ] Entregar `RFP_DashMonitor.md` como documentação funcional do sistema
- [ ] Criar `RUNBOOK.md`: procedimentos operacionais (restart, backup, deploy, logs)
- [ ] Documentar credenciais e acessos em cofre seguro (1Password, Bitwarden ou similar)

**Tarde**
- [ ] Entregar relatório final do projeto: funcionalidades entregues, pendências, SLA de suporte
- [ ] Configurar canal de suporte pós-entrega (e-mail ou Slack)
- [ ] Combinar janela de suporte gratuito pós-entrega (recomendado: 15 dias)
- [ ] Reunião de encerramento com cliente — assinatura do Termo de Aceite Final

**Entregável do dia:** Documentação completa entregue. Termo de Aceite Final assinado.

---

## Resumo de Entregáveis por Fase

| Fase | Entregáveis |
|------|------------|
| **Fase 1** | Servidor HTTPS ativo, banco + pool + cache rodando, Gunicorn + Celery rodando, e-mail funcionando |
| **Fase 2** | Recuperação de senha admin + cliente, isolamento multi-tenant auditado, performance validada |
| **Fase 3** | Usuários e clientes reais cadastrados, campanhas importadas via XLSX, Google Ads e Meta Ads sincronizando |
| **Fase 4** | Interface refinada, responsiva, templates de e-mail prontos, dashboards com dados reais |
| **Fase 5** | Zero bugs críticos, ata de homologação assinada |
| **Fase 6** | Go-live, treinamento, documentação completa, Termo de Aceite Final |

---

## Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|-------|--------------|---------|-----------|
| Planilhas XLSX dos clientes em formato diferente do esperado | Alta | Médio | D10 reserva buffer para ajuste do parser |
| OAuth Google/Meta recusado por domínio não verificado | Média | Alto | D11 inclui buffer; verificar domínio na plataforma antes de D9 |
| Provedor SMTP marcando e-mails como spam | Média | Alto | Configurar SPF/DKIM/DMARC em D4; testar antes de ir a clientes reais |
| Volume de dados muito grande (>50 mil PlacementDays) | Baixa | Médio | Índices já criados; adicionar paginação nas views de relatório se necessário |
| Cliente solicitar muitos ajustes na homologação | Média | Médio | D17 já prevê buffer para ajustes; alinhar escopo em D18 manhã antes de implementar |

---

## Premissas e Dependências

**O cronograma pressupõe:**
- Acesso ao repositório Git do projeto disponível desde D1
- Planilhas XLSX das campanhas reais entregues até D9 (para D10)
- Credenciais das contas Google Ads e Meta Ads entregues até D10 (para D11)
- Logo e dados cadastrais dos clientes entregues até D8 (para D9)
- Cliente disponível para sessão de homologação no D18
- Servidor VPS contratado antes de D1 (ou custo incluso na proposta)

---

## Acordo de Escopo

Este cronograma cobre o projeto conforme escopo atual do DashMonitor. Solicitações de novas funcionalidades fora do escopo acordado serão tratadas como ordens de serviço adicionais, com prazo e custo a combinar.

---

**Aprovação do Cronograma:**

| | Cliente | Fornecedor |
|--|---------|-----------|
| **Nome** | | |
| **Cargo** | | |
| **Data** | | |
| **Assinatura** | | |

---

*Documento gerado em Março de 2026 — DashMonitor v1.0*
