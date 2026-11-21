# Graph Report - Nexus Chatbot  (2026-11-21)

## Corpus Check
- 111 files · ~228,083 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 10 file(s) not represented in the graph (top: (none) 6, .example 1, .ini 1)

## Summary
- 1106 nodes · 3088 edges · 57 communities (31 shown, 26 thin omitted)
- Extraction: 87% EXTRACTED · 13% INFERRED · 0% AMBIGUOUS · INFERRED: 392 edges (avg confidence: 0.92)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `c9052ec6`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- errorMessage
- ConversationService
- routes/knowledge.py
- routes/operators.py
- TenantRepository
- openwa.py
- IntegrationService
- routes/auth.py
- openai.py
- package.json
- services/openwa_webhook.py
- labels
- install_vps.py
- check_work.py
- Communities (57 total, 28 thin omitted)
- main.py
- environment
- compilerOptions
- tenant_transaction
- Settings
- Nexus Atende — Especificação técnica
- Nexus Atende
- Nexus Atende — Implementado
- BotRepository
- api
- worker
- healthcheck
- routes/conversations.py
- services
- postgres
- web
- request_validation_error
- allowBuilds
- AGENTS.md
- PENDENCIAS.md
- nexus-atende

## God Nodes (most connected - your core abstractions)
1. `tenant_transaction()` - 77 edges
2. `Operator` - 68 edges
3. `IntegrationService` - 58 edges
4. `TenantRepository` - 35 edges
5. `errorMessage()` - 35 edges
6. `OperatorService` - 33 edges
7. `Communities (57 total, 28 thin omitted)` - 30 edges
8. `api()` - 30 edges
9. `ConversationService` - 29 edges
10. `ConversationRepository` - 28 edges

## Surprising Connections (you probably didn't know these)
- `God Nodes (most connected - your core abstractions)` --references--> `lifespan()`  [INFERRED]
  .planning/graphs/GRAPH_REPORT.md → backend/src/main.py
- `God Nodes (most connected - your core abstractions)` --references--> `tenant_transaction()`  [INFERRED]
  .planning/graphs/GRAPH_REPORT.md → backend/src/repositories/database.py
- `God Nodes (most connected - your core abstractions)` --references--> `TenantRepository`  [INFERRED]
  .planning/graphs/GRAPH_REPORT.md → backend/src/repositories/tenants.py
- `God Nodes (most connected - your core abstractions)` --references--> `IntegrationService`  [INFERRED]
  .planning/graphs/GRAPH_REPORT.md → backend/src/services/integrations.py
- `God Nodes (most connected - your core abstractions)` --references--> `OperatorService`  [INFERRED]
  .planning/graphs/GRAPH_REPORT.md → backend/src/services/operators.py

## Import Cycles
- None detected.

## Communities (57 total, 26 thin omitted)

### Community 0 - "errorMessage"
Cohesion: 0.05
Nodes (78): config, Page(), metadata, Page(), api(), ApiError, Conversation, csrfToken() (+70 more)

### Community 1 - "ConversationService"
Cohesion: 0.11
Nodes (11): _close_locked(), ConversationRepository, BotStateRequest, ConversationSummary, HistoryMessage, QueueCounts, SendTextRequest, TransferNotice (+3 more)

### Community 2 - "routes/knowledge.py"
Cohesion: 0.07
Nodes (34): delete(), ingest(), ingest_file(), ingest_url(), knowledge_service(), origins(), preview(), save_origin() (+26 more)

### Community 3 - "routes/operators.py"
Cohesion: 0.09
Nodes (22): accept(), create(), create_function(), delete(), delete_function(), functions(), operator_service(), operators() (+14 more)

### Community 4 - "TenantRepository"
Cohesion: 0.07
Nodes (26): archive_client(), clients(), create_client(), list_clients(), postal_address(), renew_admin(), _update(), update_client() (+18 more)

### Community 5 - "openwa.py"
Cohesion: 0.08
Nodes (20): connection(), pair(), qr(), update_phone(), whatsapp_service(), PhoneInUse, OpenWAQR, OpenWASession (+12 more)

### Community 6 - "IntegrationService"
Cohesion: 0.11
Nodes (16): ai(), handoff_email(), integrations(), openwa(), resend(), save_handoff_email(), test_resend(), view() (+8 more)

### Community 7 - "routes/auth.py"
Cohesion: 0.10
Nodes (29): administrator(), administrator_mutation(), authenticated_operator(), change_password(), check_origin(), companies(), current_operator(), login() (+21 more)

### Community 8 - "openai.py"
Cohesion: 0.15
Nodes (9): _Choice, _Completion, _Embedding, _Embeddings, _GeminiEmbedding, _GeminiEmbeddings, _Message, _OllamaEmbeddings (+1 more)

### Community 9 - "package.json"
Cohesion: 0.07
Nodes (34): dependencies, @astryxdesign/core@0.7.16, @astryxdesign/theme-neutral@0.7.16, next@16.4.6, react@^19.3.1, react-dom@^19.3.1, @stylexjs/stylex@~0.19.2, devDependencies (+26 more)

### Community 10 - "services/openwa_webhook.py"
Cohesion: 0.12
Nodes (12): health(), receive(), IncomingMessageRepository, HealthResponse, IncomingText, OpenWAEvent, OpenWAMessage, OpenWAReceivedEvent (+4 more)

### Community 11 - "labels"
Cohesion: 0.07
Nodes (31): environment, labels, networks, ports, FORWARDED_ALLOW_IPS, traefik.docker.network, traefik.enable, traefik.http.routers.nexus-atende-api.entrypoints (+23 more)

### Community 12 - "install_vps.py"
Cohesion: 0.07
Nodes (12): _PageText, bootstrap(), choose(), create_environment(), detect_routing(), main(), output(), private_write() (+4 more)

### Community 13 - "check_work.py"
Cohesion: 0.17
Nodes (12): check(), check_whatsapp(), request(), check(), call(), login(), check(), check() (+4 more)

### Community 14 - "Communities (57 total, 28 thin omitted)"
Cohesion: 0.05
Nodes (37): Communities (57 total, 28 thin omitted), Community 0 - "errorMessage", Community 10 - "services/openwa_webhook.py", Community 11 - "labels", Community 12 - "install_vps.py", Community 13 - "check_work.py", Community 14 - "tenant_transaction", Community 15 - "main.py" (+29 more)

### Community 15 - "main.py"
Cohesion: 0.15
Nodes (5): lifespan(), EventRepository, Listener, _NotificationConnection, ConversationEvents

### Community 16 - "environment"
Cohesion: 0.21
Nodes (18): environment, FORWARDED_ALLOW_IPS, NEXUS_ATENDE_CONFIG_KEY, NEXUS_ATENDE_DATABASE_URL, NEXUS_ATENDE_KNOWLEDGE_URL_ORIGIN, NEXUS_ATENDE_OLLAMA_URL, NEXUS_ATENDE_OPENAI_API_KEY, NEXUS_ATENDE_OPENAI_MODEL (+10 more)

### Community 17 - "compilerOptions"
Cohesion: 0.11
Nodes (17): compilerOptions, allowJs, esModuleInterop, incremental, isolatedModules, jsx, lib, module (+9 more)

### Community 18 - "tenant_transaction"
Cohesion: 0.15
Nodes (10): tenant_transaction(), OutgoingMessageRepository, enqueue(), finish(), WorkRepository, WhatsAppDispatch, WorkItem, WorkReceipt (+2 more)

### Community 19 - "Settings"
Cohesion: 0.11
Nodes (5): verify_runtime_access(), IntegrationRepository, Settings, run(), Worker

### Community 20 - "Nexus Atende — Especificação técnica"
Cohesion: 0.14
Nodes (13): 1.1. Objetivos do Sistema, 1. Visão Geral e Requisitos, 2. Arquitetura da Solução, 3. Modelo de Dados Relacional e Vetorial (PostgreSQL), 4.1. Ingestão no Webhook, 4.2. Execução do Worker Celery, 4. Ciclo de Vida da Mensagem e Gestão de Memória, 5. Pipeline de Ingestão de Conhecimento (RAG) (+5 more)

### Community 21 - "Nexus Atende"
Cohesion: 0.15
Nodes (12): 1. Primeiro acesso, senha e perfis, 2. Funções, colaboradores e configuração inicial, 3. Rotina de atendimento e indicadores, 4. Automação, base de conhecimento e solução de problemas, Ajuste a experiência automática, Atenda uma conversa, Conecte o WhatsApp e configure os avisos, Dúvidas frequentes (+4 more)

### Community 22 - "Nexus Atende — Implementado"
Cohesion: 0.17
Nodes (11): Origin, Administrar operadores e a base de conhecimento, Configurar as integrações pelo painel, Configurar o OpenWA no piloto, Executar a API, o worker e os alertas, Executar a migração local, Executar o painel web, Instalar na VPS (+3 more)

### Community 24 - "api"
Cohesion: 0.22
Nodes (9): build, depends_on, image, ports, profiles, restart, postgres, condition (+1 more)

### Community 25 - "worker"
Cohesion: 0.22
Nodes (9): condition, api, worker, depends_on, command, depends_on, image, profiles (+1 more)

### Community 26 - "healthcheck"
Cohesion: 0.57
Nodes (8): healthcheck, interval, retries, test, timeout, healthcheck, healthcheck, healthcheck

### Community 27 - "routes/conversations.py"
Cohesion: 0.16
Nodes (16): acknowledge_transfer(), claim(), close(), conversation_events(), conversation_service(), messages(), operators(), queue_counts() (+8 more)

### Community 28 - "services"
Cohesion: 0.33
Nodes (5): image, services, redis, volumes, postgres_data

### Community 29 - "postgres"
Cohesion: 0.33
Nodes (6): POSTGRES_DB, POSTGRES_PASSWORD, environment, image, volumes, postgres

### Community 30 - "web"
Cohesion: 0.33
Nodes (6): web, build, image, ports, profiles, restart

### Community 35 - "allowBuilds"
Cohesion: 0.50
Nodes (3): allowBuilds, @astryxdesign/cli, @astryxdesign/core

## Knowledge Gaps
- **1 isolated node(s):** `nexus-atende`
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 308 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **26 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `God Nodes (most connected - your core abstractions)` connect `ConversationService` to `errorMessage`, `routes/operators.py`, `TenantRepository`, `IntegrationService`, `Communities (57 total, 28 thin omitted)`, `main.py`, `tenant_transaction`?**
  _High betweenness centrality (0.131) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `tenant_transaction()` (e.g. with `God Nodes (most connected - your core abstractions)` and `Suggested Questions`) actually correct?**
  _`tenant_transaction()` has 2 INFERRED edges - model-reasoned connections that need verification._
- **What connects `nexus-atende` to the rest of the system?**
  _1 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `errorMessage` be split into smaller, more focused modules?**
  _Cohesion score 0.050669772859638904 - nodes in this community are weakly interconnected._
- **Why does `errorMessage()` connect `errorMessage` to `ConversationService`, `routes/auth.py`?**
  _High betweenness centrality (0.120) - this node is a cross-community bridge._
- **Are the 23 inferred relationships involving `Operator` (e.g. with `administrator()` and `administrator_mutation()`) actually correct?**
  _`Operator` has 23 INFERRED edges - model-reasoned connections that need verification._
- **Should `ConversationService` be split into smaller, more focused modules?**
  _Cohesion score 0.1111111111111111 - nodes in this community are weakly interconnected._