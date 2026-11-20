# Nexus Atende — Implementado

- Base FastAPI em `backend/src`, com contratos Pydantic separados das rotas.
- `GET /api/v1/health` responde `200` com `{"status":"ok"}` quando a aplicação está em execução. A rota verifica o processo da API.
- Dependências Python gerenciadas com `uv`.
- Ambiente local em `compose.yaml` com PostgreSQL 17, pgvector e Redis, acessíveis pela rede interna do Compose.
- Migração Alembic `0001_atendimento` para empresas, usuários, clientes, conversas e mensagens. As tabelas usam RLS forçada e chaves estrangeiras compostas para impedir vínculos entre empresas.
- Teste SQL cobre leitura sem escopo, acesso entre empresas e tentativa de atribuição a um operador de outra empresa.
- Repositório assíncrono de configuração da empresa via SQLAlchemy e `asyncpg`. O repositório configura o escopo dentro de cada transação e retorna um contrato Pydantic.
- O FastAPI inicializa o pool a partir de `NEXUS_ATENDE_DATABASE_URL`, verifica se a conexão está sujeita a RLS e encerra o pool ao desligar. O repositório fica disponível no estado da aplicação para os próximos serviços.
- Administradores e operadores usam `POST /api/v1/auth/login`, `GET /api/v1/auth/me` e `POST /api/v1/auth/logout`. O login recebe `tenant_id`, `email` e `password`. A sessão expira em oito horas e apenas o hash do token é persistido. O logout exige origem válida e o cabeçalho `X-CSRF-Token` com o valor do cookie `nexus_atende_csrf`.
- A migração `0002_auth` cria as sessões isoladas por empresa e os limites de login persistentes por IP e identidade. Defina `NEXUS_ATENDE_PUBLIC_ORIGIN` com a origem HTTPS do painel, sem caminho ou barra final. Configure o proxy para que a API aceite o endereço encaminhado apenas de proxies confiáveis.
- Administradores podem consultar o status em `GET /api/v1/whatsapp/connection` e obter o QR Code em `GET /api/v1/whatsapp/connection/qr`. A API resolve o UUID da sessão pela empresa autenticada e retorna o QR apenas durante o pareamento.
- `POST /api/v1/webhooks/openwa/{tenant_id}` recebe eventos `message.received`, valida HMAC sobre o corpo original e grava mensagens de texto diretas no PostgreSQL. A primeira mensagem cria o contato e coloca a conversa na fila. Entregas duplicadas não geram novas mensagens ou contatos.
- A API de conversas mostra a fila compartilhada, as conversas da IA e os atendimentos do operador. Administradores podem consultar todos os atendimentos atribuídos e transferi-los dentro da empresa. A atribuição é atômica no PostgreSQL.
- O operador responsável pode enfileirar uma resposta de texto. A API registra o identificador informado pelo painel para deduplicar reenvios do mesmo comando. O worker grava o ID retornado pelo OpenWA e o histórico exibe o estado do envio. Um resultado incerto fica visível e exige conferência humana antes de novo envio.
- A IA do piloto usa OpenAI e pgvector. A base aceita texto, TXT, DOCX, PDF com texto e páginas de uma origem HTTPS autorizada. A recuperação busca só na base da empresa, usa o histórico de até 15 minutos e conserva um resumo de atendimentos anteriores para retornos.
- Quando a conversa entra na fila humana, o worker pode enviar um e-mail pelo Resend com a referência da conversa. O e-mail não inclui telefone ou conteúdo do WhatsApp. Retentativas de e-mail usam a mesma chave de idempotência.
- Administradores podem cadastrar, atualizar e desativar operadores. A desativação revoga sessões e devolve as conversas atribuídas à fila. O worker limpa sessões e tentativas expiradas.

## Operar a fila pela API

As rotas exigem sessão autenticada. Para assumir ou transferir, envie também a origem configurada e `X-CSRF-Token`.

| Rota | Uso |
| --- | --- |
| `GET /api/v1/conversations` | Filtrar por `queue=waiting`, `bot`, `mine` ou `assigned`. A última exige administrador. |
| `GET /api/v1/conversations/{id}/messages` | Ler do mais recente ao mais antigo. Passe o ID da última mensagem em `before` para continuar. |
| `POST /api/v1/conversations/{id}/claim` | Assumir uma conversa em espera. Se outra pessoa assumiu primeiro, a API retorna `409`. |
| `POST /api/v1/conversations/{id}/transfer` | Transferir uma conversa atribuída para o `user_id` informado no corpo, como administrador. |
| `GET /api/v1/conversations/operators` | Listar operadores ativos e administradores habilitados para transferência. |
| `POST /api/v1/conversations/{id}/messages` | Enfileirar texto com `request_id` (UUID) e `text`. Reaproveite o `request_id` ao repetir a mesma solicitação. |
| `PUT /api/v1/conversations/{id}/bot` | Pausar ou devolver para a IA com `{"active": false}` ou `{"active": true}`. |
| `GET /api/v1/conversations/events` | Receber sinais SSE de mudança da empresa. Ao receber `change`, recarregue pela API a fila ou o histórico aberto. |

## Administrar operadores e a base de conhecimento

| Rota | Uso |
| --- | --- |
| `GET` e `POST /api/v1/operators` | Listar operadores ou enviar um convite com `name` e `email`. |
| `PUT /api/v1/operators/{id}` | Alterar `name` e `is_active` de um operador. |
| `POST /api/v1/operators/{id}/invite` | Reenviar um convite pendente, substituindo o link anterior. |
| `POST /api/v1/operators/accept-invite` | Definir a primeira senha com um convite válido por 24 horas, de uso único. |
| `GET` e `PUT /api/v1/knowledge` | Listar fontes ou substituir uma fonte por `source` e `text`. |
| `PUT /api/v1/knowledge/file?kind=pdf&source=Manual` | Envie o arquivo como corpo binário. `kind` aceita `pdf`, `docx` e `txt`. Limites de 4 MiB e 40.000 caracteres extraídos. |
| `PUT /api/v1/knowledge/url` | Importar ou atualizar uma página com `source` e `url`. A origem vem de `NEXUS_ATENDE_KNOWLEDGE_URL_ORIGIN`. |
| `DELETE /api/v1/knowledge?source=Manual` | Remover a fonte e seus vetores. |
| `GET` e `PUT /api/v1/knowledge/welcome` | Consultar ou salvar a saudação da empresa com `message` de até 500 caracteres. Campo vazio desativa o texto fixo. |
| `POST /api/v1/knowledge/preview` | Simular uma pergunta com `question`. Retorna a resposta, o encaminhamento ou a indisponibilidade, além das fontes recuperadas. Não cria mensagens ou alertas. |

O cadastro e as alterações administrativas exigem sessão de administrador, origem configurada e token CSRF. A aceitação do convite usa a origem configurada e o token secreto do link.

## Configurar as integrações pelo painel

Em **Configurações → Integrações**, selecione OpenAI, Google Gemini, Anthropic Claude ou Ollama local e informe o modelo. Para Claude, configure também uma chave OpenAI para embeddings. Para usar o Ollama, configure `NEXUS_ATENDE_OLLAMA_URL` no servidor e escolha um modelo de chat e um modelo de embeddings compatível com 768 dimensões. Reimporte as fontes quando mudar o provedor ou modelo de embeddings.

Configure `NEXUS_ATENDE_CONFIG_KEY` com uma chave Fernet gerada pelo backend e preserve o mesmo valor na API e no worker. Para gerar uma, rode `uv run --locked python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` em `backend`. As chaves das integrações são criptografadas no banco. O painel informa se uma chave existe e oferece a substituição sem exibir o valor salvo.

Para Resend, salve a chave, o remetente verificado e, se desejar alertas de fila, o e-mail da equipe. Convites usam o remetente verificado e o destinatário de cada operador. A opção **Reenviar convite** gera um novo link quando o anterior expira ou o envio falha.

Para OpenWA, salve a chave no painel e consulte a sessão, o status e o QR Code na área WhatsApp. O endereço OpenWA, a sessão dedicada e o segredo do webhook são provisionados no servidor para limitar o acesso na VPS compartilhada. As credenciais de ambiente continuam disponíveis como configuração inicial.

Em **Configurações → Boas-vindas**, o administrador define o texto que abre a primeira resposta automática e uma nova sessão após 15 minutos sem interação. A saudação também acompanha o primeiro encaminhamento automático para a fila humana. Para o acervo da Nexus, cadastre fontes distintas por serviço ou aplicativo. A importação web lê uma página por URL da origem HTTPS configurada.

## Executar a migração local

Copie `.env.example` para `.env`, configure `NEXUS_ATENDE_DB_PASSWORD` e execute na raiz do projeto:

```powershell
docker compose up -d --wait
Push-Location backend
uv run --locked alembic upgrade head --sql | Set-Content -Encoding ascii "$env:TEMP/nexus-atende-0001.sql"
Pop-Location
Get-Content -Raw "$env:TEMP/nexus-atende-0001.sql" | docker compose exec -T postgres psql -U postgres -d nexus_atende -v ON_ERROR_STOP=1
Get-Content -Raw backend/tests/tenant_isolation.sql | docker compose exec -T postgres psql -U postgres -d nexus_atende -v ON_ERROR_STOP=1
```

A migração completa se aplica a um banco novo. Para atualizações, consulte `SELECT version_num FROM alembic_version` e use `alembic upgrade <revisão_atual>:head --sql`. Por exemplo, `alembic upgrade 0002_auth:head --sql` inclui as novas tabelas e alterações a partir da revisão de autenticação.

## Login de runtime e validação

Depois da migração, abra `docker compose exec postgres psql -U postgres -d nexus_atende` e execute uma vez no ambiente:

```sql
CREATE ROLE nexus_atende_runtime LOGIN INHERIT NOSUPERUSER NOBYPASSRLS IN ROLE nexus_atende_app;
\password nexus_atende_runtime
```

Defina `NEXUS_ATENDE_DATABASE_URL` com uma URL `postgresql+asyncpg` para esse login no ambiente do processo da API. O chamador do repositório deve fornecer um UUID de empresa autorizado pelo servidor.

O teste `backend/tests/check_runtime.py` usa um banco descartável com duas empresas de IDs `00000000-0000-0000-0000-000000000001` e `00000000-0000-0000-0000-000000000002`. Defina `NEXUS_ATENDE_TEST_DATABASE_URL` para o login restrito e `NEXUS_ATENDE_TEST_ADMIN_URL` para o superusuário do banco descartável. Rode `uv run --locked python -m tests.check_runtime` em `backend` para validar o escopo da transação e a inicialização com cada login.

Para preparar o primeiro administrador, gere o hash interativamente com `uv run --locked python -m src.services.passwords` em `backend`. Use o login de migração para inserir a empresa em `nexus_atende.tenants` e o usuário em `nexus_atende.users`, com o UUID da empresa, e-mail em minúsculas, nome, hash e `role = 'admin'`. Entregue o UUID da empresa e o e-mail ao administrador pelo canal interno do piloto.

## Configurar o OpenWA no piloto

Defina `NEXUS_ATENDE_OPENWA_BASE_URL` com a URL HTTPS da API terminada em `/api` e `NEXUS_ATENDE_OPENWA_API_KEY` com a credencial fornecida para a integração. Crie e inicie uma sessão dedicada ao Nexus no painel do OpenWA. Com o login de migração, registre o UUID da sessão em `nexus_atende.tenants.openwa_session_id` na empresa Nexus e o número em `phone_number`. Os endpoints passam a consultar essa sessão.

Para habilitar a entrada, configure `NEXUS_ATENDE_OPENWA_WEBHOOK_TENANT_ID` com o UUID da empresa Nexus e `NEXUS_ATENDE_OPENWA_WEBHOOK_SECRET` com um segredo aleatório de pelo menos 32 caracteres. Cadastre na sessão dedicada o webhook da API com esse mesmo segredo. A assinatura esperada é `X-OpenWA-Signature: sha256=<hex>`. O limite do corpo é 512 KiB. A configuração atual vincula o segredo a uma única empresa, suficiente para o piloto.

## Executar a API, o worker e os alertas

Após migrar o banco e criar o login de runtime, preencha `NEXUS_ATENDE_DATABASE_URL` no `.env` com o host `postgres`. Na raiz do projeto, execute `docker compose --profile app up -d --build --wait`. A API local responde por padrão em `http://127.0.0.1:8085`. O worker usa o UUID de `NEXUS_ATENDE_OPENWA_WEBHOOK_TENANT_ID` para processar a fila da Nexus. Em implantação, configure o proxy HTTPS, a origem pública e `NEXUS_ATENDE_TRUSTED_PROXY_IPS` com os endereços dos proxies confiáveis. O proxy deve encaminhar o stream SSE sem buffering e aceitar uploads de até 4 MiB.

Para ligar os alertas no worker, configure `NEXUS_ATENDE_RESEND_API_KEY`, `NEXUS_ATENDE_RESEND_FROM` com um remetente verificado e `NEXUS_ATENDE_RESEND_TO` com o e-mail da equipe. O arquivo local `C:/Projetos/API Whatsapp/resend.txt` é a referência para a credencial e o endereço. Confirme se o endereço fornecido é o remetente ou o destinatário antes de ativar o worker. Sem configuração de Resend, os alertas permanecem na fila para processamento posterior.

O piloto usa uma fila transacional no PostgreSQL para IA, WhatsApp e e-mail. Eventos do painel usam SSE e notificações do PostgreSQL. O worker é um processo separado da API.

Rode `powershell -NoProfile -File backend/tests/run_local.ps1` para criar um PostgreSQL descartável e validar a API, a concorrência, o webhook, os envios, o RAG, os arquivos, o isolamento e o transbordo. Os provedores externos são simulados.

## Executar o painel web

O painel em `frontend` usa Next.js App Router, TypeScript, Tailwind e Astryx. Inclui login, filas de conversas, histórico, envio e status de entregas, transferência, controle da IA, QR Code, operadores e fontes do RAG.

Com a API em `http://127.0.0.1:8085`, configure `NEXUS_ATENDE_PUBLIC_ORIGIN=http://127.0.0.1:3000` no backend local. Em `frontend`, execute `corepack pnpm install --frozen-lockfile` e `corepack pnpm dev --hostname 127.0.0.1`. Acesse `http://127.0.0.1:3000`. Defina `NEXUS_ATENDE_API_URL` no ambiente do Next.js para usar outro endereço de API. O navegador usa rotas de mesma origem para sessão e SSE.

Para validar o painel, rode `corepack pnpm lint`, `corepack pnpm build` e `corepack pnpm exec astryx doctor --built .next` em `frontend`.

Para executar o painel em modo produção local, depois de preparar o banco, configure `NEXUS_ATENDE_PUBLIC_ORIGIN=http://127.0.0.1:3001` e rode `docker compose --profile web up -d --build --wait web`. O painel ficará em `http://127.0.0.1:3001` e encaminhará `/api/v1` à API na rede interna do Compose. O perfil `app` permanece disponível para executar o worker.

Na hospedagem, aponte o proxy HTTPS para o painel e configure `NEXUS_ATENDE_PUBLIC_ORIGIN` com a origem pública. Preserve o cabeçalho `Origin`, permita requisições SSE sem buffering e configure apenas proxies confiáveis em `NEXUS_ATENDE_TRUSTED_PROXY_IPS`.
