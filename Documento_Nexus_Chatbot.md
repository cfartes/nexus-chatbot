# Nexus Atende — Especificação técnica

**Atendimento no WhatsApp com IA e equipe humana.**

Este documento consolida a arquitetura de software, modelagem de dados, regras de negócio e fluxos assíncronos para o desenvolvimento da plataforma multi-tenant de atendimento via WhatsApp, integrada a instâncias multi-sessão do **OpenWA**, equipada com recuperação vetorial (RAG) e transbordo inteligente para operadores humanos.

---

## 1. Visão Geral e Requisitos

### 1.1. Objetivos do Sistema
* **Multi-tenancy Rígido**: Isolamento total de clientes (empresas), configurações, operadores, histórico e base vetorial.
* **Integração WhatsApp Multi-sessão**: Conexão com VPS OpenWA gerenciando múltiplos números e pareamentos independentes.
* **Motor Híbrido (IA + Humano)**:
  * Respostas autônomas alimentadas por documentos (PDF, DOCX, TXT) e scraping de URLs.
  * Transbordo dinâmico para operadores humanos com pausa do bot e notificação em tempo real.
  * Painel de Live Chat para intervenção manual e reativação do bot sob demanda.
* **Gestão de Memória Dual**:
  * **Curto Prazo**: Janela deslizante de 15 minutos via Redis para contexto de conversa contínua.
  * **Longo Prazo**: Persistência de perfil do cliente (número, nome, histórico cumulativo e resumo de atendimentos anteriores) no PostgreSQL para saudações contextualizadas em retornos futuros.
* **Controle de Acesso (RBAC)**: Perfis de Administrador (gestão da conta, base de dados e IA) e Operadores (atendimento de chamados).

---

## 2. Arquitetura da Solução

```
[Cliente WhatsApp]
        │
        ▼
 [OpenWA VPS]  ──(HTTP Webhook)──► [FastAPI API Gateway]
                                           │
                ┌──────────────────────────┴──────────────────────────┐
                ▼                                                     ▼
        [Redis Cluster]                                         [PostgreSQL]
        - Fila Celery                                       - Tenants, Usuários, Perfis
        - Lock Atômico de Sessão                            - Histórico de Mensagens
        - Memória 15 min (TTL)                              - Chunks RAG com pgvector
                │
                ▼
      [Celery Worker Pool]
        ├── 1. Validação de Estado (`bot_active`)
        ├── 2. Extração de Memória (Curto e Longo Prazo)
        ├── 3. Busca Vetorial (pgvector - Cosseno)
        ├── 4. Execução da LLM (Gemini / OpenAI / Ollama)
        └── 5. Dispatch de Mensagem ──► [OpenWA API REST]
```

### Componentes Principais
* **API Gateway (FastAPI)**: Recebe webhooks do OpenWA, gerencia autenticação JWT, expõe WebSockets para o painel de atendimento e gerencia upload de conhecimento.
* **Fila de Mensageria (Redis + Celery)**: Desacopla o webhook síncrono das chamadas à LLM, evitando timeouts e perdas de pacotes.
* **Banco de Dados (PostgreSQL + extensão `pgvector`)**: Armazenamento relacional unificado com capacidades de busca por similaridade semântica (vetores).
* **Painel Web (Frontend SPA / WebSocket)**: Painel de Live Chat, pareamento por QR Code, cadastro de operadores e gerenciamento de bases de conhecimento.

---

## 3. Modelo de Dados Relacional e Vetorial (PostgreSQL)

```sql
-- Ativação da extensão vetorial
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";

-- 1. Tenants (Empresas clientes)
CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(150) NOT NULL,
    phone_number VARCHAR(30) UNIQUE,
    openwa_session_id VARCHAR(100) UNIQUE NOT NULL,
    is_connected BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 2. Usuários da Plataforma (Admin e Operadores)
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(150) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'operator', -- 'admin', 'operator'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 3. Configurações de IA por Tenant
CREATE TABLE ai_configs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID UNIQUE NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    provider VARCHAR(50) NOT NULL, -- 'gemini', 'openai', 'ollama'
    api_key_encrypted TEXT,
    model_name VARCHAR(100) NOT NULL,
    temperature NUMERIC(3,2) DEFAULT 0.30,
    system_prompt TEXT NOT NULL,
    fallback_message TEXT DEFAULT 'Estou transferindo você para um de nossos especialistas. Aguarde um instante.',
    similarity_threshold NUMERIC(3,2) DEFAULT 0.70 -- Limiar mínimo para considerar conteúdo RAG válido
);

-- 4. Base de Conhecimento RAG
CREATE TABLE knowledge_chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    source_name VARCHAR(255) NOT NULL,
    source_type VARCHAR(50) NOT NULL, -- 'pdf', 'docx', 'url', 'manual'
    content TEXT NOT NULL,
    embedding vector(768) NOT NULL, -- 768 dimensões (compatível com Google text-embedding-004 e bge-base)
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX idx_chunks_tenant_vector ON knowledge_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- 5. Clientes Finais (Identificação permanente e memória de longo prazo)
CREATE TABLE customers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    phone_number VARCHAR(30) NOT NULL,
    name VARCHAR(150),
    total_interactions INT DEFAULT 0,
    summary TEXT, -- Resumo consolidado de atendimentos passados
    first_seen_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_seen_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(tenant_id, phone_number)
);

-- 6. Conversas Ativas e Estado de Transbordo
CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    bot_active BOOLEAN DEFAULT TRUE,
    assigned_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    last_interaction TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(tenant_id, customer_id)
);

-- 7. Histórico de Mensagens
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    sender_type VARCHAR(20) NOT NULL, -- 'customer', 'bot', 'operator'
    sender_id UUID REFERENCES users(id) ON DELETE SET NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX idx_messages_conversation ON messages (conversation_id, created_at DESC);
```

---

## 4. Ciclo de Vida da Mensagem e Gestão de Memória

### 4.1. Ingestão no Webhook
1. O OpenWA envia um `POST /api/v1/webhook` contendo payload da mensagem.
2. O FastAPI valida o `session_id` e associa ao `tenant_id`.
3. Executa um `UPSERT` na tabela `customers` buscando por `(tenant_id, phone_number)`:
   * Atualiza `last_seen_at`.
   * Se `NOW() - last_seen_at > 15 minutes`: sinaliza flag `is_new_session = TRUE`.
4. Verifica status de `bot_active` na conversa:
   * **Se `bot_active == FALSE`**: Dispara evento WebSocket para os operadores conectados daquele tenant e encerra o webhook.
   * **Se `bot_active == TRUE`**: Enfileira a tarefa no Celery (`process_incoming_whatsapp_message.delay(...)`). Retorna `HTTP 200 OK` imediatamente ao OpenWA.

### 4.2. Execução do Worker Celery
1. **Aquisição de Lock**: Obtém trava no Redis `lock:chat:{conversation_id}` para evitar processamento de mensagens concorrentes.
2. **Coleta de Memória de Curto Prazo**:
   * Consulta a chave Redis `chat_history:{conversation_id}`.
   * Se expirada (> 15 min), a lista de mensagens recentes é reiniciada vazia.
3. **Extração de Conhecimento (RAG)**:
   * Gera embedding da mensagem de entrada.
   * Executa busca por produto escalar/cosseno no PostgreSQL:
     ```sql
     SELECT content, 1 - (embedding <=> :query_embedding) AS similarity
     FROM knowledge_chunks
     WHERE tenant_id = :tenant_id
     ORDER BY embedding <=> :query_embedding
     LIMIT 3;
     ```
4. **Montagem do Contexto (Prompt)**:
   * **Perfil persistente**: Injeta nome do cliente, histórico de compras/demandas passadas (`customers.summary`).
   * **Instrução de Saudação**: Se `is_new_session == TRUE`, instrui a IA a fazer saudação calorosa utilizando o nome do cliente. Se `FALSE`, proíbe novas saudações e exige resposta direta.
   * **Contexto RAG**: Chunks recuperados acima do limiar de similaridade.
   * **Histórico Imediato**: Últimas mensagens trocadas nos últimos 15 minutos.
5. **Avaliação de Transbordo**:
   * A LLM é instruída com uma Function Call / Tool `request_human_handover(reason: str)`.
   * Critérios de acionamento:
     1. Solicitação explícita do usuário ("atendente", "falar com suporte").
     2. A similaridade do RAG não alcançou o limiar e a dúvida foge do conhecimento fornecido.
   * **Ação do Handover**:
     1. Atualiza `conversations.bot_active = FALSE`.
     2. Dispara a mensagem de fallback configurada no WhatsApp via OpenWA.
     3. Emite notificação de alerta sonoro/visual via WebSocket para a interface dos operadores.
6. **Resposta e Despacho**:
   * Em caso de resposta normal da IA, envia o texto via OpenWA (`POST /api/sessions/{id}/messages/send-text`) com `chatId` e `text`.
   * Persiste a resposta na tabela `messages`.
   * Atualiza o cache de 15 minutos no Redis (`EXPIRE chat_history:{conversation_id} 900`).

---

## 5. Pipeline de Ingestão de Conhecimento (RAG)

```
[Documento PDF/DOCX ou URL]
            │
            ▼
    [Extração de Texto]
  (pypdf / python-docx / trafilatura)
            │
            ▼
    [Recursive Chunking]
  (Chunk Size: 600 tokens | Overlap: 100 tokens)
            │
            ▼
  [Embeddings Generation]
  (Google Gemini text-embedding-004)
            │
            ▼
 [Armazenamento com Metadata]
 (PostgreSQL: knowledge_chunks)
```

* **Regras de Atualização**: O cliente pode substituir ou excluir documentos pela tela de configuração. Ao excluir um documento, todos os chunks associados àquele `source_name` e `tenant_id` são expurgados do banco vetorial.

---

## 6. Painel de Atendimento (Live Chat) e Gestão

### 6.1. Funcionalidades da Interface
* **Visão Operacional (Operadores e Admins)**:
  * Painel dividido em três filas:
    1. *Atendimento Automatizado (IA)*.
    2. *Aguardando Atendente (Transbordados)*.
    3. *Meus Atendimentos (Em curso manual)*.
  * Janela de chat com timeline completa e visualização clara de autores (`Cliente`, `IA`, `Operador`).
  * Botão de controle mestre: **"Pausar IA" / "Devolver para IA"**.
  * Input de texto para resposta imediata do operador conectado diretamente à API do OpenWA.
* **Visão Administrativa (Apenas Admins)**:
  * Gerenciamento de credenciais de operadores (`CRUD` de usuários).
  * Painel de configuração de IA (Seleção de provedor, inserção de API Key encriptada, ajuste de prompt e tolerância de temperatura).
  * Gerenciador de base de dados RAG (Upload de arquivos e inclusão de URLs monitoradas).
  * Conexão WhatsApp: Inicialização de sessão, exibição do QR Code gerado pelo OpenWA e indicador de status (Online/Offline).

---

## 7. Roadmap de Implementação

| Fase | Escopo de Entrega | Entregáveis Técnicos |
| :--- | :--- | :--- |
| **Fase 1** | **Infraestrutura e Banco de Dados** | Docker Compose (PostgreSQL com `pgvector`, Redis), migrações com Alembic, models SQLAlchemy e estrutura base do FastAPI. |
| **Fase 2** | **Conexão OpenWA e Webhook** | Criação de sessões OpenWA, rota receptora de webhook com validação de payload, enfileiramento Celery e cliente de disparo de mensagens. |
| **Fase 3** | **Motor de RAG e Pipeline de IA** | Módulo de extração de texto, geração de embeddings, busca semântica multi-tenant e adapter para múltiplos provedores (Gemini, OpenAI). |
| **Fase 4** | **Memória Dual e Transbordo** | Lógica de saudação inteligente, detecção de retorno (> 15 min), controle de estado `bot_active` e function calling para acionamento de humano. |
| **Fase 5** | **Live Chat e Front-end** | Comunicação bidirecional via WebSocket, interface web de atendimento multi-operador e telas de configuração de IA e base de documentos. |
```

Este arquivo reúne a modelagem relacional e vetorial, as regras de controle de sessão com janelas de tempo, a estratégia de memória persistente e a estrutura de transbordo para o live chat.

## 8. Definições complementares — Planos, autocadastro e referência visual

Definições confirmadas durante a revisão de requisitos. Esta seção complementa o documento; a arquitetura e o SQL anteriores ainda precisam de consolidação antes da implementação.

### 8.1. Planos e Superadmin

* O Superadmin terá painel próprio para administrar a plataforma, empresas, planos e integrações.
* O catálogo começa com Basic, Professional e Enterprise e permite criar outros planos e editar suas informações. Os planos não serão uma enumeração fixa no código.
* Preços, franquias e recursos de cada plano ainda serão definidos; não há valores aprovados.
* Proposta para validação: configurar nome, descrição, preço, operadores permitidos, consumo de IA, recursos habilitados e disponibilidade para contratação.
* Proposta para validação: preservar versões das condições contratadas, registrar alterações em auditoria e arquivar planos sem apagar vínculos históricos.
* Cada empresa terá um número de WhatsApp, independentemente do plano, conforme requisito já confirmado.

### 8.2. Autocadastro das empresas

* Diferentemente do RotaFY, o cadastro inicial da empresa será realizado pelo próprio cliente em uma página pública.
* Proposta de fluxo: escolha do plano, cadastro da empresa e do administrador, verificação do e-mail e configuração inicial de WhatsApp, expediente, equipe, conhecimento e Google Agenda.
* A criação da empresa e do primeiro administrador deve ser atômica e não deve conceder privilégios de Superadmin.
* O backend deve validar o plano e suas condições; preço, limites e permissões não podem ser aceitos como valores fornecidos pelo navegador.
* A empresa poderá utilizar uma demonstração com duração configurada pelo Superadmin. Ao final, receberá o link para pagamento antecipado da primeira mensalidade. O período mensal pago começa somente após a confirmação do primeiro pagamento.

### 8.3. Referência Nexus RotaFY

* Projeto de referência: `C:/Projetos/Nexus RotaFY`, consultado apenas para análise.
* Referências inspecionadas: `frontend/src/styles.css`, `frontend/src/billing/Billing.tsx`, `backend/app/billing/routes.py` e `backend/app/billing/schemas.py`.
* Usar como referência a identidade em azul-marinho e turquesa, fundos claros, menu lateral, cartões de planos, indicadores de status e formulários responsivos.
* O RotaFY apresenta criação de planos, publicação de versões, histórico, ativação/arquivamento e assinaturas por empresa. A adoção dessas regras no chatbot deve considerar os requisitos próprios deste produto.
* Não transportar regras específicas de viagens nem pressupor que o faturamento do RotaFY faça parte do escopo aprovado do chatbot.

### 8.4. Demonstração e cobrança antecipada via InfinitePay

Requisitos confirmados:

* Cobrança automatizada via InfinitePay, tomando como referência a integração existente no RotaFY (`backend/app/billing/infinitepay.py` e configurações de cobrança).
* O Superadmin configura a quantidade de dias de demonstração e a integração de pagamento da plataforma.
* Ao término da demonstração, gerar a cobrança e disponibilizar/enviar ao responsável pela empresa o link de pagamento da primeira mensalidade.
* O primeiro período mensal pago começa na confirmação do primeiro pagamento, não no cadastro nem no término da demonstração. Não cobrar retroativamente os dias de espera pelo pagamento inicial.
* As mensalidades são antecipadas: cada pagamento cobre o próximo período de serviço.
* Distinguir geração/envio automático de cobranças de débito recorrente no cartão; não presumir autorização ou suporte a débito automático apenas por existir checkout por link.

Recomendações técnicas para implementação:

* Registrar na contratação o prazo de demonstração aplicado; alterações globais posteriores não devem modificar demonstrações já iniciadas sem uma ação explícita e auditada.
* Persistir estados de demonstração, aguardando primeiro pagamento, assinatura ativa, pagamento pendente, suspensão e cancelamento.
* Processar notificações do provedor com deduplicação e verificação independente do pagamento, conferindo referência da cobrança, valor e conta recebedora. O redirecionamento do navegador não comprova pagamento.
* Repetições de notificações não podem criar períodos adicionais nem liberar outra empresa. Manter reconciliação de pagamentos para recuperar notificações perdidas.
* Registrar períodos e condições comerciais separadamente das cobranças e tentativas de checkout. Preservar condições de cobranças emitidas e períodos pagos ao editar um plano.
* O painel deve permitir consultar cobranças, status, links e falhas; durante restrição financeira, manter acesso ao pagamento e preservar os dados conforme política de retenção.

Pendências para definição:

* Marco inicial da demonstração: confirmação do e-mail ou primeira conexão do WhatsApp.
* Canal para envio de cobranças, independente da sessão WhatsApp da empresa devedora: e-mail e/ou número de cobrança da plataforma.
* Antecedência dos avisos de renovação, eventual tolerância e comportamento do atendimento ao expirar o período sem pagamento.
* Regra de mês calendário, inclusive datas 29 a 31, e início do novo período após pagamento atrasado. Proposta: mês calendário; renovação pontual estende o período existente e reativação após suspensão começa na confirmação do pagamento, sem cobrança do intervalo suspenso.

Referência pública consultada: https://www.infinitepay.io/checkout-documentacao . O contrato vigente da API deve ser validado na implementação; o código do RotaFY não substitui a documentação do provedor.

## 9. Escopo confirmado do piloto Nexus

O primeiro uso será o atendimento da própria Nexus via WhatsApp. A base mantém o isolamento por empresa, com um número de WhatsApp por empresa e vários operadores por número. O piloto usará a mesma VPS OpenWA do RotaFY. O Nexus terá sessão dedicada e deverá validar a versão e o contrato da instância antes do pareamento.

### 9.1. Sequência de entrega

1. **Atendimento humano em texto.** Parear o número por QR Code e exibir o status da sessão. Receber mensagens por webhook autenticado, deduplicar eventos e persistir o histórico. Todos os operadores da empresa veem a fila de espera. Um único operador assume cada conversa, mesmo quando dois tentam assumi-la ao mesmo tempo. O administrador pode transferir o atendimento. O operador responsável responde pelo painel e acompanha o envio.
2. **IA com RAG.** Responder com base no conhecimento da Nexus, usando fontes e histórico isolados por empresa. Encaminhar para a fila humana quando o cliente pedir um atendente ou quando faltar conhecimento para responder. Pausar a IA durante o atendimento humano, inclusive quando uma resposta estiver em processamento, e permitir sua reativação pelo painel.

### 9.2. Itens posteriores

Google Agenda fica fora do escopo atual. Autocadastro público, catálogo comercial e cobrança InfinitePay ficam para depois do piloto. As regras comerciais permanecem na seção 8.

### 9.3. Referência de implementação

Adaptar do RotaFY o pareamento, o status da sessão, a validação de assinatura do webhook, a conferência do vínculo entre empresa e sessão e a deduplicação de mensagens. Usar o chat e as telas de configuração como referência para o painel. Implementar as adaptações segundo o `agents.md` e as diretrizes de segurança, privacidade e acessibilidade de `C:/Projetos`.

O guia local `C:/Projetos/API Whatsapp/1_5062084322337490808_1.md` documenta a listagem e o status de sessões, o formato de `chatId` e o envio de texto. Usar o UUID da sessão dedicado ao Nexus. Para obter o QR Code e validar o recebimento de eventos, consultar a implementação do RotaFY e conferir o contrato da versão instalada. Configurar a autenticação no backend por variáveis de ambiente, sem copiar credenciais do guia para o repositório.
