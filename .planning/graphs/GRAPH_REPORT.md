# Graph Report - Nexus Chatbot  (2026-11-21)

## Corpus Check
- 108 files · ~44,895 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 10 file(s) not represented in the graph (top: (none) 6, .example 1, .ini 1)

## Summary
- 1064 nodes · 3024 edges · 57 communities (29 shown, 28 thin omitted)
- Extraction: 88% EXTRACTED · 12% INFERRED · 0% AMBIGUOUS · INFERRED: 368 edges (avg confidence: 0.92)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `b35615bc`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- errorMessage
- Operator
- routes/knowledge.py
- routes/operators.py
- TenantRepository
- openwa.py
- IntegrationService
- routes/auth.py
- knowledge_documents.py
- package.json
- services/openwa_webhook.py
- labels
- install_vps.py
- check_work.py
- tenant_transaction
- main.py
- environment
- compilerOptions
- WorkItem
- Settings
- Nexus Atende — Especificação técnica
- Nexus Atende
- Nexus Atende — Implementado
- BotRepository
- api
- worker
- healthcheck
- services
- postgres
- web
- request_validation_error
- _NotificationConnection
- allowBuilds
- AGENTS.md
- PENDENCIAS.md
- nexus-atende

## God Nodes (most connected - your core abstractions)
1. `tenant_transaction()` - 75 edges
2. `Operator` - 68 edges
3. `IntegrationService` - 56 edges
4. `TenantRepository` - 33 edges
5. `errorMessage()` - 33 edges
6. `OperatorService` - 32 edges
7. `api()` - 29 edges
8. `ConversationService` - 28 edges
9. `ConversationRepository` - 27 edges
10. `lifespan()` - 26 edges

## Surprising Connections (you probably didn't know these)
- `Executar o painel web` --references--> `Origin`  [INFERRED]
  IMPLEMENTADO.md → frontend/src/features/atendimento/settings.tsx
- `authenticated_operator()` --uses--> `Operator`  [INFERRED]
  backend/src/api/routes/auth.py → backend/src/schemas/auth.py
- `mutation_operator()` --uses--> `Operator`  [INFERRED]
  backend/src/api/routes/auth.py → backend/src/schemas/auth.py
- `administrator()` --uses--> `Operator`  [INFERRED]
  backend/src/api/routes/auth.py → backend/src/schemas/auth.py
- `administrator_mutation()` --uses--> `Operator`  [INFERRED]
  backend/src/api/routes/auth.py → backend/src/schemas/auth.py

## Import Cycles
- None detected.

## Communities (57 total, 28 thin omitted)

### Community 0 - "errorMessage"
Cohesion: 0.05
Nodes (78): config, Page(), metadata, Page(), api(), ApiError, Conversation, csrfToken() (+70 more)

### Community 1 - "Operator"
Cohesion: 0.07
Nodes (29): acknowledge_transfer(), claim(), close(), conversation_events(), conversation_service(), messages(), operators(), queue_counts() (+21 more)

### Community 2 - "routes/knowledge.py"
Cohesion: 0.08
Nodes (32): delete(), ingest(), ingest_file(), ingest_url(), knowledge_service(), origins(), preview(), save_origin() (+24 more)

### Community 3 - "routes/operators.py"
Cohesion: 0.08
Nodes (23): accept(), create(), create_function(), delete(), delete_function(), functions(), operator_service(), operators() (+15 more)

### Community 4 - "TenantRepository"
Cohesion: 0.08
Nodes (26): companies(), archive_client(), clients(), create_client(), list_clients(), postal_address(), renew_admin(), _update() (+18 more)

### Community 5 - "openwa.py"
Cohesion: 0.09
Nodes (21): administrator(), administrator_mutation(), connection(), pair(), qr(), update_phone(), whatsapp_service(), PhoneInUse (+13 more)

### Community 6 - "IntegrationService"
Cohesion: 0.12
Nodes (15): ai(), handoff_email(), integrations(), openwa(), resend(), save_handoff_email(), test_resend(), view() (+7 more)

### Community 7 - "routes/auth.py"
Cohesion: 0.10
Nodes (23): authenticated_operator(), change_password(), check_origin(), current_operator(), login(), logout(), mutation_operator(), _service() (+15 more)

### Community 8 - "knowledge_documents.py"
Cohesion: 0.07
Nodes (14): Answer, extract_url(), _PageText, _Choice, _Completion, _Embedding, _Embeddings, _GeminiEmbedding (+6 more)

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
Cohesion: 0.13
Nodes (11): bootstrap(), choose(), create_environment(), detect_routing(), main(), output(), private_write(), public_check() (+3 more)

### Community 13 - "check_work.py"
Cohesion: 0.17
Nodes (14): check(), check_whatsapp(), request(), check(), call(), login(), check(), check() (+6 more)

### Community 14 - "tenant_transaction"
Cohesion: 0.25
Nodes (3): tenant_transaction(), IntegrationRepository, enqueue()

### Community 15 - "main.py"
Cohesion: 0.18
Nodes (4): lifespan(), verify_runtime_access(), EventRepository, ConversationEvents

### Community 16 - "environment"
Cohesion: 0.21
Nodes (18): environment, FORWARDED_ALLOW_IPS, NEXUS_ATENDE_CONFIG_KEY, NEXUS_ATENDE_DATABASE_URL, NEXUS_ATENDE_KNOWLEDGE_URL_ORIGIN, NEXUS_ATENDE_OLLAMA_URL, NEXUS_ATENDE_OPENAI_API_KEY, NEXUS_ATENDE_OPENAI_MODEL (+10 more)

### Community 17 - "compilerOptions"
Cohesion: 0.11
Nodes (17): compilerOptions, allowJs, esModuleInterop, incremental, isolatedModules, jsx, lib, module (+9 more)

### Community 18 - "WorkItem"
Cohesion: 0.21
Nodes (5): finish(), WorkRepository, WhatsAppDispatch, WorkItem, Worker

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
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 271 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **28 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `tenant_transaction()` connect `tenant_transaction` to `Operator`, `routes/knowledge.py`, `routes/operators.py`, `TenantRepository`, `IntegrationService`, `routes/auth.py`, `services/openwa_webhook.py`, `check_work.py`, `main.py`, `WorkItem`, `BotRepository`?**
  _High betweenness centrality (0.047) - this node is a cross-community bridge._
- **Are the 23 inferred relationships involving `Operator` (e.g. with `administrator()` and `administrator_mutation()`) actually correct?**
  _`Operator` has 23 INFERRED edges - model-reasoned connections that need verification._
- **What connects `nexus-atende` to the rest of the system?**
  _1 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `errorMessage` be split into smaller, more focused modules?**
  _Cohesion score 0.050669772859638904 - nodes in this community are weakly interconnected._
- **Why does `Operator` connect `Operator` to `routes/knowledge.py`, `routes/operators.py`, `TenantRepository`, `openwa.py`, `IntegrationService`, `routes/auth.py`, `tenant_transaction`, `BotRepository`?**
  _High betweenness centrality (0.042) - this node is a cross-community bridge._
- **Are the 18 inferred relationships involving `IntegrationService` (e.g. with `integrations()` and `BotService`) actually correct?**
  _`IntegrationService` has 18 INFERRED edges - model-reasoned connections that need verification._
- **Should `Operator` be split into smaller, more focused modules?**
  _Cohesion score 0.07113543091655267 - nodes in this community are weakly interconnected._