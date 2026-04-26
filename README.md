<p align="center">
  <img src="https://img.shields.io/badge/python-3.12+-blue?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/LangGraph-agent-purple?logo=langchain&logoColor=white" alt="LangGraph">
  <img src="https://img.shields.io/badge/pgvector-PostgreSQL-336791?logo=postgresql&logoColor=white" alt="pgvector">
  <img src="https://img.shields.io/badge/Celery-async-37814A?logo=celery&logoColor=white" alt="Celery">
  <img src="https://img.shields.io/badge/Docker-compose-2496ED?logo=docker&logoColor=white" alt="Docker">
</p>

# FastDocs

> **Multi-tenant RAG microservice** — ingere documentos, indexa como embeddings vetoriais e responde perguntas em linguagem natural, tudo por trás de uma simples API Key.

FastDocs é um serviço de Retrieval-Augmented Generation (RAG) projetado para ser consumido por outras aplicações. Cada consumidor (tenant) possui coleções de documentos, threads de chat e contexto de queries isolados, acessíveis através do header `X-API-Key`. Tenants e API Keys são provisionados via API administrativa protegida, e cada tenant traz a própria chave Gemini — o custo de LLM fica isolado por cliente.

---

## Funcionalidades

| Feature | Descrição |
|---------|-----------|
| **Admin API** | Endpoints `/admin/*` para CRUD de tenants, emissão e revogação de API Keys |
| **Auth em camada dupla** | Rotas admin protegidas por `X-Service-Key` + IP allowlist; rotas tenant por `X-API-Key` SHA-256 |
| **Gemini key por tenant** | Cada tenant cadastra a própria chave Gemini (criptografada com Fernet); custo isolado |
| **Multi-tenant** | Isolamento total: toda query inclui `WHERE tenant_id = ?` na camada de repositório |
| **Multi-formato** | PDF, DOCX, XLSX, CSV, TXT, MD, PPTX e imagens |
| **OCR** | Auto-detecção de PDFs escaneados com roteamento para Tesseract |
| **LangGraph RAG** | Agente com 6 nós: análise, recuperação, avaliação, reranking, reformulação e geração |
| **pgvector** | Busca vetorial no mesmo Postgres — sem banco extra para gerenciar |
| **Pipeline assíncrono** | Celery workers processam documentos em background; upload retorna `202` imediatamente |
| **Outbox Pattern** | Publicação transacional via Postgres `LISTEN/NOTIFY` — zero eventos perdidos |
| **Chat com histórico** | Conversas em threads com estado persistido via checkpointer do LangGraph no Redis |
| **Streaming SSE** | Respostas em tempo real via Server-Sent Events (`stream: true`) |
| **Rate limiting** | Sliding window por tenant/endpoint com Redis sorted sets |
| **Cache de queries** | Cache Redis com invalidação automática ao ingerir novo documento |
| **Webhooks** | Callbacks com assinatura HMAC-SHA256 e 3 retentativas com backoff exponencial |

---

## Arquitetura

```mermaid
flowchart TB
    subgraph AdminCaller["Backend Administrativo"]
        AA[Serviço interno]
    end

    subgraph Client
        A[Consumer Service]
    end

    subgraph API["FastAPI (async)"]
        ADM[Admin Router\nX-Service-Key + IP]
        B[Auth Middleware\nX-API-Key → tenant_id + gemini_key]
        C[Chat Router]
        D[Documents Router]
        E[Projects Router]
    end

    subgraph Processing["Background Workers"]
        F[Outbox Relay\nLISTEN/NOTIFY]
        G[Celery Worker]
        H["Parse → Clean → Chunk → Embed"]
    end

    subgraph Storage
        I[(PostgreSQL\n+ pgvector)]
        J[(Redis\nBroker + Cache)]
        K[(Azure Blob\nOriginal Files)]
    end

    subgraph AI
        L[Gemini Flash\nChat LLM — por tenant]
        M[LangGraph Agent\nRAG com retry]
    end

    AA -->|X-Service-Key| ADM
    ADM -->|CRUD tenants + keys| I
    A -->|X-API-Key| B
    B --> C & D & E
    D -->|Upload 202| K
    D -->|Outbox Event| I
    I -->|LISTEN/NOTIFY| F
    F -->|Publish task| J
    J -->|Consume| G
    G --> H
    H -->|Embeddings — key do tenant| I
    C --> M
    M -->|Similarity search| I
    M -->|Generate — key do tenant| L
    J -.->|Cache| C
```

### Fluxo de Provisionamento (Admin)

```
POST /admin/tenants
  Body: { name, gemini_api_key, webhook_url? }
  → Valida a gemini_api_key contra a API do Google
  → Criptografa a key com Fernet e grava no banco
  → Emite a primeira API Key para o tenant
  → Retorna { id, name, api_key: "fdocs_..." }   ← plaintext exibido uma única vez
```

### Fluxo de Ingestão

```
Upload → 202 Accepted
  → Outbox Event (atômico com o INSERT do documento)
  → Relay publica no Redis via LISTEN/NOTIFY
  → Celery Worker consome a task
  → Carrega gemini_key do tenant e descriptografa
  → Download do Blob → Parse → Clean → Chunk → Embed → pgvector
  → Webhook callback (se configurado)
```

### Fluxo de Query

```
POST /api/chat/message
  → Auth → tenant_id + gemini_key injetados
  → Cache lookup (Redis)
  → LangGraph Agent (usa gemini_key do tenant):
      analyze_query → retrieve (pgvector) → evaluate_context
        ├─ suficiente? → rerank → generate (Gemini Flash) → response
        └─ insuficiente? → reformulate → retrieve novamente (máx 2 tentativas)
  → Armazena resultado no cache (TTL 30min)
```

### Recuperação de documentos travados

O Celery Beat executa `recover_stuck_documents` a cada 60 segundos. Documentos em status `processing` por mais de 10 minutos são automaticamente resetados para `pending` (ou marcados como `error` após 3 tentativas).

---

## Stack

| Camada | Tecnologia | Motivo |
|--------|-----------|--------|
| **API** | FastAPI + Pydantic v2 | Async nativo, validação robusta, docs OpenAPI automáticas |
| **ORM** | SQLAlchemy 2.0 + Alembic | Queries async type-safe, migrations versionadas |
| **Vetores** | pgvector (PostgreSQL 16) | Sem DB extra — relacional + vetorial em uma query |
| **RAG** | LangChain + LangGraph | Orquestração de pipeline + agente com estado |
| **LLM + Embeddings** | Gemini Flash + gemini-embedding-001 | Key por tenant — custo isolado |
| **Cripto** | Fernet (cryptography) | Criptografia reversível das chaves Gemini no banco |
| **Tasks** | Celery + Redis | Processamento em background com retry e scheduler |
| **Storage** | Azure Blob (Azurite local) | Pronto para Azure, paridade local com Azurite |
| **OCR** | Tesseract | Open source, local, sem custo de API |
| **Cache** | Redis | Cache de queries + rate limiting + broker Celery |

---

## Quick Start

### Pré-requisitos

- [Docker](https://docs.docker.com/get-docker/) e Docker Compose
- Uma [Google AI API Key](https://aistudio.google.com/apikey) (Gemini) — agora por tenant

### 1. Clonar e configurar

```bash
git clone https://github.com/TiagoAReiz/fastdocs.git
cd fastdocs

cp backend/.env.example backend/.env
```

Edite `backend/.env` e preencha as variáveis obrigatórias:

```bash
# Gerar SERVICE_API_KEY
python -c "import secrets; print(secrets.token_urlsafe(48))"

# Gerar ENCRYPTION_KEY
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

> A connection string do Azurite já tem o valor padrão preenchido — não precisa alterar para desenvolvimento local.

### 2. Subir todos os serviços

```bash
docker compose up --build
```

Isso inicia **7 serviços**: FastAPI backend, Celery worker, Celery beat, Outbox relay, PostgreSQL (pgvector), Redis e Azurite.

As migrations do Alembic rodam automaticamente no startup do backend.

### 3. Verificar

```bash
curl http://localhost:8000/health
# → {"status": "ok"}

# Swagger UI
open http://localhost:8000/docs
```

---

## Referência da API

### Admin (provisionamento de tenants)

Todos os endpoints `/admin/*` exigem `X-Service-Key` e devem ser chamados de um IP cadastrado em `ADMIN_ALLOWED_IPS`.

```bash
# Criar tenant + emitir primeira API Key (key aparece uma única vez)
curl -X POST http://localhost:8000/admin/tenants \
  -H "X-Service-Key: $SERVICE_API_KEY" \
  -H "X-Forwarded-For: $MEU_IP" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "acme",
    "gemini_api_key": "AIza...",
    "webhook_url": "https://acme.com/webhook"
  }'
# → { "id": "...", "name": "acme", "api_key": "fdocs_..." }

# Listar tenants
curl http://localhost:8000/admin/tenants \
  -H "X-Service-Key: $SERVICE_API_KEY" \
  -H "X-Forwarded-For: $MEU_IP"

# Emitir nova API Key para um tenant
curl -X POST http://localhost:8000/admin/tenants/<tenant-uuid>/api-keys \
  -H "X-Service-Key: $SERVICE_API_KEY" \
  -H "X-Forwarded-For: $MEU_IP" \
  -H "Content-Type: application/json" \
  -d '{"label": "producao"}'

# Revogar API Key
curl -X DELETE http://localhost:8000/admin/api-keys/<key-uuid> \
  -H "X-Service-Key: $SERVICE_API_KEY" \
  -H "X-Forwarded-For: $MEU_IP"

# Rotacionar chave Gemini de um tenant
curl -X PATCH http://localhost:8000/admin/tenants/<tenant-uuid> \
  -H "X-Service-Key: $SERVICE_API_KEY" \
  -H "X-Forwarded-For: $MEU_IP" \
  -H "Content-Type: application/json" \
  -d '{"gemini_api_key": "AIzaNova..."}'

# Deletar tenant (soft delete)
curl -X DELETE http://localhost:8000/admin/tenants/<tenant-uuid> \
  -H "X-Service-Key: $SERVICE_API_KEY" \
  -H "X-Forwarded-For: $MEU_IP"
```

### Projects

```bash
# Criar um projeto (coleção de documentos)
curl -X POST http://localhost:8000/api/projects/ \
  -H "X-API-Key: sua_chave" \
  -H "Content-Type: application/json" \
  -d '{"name": "Documentos Jurídicos"}'

# Listar projetos
curl http://localhost:8000/api/projects/ \
  -H "X-API-Key: sua_chave"
```

### Documents

```bash
# Upload de documento (retorna 202 — processado async)
curl -X POST http://localhost:8000/api/documents/upload \
  -H "X-API-Key: sua_chave" \
  -F "file=@contrato.pdf" \
  -F "id_project=<project-uuid>"

# Verificar status do documento
curl http://localhost:8000/api/documents/<document-uuid> \
  -H "X-API-Key: sua_chave"

# Listar documentos (paginado, filtros opcionais)
curl "http://localhost:8000/api/documents?page=1&page_size=20&id_project=<project-uuid>" \
  -H "X-API-Key: sua_chave"

# Reprocessar um documento
curl -X POST http://localhost:8000/api/documents/<document-uuid>/reprocess \
  -H "X-API-Key: sua_chave"
```

**Status possíveis:** `pending` → `processing` → `done` | `error`

### Chat (RAG Query)

```bash
# Perguntar (resposta completa)
curl -X POST http://localhost:8000/api/chat/message \
  -H "X-API-Key: sua_chave" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Quais são as cláusulas de rescisão?",
    "id_project": "<project-uuid>"
  }'

# Continuar conversa em thread existente
curl -X POST http://localhost:8000/api/chat/message \
  -H "X-API-Key: sua_chave" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Resuma os pontos principais",
    "id_project": "<project-uuid>",
    "id_thread": "<thread-uuid>",
    "stream": false
  }'

# Resposta em streaming (SSE)
curl -X POST http://localhost:8000/api/chat/message \
  -H "X-API-Key: sua_chave" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Explique o prazo de vigência",
    "id_project": "<project-uuid>",
    "stream": true
  }'

# Listar threads de um projeto
curl "http://localhost:8000/api/chat/history?id_project=<project-uuid>" \
  -H "X-API-Key: sua_chave"

# Histórico de mensagens de uma thread
curl http://localhost:8000/api/chat/history/<thread-uuid> \
  -H "X-API-Key: sua_chave"
```

### Formatos suportados

| Formato | Parser | Detalhes |
|---------|--------|---------|
| `.pdf` | PyMuPDF + Tesseract | Auto-detecta páginas escaneadas |
| `.docx` | python-docx | Preserva hierarquia de headings |
| `.xlsx` | openpyxl | Uma sheet = uma unidade de documento |
| `.csv` | pandas | Unidades semânticas por linha |
| `.txt` | built-in | Ingestão direta |
| `.md` | LangChain splitter | Headers viram metadados de chunk |
| `.pptx` | python-pptx | Extração slide a slide |
| `.jpg`, `.png` | Tesseract OCR | Imagens via OCR |

---

## Variáveis de Ambiente

Crie `backend/.env` a partir de `backend/.env.example`:

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `SERVICE_API_KEY` | — | **Obrigatória.** Chave do caller admin (server-to-server) |
| `ENCRYPTION_KEY` | — | **Obrigatória.** Fernet key para criptografar chaves Gemini no banco |
| `ADMIN_ALLOWED_IPS` | — | **Obrigatória.** Lista JSON de IPs autorizados a chamar `/admin/*` |
| `DATABASE_URL` | `postgresql+asyncpg://fastdocs:fastdocs@postgres:5432/fastdocs` | URL do Postgres |
| `REDIS_URL` | `redis://redis:6379/0` | URL do Redis |
| `AZURE_STORAGE_CONNECTION_STRING` | string Azurite padrão | Connection string do Blob Storage |
| `AZURE_STORAGE_CONTAINER` | `documents` | Nome do container |
| `EMBEDDING_MODEL` | `models/gemini-embedding-001` | Modelo de embeddings |
| `EMBEDDING_DIM` | `768` | Dimensão dos vetores |
| `CHUNK_SIZE` | `1000` | Tamanho de cada chunk (chars) |
| `CHUNK_OVERLAP` | `150` | Overlap entre chunks |
| `RATE_LIMIT_INGEST` | `50` | Requests/min para ingestão por tenant |
| `RATE_LIMIT_QUERY` | `200` | Requests/min para queries por tenant |

---

## Estrutura do Projeto

```
fastdocs/
├── docker-compose.yml          # 7 serviços
├── azurite.Dockerfile          # Emulador Azure Blob
│
└── backend/
    ├── Dockerfile.api          # FastAPI + Alembic migrations
    ├── Dockerfile.worker       # Celery worker (inclui Tesseract/Poppler)
    ├── Dockerfile.relay        # Outbox relay
    ├── requirements.txt
    ├── .env.example
    │
    ├── alembic/
    │   └── versions/
    │       ├── 0001_initial_schema.py          # Schema completo + trigger NOTIFY
    │       ├── 0002_tenant_webhook_fields.py
    │       └── 0003_tenant_gemini_key.py       # gemini_api_key_encrypted
    │
    └── app/
        ├── main.py                     # FastAPI app + lifespan
        │
        ├── core/
        │   ├── config.py               # Pydantic Settings
        │   ├── database.py             # Engine SQLAlchemy async
        │   ├── celery_app.py           # Celery + beat_schedule
        │   ├── redis.py                # Conexão Redis
        │   ├── storage.py              # Inicialização Azure Blob
        │   ├── llm.py                  # Factory build_chat_llm(api_key)
        │   ├── crypto.py               # Fernet encrypt/decrypt
        │   └── graph/
        │       ├── state.py            # RagState (TypedDict)
        │       └── checkpointer.py     # AsyncRedisSaver lifecycle
        │
        ├── models/                     # SQLAlchemy ORM
        ├── schemas/                    # Pydantic DTOs
        │   └── admin.py                # DTOs do admin (TenantCreate, ApiKeyResponse…)
        ├── repositories/               # Data access (scoped por tenant_id)
        │
        ├── services/
        │   ├── admin_service.py        # CRUD tenants + emissão/revogação de keys
        │   ├── chat_service.py         # Thread, cache, histórico
        │   ├── document_service.py     # Upload, soft delete, reprocessing
        │   ├── project_service.py
        │   ├── rag_graph.py            # LangGraph (6 nós) — recebe gemini_api_key
        │   ├── ingestion_tasks.py      # Celery task principal
        │   ├── beat_tasks.py           # recover_stuck_documents
        │   ├── webhook_tasks.py        # Callbacks com HMAC-SHA256
        │   ├── outbox_relay.py         # LISTEN/NOTIFY → Celery
        │   └── extraction/
        │       ├── registry.py         # Formato → parser
        │       ├── chunker.py
        │       ├── cleaner.py
        │       ├── pdf.py, docx.py, xlsx.py, csv.py
        │       ├── txt.py, md.py, pptx.py, image.py
        │       └── tabular.py
        │
        ├── routers/
        │   ├── deps.py                 # Auth tenant + require_admin
        │   ├── admin.py                # /admin/* endpoints
        │   ├── chat.py
        │   ├── documents.py
        │   └── projects.py
        │
        └── clients/
            ├── blob_client.py
            ├── llm_client.py           # Embeddings batched + chat (api_key explícito)
            └── redis_client.py         # Cache + rate limit
```

---

## Decisões de Arquitetura

| Decisão | Alternativa Considerada | Motivação |
|----------|----------------------|-----------|
| **Gemini key por tenant** | Key global no `.env` | Isola custo por cliente; chave faturada para o tenant não para o serviço |
| **Fernet** para criptografia das keys | KMS (Vault/AWS) | Suficiente para MVP; master key no `.env`; KMS é upgrade natural |
| **IP allowlist + service key** para admin | OAuth / JWT | Caller é server-to-server conhecido; dupla camada sem infra extra |
| **pgvector** no Postgres | Qdrant, Chroma, Pinecone | Sem serviço extra; joins relacionais + vetoriais em uma query |
| **Outbox Pattern** com LISTEN/NOTIFY | Publish direto no Redis | Elimina dual-write SPOF; eventos nunca são perdidos |
| **Celery** para tasks | FastAPI BackgroundTasks | Tasks sobrevivem restarts; retry e monitoring nativos |
| **Tesseract** para OCR | Gemini Vision API | Custo zero; roda local; Vision como fallback futuro |
| **Azure Blob** (Azurite local) | MinIO / S3 | Deploy alvo é Azure; Azurite oferece paridade local |
| **Cache exato** de queries | Cache semântico | Mais simples; evita falsos positivos em v1 |
| **Sliding window** rate limiting | Token bucket | Mais preciso; granularidade por tenant com Redis sorted sets |

---

## Segurança

- **Admin**: dupla camada — `X-Service-Key` (constant-time compare) + IP allowlist. Ambas obrigatórias
- **API Keys de tenant**: apenas o hash SHA-256 é armazenado — plaintext exibido uma única vez na criação
- **Chaves Gemini**: armazenadas criptografadas com Fernet; descriptografadas em memória apenas durante a request/task
- **Isolamento de tenant**: toda query inclui `WHERE tenant_id = ?` — aplicado na camada de repositório
- **Webhook signing**: header `X-FastDocs-Signature: sha256=<hmac>` para verificação de callbacks
- **Sem segredos no repo**: `.env` está no `.gitignore`; `.env.example` fornece o template

---

## O que está implementado

- [x] **Admin API** — CRUD de tenants, emissão/revogação de API Keys, rotação de chave Gemini
- [x] **Auth em camada dupla** — `X-Service-Key` + IP allowlist para admin; `X-API-Key` SHA-256 para tenants
- [x] **Gemini key por tenant** — criptografada com Fernet, validada contra a API do Google no cadastro
- [x] Auth multi-tenant com API Keys (hash SHA-256, isolamento por tenant)
- [x] Pipeline de ingestão (PDF, DOCX, XLSX, CSV, TXT, MD, PPTX, imagens)
- [x] Auto-detecção de PDF escaneado + OCR Tesseract
- [x] Outbox Pattern com Postgres LISTEN/NOTIFY + fallback polling
- [x] Agente LangGraph RAG com 6 nós e retry automático
- [x] Chat com histórico em threads e estado persistido (LangGraph checkpointer Redis)
- [x] Streaming SSE (`stream: true`)
- [x] Rate limiting sliding window (Redis sorted sets, por tenant/endpoint)
- [x] Cache de queries (TTL 30min, invalidação automática ao ingerir documento)
- [x] Webhooks (assinatura HMAC-SHA256, 3 retentativas com backoff exponencial)
- [x] Celery Beat — `recover_stuck_documents` a cada 60s
- [x] Docker Compose (7 serviços com healthchecks e volumes persistentes)
- [x] Migrations Alembic (schema inicial + webhook + gemini key)
- [x] Pipeline de limpeza de texto (normalização de encoding, dedup)
- [x] Reprocessamento de documentos (`POST /documents/{id}/reprocess`)
- [x] Suíte de testes (pytest — 15 arquivos)

---

## Roadmap

- [ ] Logging estruturado com correlation IDs por request
- [ ] CI/CD com GitHub Actions
- [ ] Observabilidade (endpoint de métricas, Prometheus/Grafana)

---

## Licença

Este projeto é para fins de portfólio e aprendizado.

---

<p align="center">
  Desenvolvido por <a href="https://github.com/TiagoAReiz">Tiago Reiz</a>
</p>
