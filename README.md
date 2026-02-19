# Aisthetic Catalog

AI-powered fashion e-commerce backend with a conversational stylist agent. Retailers embed this service to give shoppers a knowledgeable, personalised fashion advisor — one that learns preferences over time, handles natural-language product search, builds occasion outfits, and manages shortlists.

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Local setup (Python)](#local-setup-python)
  - [Docker Compose](#docker-compose)
- [Database initialisation](#database-initialisation)
- [Scripts](#scripts)
- [API Reference](#api-reference)
- [Environment Variables](#environment-variables)
- [Switching LLM Providers](#switching-llm-providers)
- [Contributing](#contributing)

---

## Features

- **Conversational stylist** — LangGraph agent handles greetings, product discovery, occasion styling, follow-ups, and shortlist management in a single chat endpoint
- **Semantic + filter search** — OpenSearch kNN + hard filters (category, color, price, gender, stock)
- **Pluggable LLM backend** — swap between OpenAI and Anthropic Claude via a single env var; no code changes
- **Persistent user memory** — mem0 stores cross-session learnings (liked colors, fit preferences, size notes)
- **Trend-aware responses** — Tavily web search injects current fashion context into recommendations
- **Multi-tenant** — each merchant gets an isolated database; the control plane stores connection configs
- **CSV ingestion pipeline** — upload → stage → process → retry, with per-row status tracking
- **Image search** — CLIP embeddings via Replicate for visual similarity search

---

## Architecture

```
┌──────────────────────────────────────────────────┐
│                   FastAPI app                    │
│  /health   /catalog/*   /stylist/chat            │
└───────────┬──────────────────┬───────────────────┘
            │                  │
   ┌────────▼────────┐  ┌──────▼────────────────────┐
   │ Catalog Service │  │    Stylist Agent (LangGraph)│
   │  - CSV ingest   │  │                            │
   │  - Search       │  │  initialize                │
   │  - Product CRUD │  │    ↓                       │
   └────────┬────────┘  │  [intent routing]          │
            │           │    ├─ product_search        │
            │           │    ├─ occasion_styling      │
   ┌────────▼────────┐  │    ├─ follow_up             │
   │   OpenSearch    │  │    ├─ preference_collection │
   │  (kNN + filter) │  │    ├─ profile_update        │
   └─────────────────┘  │    ├─ shortlist             │
                        │    └─ small_talk            │
   ┌─────────────────┐  │    ↓                       │
   │   PostgreSQL    │  │  trend_enrichment           │
   │  Control plane  │  │    ↓                       │
   │  Tenant DBs     │  │  generate_response         │
   └─────────────────┘  │    ↓                       │
                        │  finalize                  │
   ┌─────────────────┐  └────────────────────────────┘
   │     Redis       │
   │  Chat sessions  │
   │  Shortlists     │
   └─────────────────┘
```

### Agent flow

The stylist agent is a LangGraph state machine. Every chat turn runs through:

1. **initialize** — load user profile, preferences, memories, detect intent
2. **intent routing** — conditional edge dispatches to the right node
3. **product_search** (if needed) — semantic + filter search, retries up to 2×
4. **trend_enrichment** — optional Tavily web search for trend context
5. **generate_response** — LLM composes final answer + product recommendations
6. **finalize** — persist chat turn, return `StylistResponse`

### Multi-tenant model

- **Control-plane DB** (shared) — merchant registry and per-merchant DB connection strings
- **Tenant DBs** (per merchant) — product catalog, user profiles, upload rows
- `get_tenant_sessionmaker(merchant_id)` resolves and caches connections at runtime

---

## Tech Stack

| Layer | Technology |
|---|---|
| Web framework | FastAPI + Uvicorn |
| Agent orchestration | LangGraph |
| LLM (default) | OpenAI `gpt-4.1-mini` |
| LLM (alternative) | Anthropic Claude (e.g. `claude-sonnet-4-6`) |
| Text embeddings | OpenAI `text-embedding-3-small` |
| Image embeddings | Replicate CLIP |
| Search | OpenSearch 2.13 |
| Database | PostgreSQL 15 + SQLAlchemy (async) |
| Cache / sessions | Redis 7 |
| Persistent memory | mem0 |
| Web search | Tavily |
| Validation | Pydantic v2 |
| Runtime | Python 3.11 |

---

## Project Structure

```
.
├── app/
│   ├── api/
│   │   ├── catalog_routes.py      # Product ingestion + search endpoints
│   │   └── stylist_routes.py      # Chat endpoint
│   ├── catalog/
│   │   ├── models_tenant.py       # Product, ProductImage, ProductVariant, CsvUploadRow
│   │   ├── search.py              # OpenSearch query builder
│   │   ├── embeddings.py          # Text + image embedding helpers
│   │   ├── ingestion.py           # CSV pipeline
│   │   ├── indexing_service.py    # Index management
│   │   └── opensearch_client.py
│   ├── stylist/
│   │   ├── graph.py               # LangGraph workflow definition
│   │   ├── state.py               # AgentState TypedDict
│   │   ├── agent.py               # Agent entrypoint
│   │   ├── intents.py             # StylistIntent enum (10 intents)
│   │   ├── models_user.py         # UserProfile, UserPreferences
│   │   ├── persona.py             # Profile/persona helpers
│   │   ├── query_completion.py    # LLM-powered query normaliser
│   │   ├── intent_detection.py    # LLM intent classifier
│   │   ├── session_store.py       # Redis chat sessions
│   │   ├── memory_service.py      # mem0 integration
│   │   ├── shortlist_service.py   # Redis shortlist CRUD
│   │   ├── web_search_service.py  # Tavily integration
│   │   └── nodes/                 # One file per LangGraph node
│   │       ├── initialize.py
│   │       ├── product_search.py
│   │       ├── generate_response.py
│   │       ├── preference_collection.py
│   │       ├── profile_update.py
│   │       ├── occasion_styling.py
│   │       ├── follow_up.py
│   │       ├── shortlist.py
│   │       ├── small_talk.py
│   │       ├── trend_enrichment.py
│   │       ├── finalize.py
│   │       └── helpers.py
│   ├── core/
│   │   ├── config.py              # Pydantic settings
│   │   ├── tenant_db.py           # Multi-tenant DB connection resolver
│   │   ├── db_control.py          # Control-plane DB setup
│   │   └── redis.py               # Redis singleton
│   ├── control/
│   │   └── models_control.py      # Merchant, MerchantDBConnection
│   ├── llm/
│   │   └── client.py              # chat_complete() — provider-agnostic
│   ├── main.py
│   └── logger.py
├── scripts/
│   ├── reset_db.py                # Drop + recreate + seed merchant
│   ├── sync_schema.py             # Idempotent table creation
│   ├── create_user.py             # Create a test user
│   ├── reset_ingest.py            # Clear ingestion state
│   └── delete_opensearch_index.py
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── .env
```

---

## Getting Started

### Prerequisites

- Python 3.11+
- PostgreSQL 15
- Redis 7
- OpenSearch 2.13
- An OpenAI API key (for embeddings; also for the stylist if using the OpenAI provider)

### Local setup (Python)

```bash
# 1. Clone and enter the repo
git clone <repo-url>
cd aisthetic-catalog

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create your .env (see Environment Variables below)
cp .env .env.bak   # back up existing if present
# Edit .env with your keys and DSNs

# 5. Initialise the database
python -m scripts.reset_db
# Note the merchant_id printed at the end

# 6. Create a test user
python -m scripts.create_user --merchant-id <merchant_id> --external-user-id user_001

# 7. Start the server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API is now available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

### Docker Compose

All four services (app, PostgreSQL, Redis, OpenSearch) are defined in `docker-compose.yml`.

```bash
# 1. Set required env vars (app service inherits from shell / .env)
export TEXT_EMBEDDING_API_KEY=sk-proj-...
export REPLICATE_API_TOKEN=r8_...

# 2. Build and start
docker compose up -d --build

# 3. Initialise the database (first run only)
docker exec aisthetic-app python -m scripts.reset_db

# 4. Create a test user
docker exec aisthetic-app python -m scripts.create_user \
  --merchant-id <merchant_id> --external-user-id user_001

# 5. Tail logs
docker compose logs -f app
```

**Service ports:**

| Service | Port |
|---|---|
| API | 8000 |
| PostgreSQL | 5432 |
| Redis | 6379 |
| OpenSearch | 9200 |

---

## Database initialisation

The app uses two logical databases:

| Database | Purpose |
|---|---|
| `aisthetic_control` | Merchant registry + per-merchant DB connection configs |
| Per-merchant DB | Product catalog, user profiles, upload rows |

On first run, `reset_db.py` creates all tables and inserts a demo merchant. For subsequent deploys (adding tables without dropping), use `sync_schema.py`:

```bash
python -m scripts.sync_schema --merchant-id <uuid>
```

---

## Scripts

| Script | Usage | Description |
|---|---|---|
| `reset_db` | `python -m scripts.reset_db` | Drop all tables, recreate schema, seed a demo merchant. Prints the new `merchant_id`. |
| `sync_schema` | `python -m scripts.sync_schema --merchant-id <uuid>` | Create any missing tables without dropping existing data. Safe for production migrations. |
| `create_user` | `python -m scripts.create_user --merchant-id <uuid> --external-user-id <id>` | Create a UserProfile + UserPreferences for a test user. |
| `reset_ingest` | `python -m scripts.reset_ingest` | Reset all CSV upload rows back to pending state. |
| `delete_opensearch_index` | `python -m scripts.delete_opensearch_index` | Delete all OpenSearch indexes (destructive). |

---

## API Reference

All routes are prefixed with `/merchants/{merchant_id}`.

### Health

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Returns `{"status": "ok"}` |

### Catalog

| Method | Path | Description |
|---|---|---|
| `POST` | `/merchants/{merchant_id}/catalog/ingest/csv` | Upload a CSV file to stage products. Returns `batch_id`. |
| `POST` | `/merchants/{merchant_id}/catalog/ingest/process` | Claim pending rows and queue them for processing. Returns count. |
| `GET` | `/merchants/{merchant_id}/catalog/ingest/batch/{batch_id}/status` | Fetch batch status: pending / processing / processed / failed counts. |
| `POST` | `/merchants/{merchant_id}/catalog/ingest/retry-failed` | Requeue failed rows for reprocessing. |
| `POST` | `/merchants/{merchant_id}/catalog/search` | Semantic + filter product search. Accepts `query_text`, `category`, `color`, `gender`, `price_min/max`, `excluded_ids`. |
| `POST` | `/merchants/{merchant_id}/catalog/search_by_image` | CLIP-based image similarity search. |
| `GET` | `/merchants/{merchant_id}/catalog/products/{product_id}` | Fetch full product details (images, variants, metadata). |

### Stylist

| Method | Path | Description |
|---|---|---|
| `POST` | `/merchants/{merchant_id}/stylist/chat` | Conversational chat. Request body: `external_user_id`, `message`, optional `chat_session_id`, optional `occasion`. Response: `answer`, `recommended_products`, `shortlisted_product_ids`, `quick_replies`, `session_id`, `intent`. |

**Example chat request:**

```bash
curl -X POST http://localhost:8000/merchants/<merchant_id>/stylist/chat \
  -H "Content-Type: application/json" \
  -d '{
    "external_user_id": "user_001",
    "message": "I need something casual for a beach holiday"
  }'
```

---

## Environment Variables

All variables are loaded from `.env` via `pydantic-settings`. A missing required key will raise a `ValidationError` at startup.

### Database

| Variable | Default | Required | Description |
|---|---|---|---|
| `CONTROL_DB_DSN` | `postgresql+psycopg2://airbender@localhost:5432/aisthetic_control` | Yes | SQLAlchemy DSN for the control-plane PostgreSQL database |

### OpenSearch

| Variable | Default | Required | Description |
|---|---|---|---|
| `OPENSEARCH_HOST` | `http://localhost:9200` | Yes | OpenSearch cluster base URL |
| `OPENSEARCH_USER` | _(none)_ | No | Username for auth-enabled clusters |
| `OPENSEARCH_PASSWORD` | _(none)_ | No | Password for auth-enabled clusters |

### Embeddings (OpenAI)

Used exclusively by `app/catalog/embeddings.py`. Independent of the stylist LLM provider.

| Variable | Default | Required | Description |
|---|---|---|---|
| `TEXT_EMBEDDING_API_KEY` | _(empty)_ | Yes | OpenAI API key for text embeddings. Also used as the OpenAI key for the stylist when `STYLIST_PROVIDER=openai`. |
| `TEXT_EMBEDDING_MODEL_NAME` | `text-embedding-3-small` | No | OpenAI embedding model |

### Image Embeddings (Replicate)

| Variable | Default | Required | Description |
|---|---|---|---|
| `REPLICATE_API_TOKEN` | _(empty)_ | No | Replicate API token for CLIP image embeddings |
| `REPLICATE_IMAGE_EMBEDDING_MODEL` | `openai/clip` | No | Replicate model identifier |

### Stylist LLM

| Variable | Default | Required | Description |
|---|---|---|---|
| `STYLIST_PROVIDER` | `openai` | No | LLM provider for the stylist agent. Accepted values: `openai`, `anthropic` |
| `STYLIST_MODEL_NAME` | `gpt-4.1-mini` | No | Model name passed to the active provider |
| `ANTHROPIC_API_KEY` | _(empty)_ | Conditional | Required when `STYLIST_PROVIDER=anthropic` |

### Catalog

| Variable | Default | Required | Description |
|---|---|---|---|
| `INCLUDE_OUT_OF_STOCK` | `False` | No | Include out-of-stock products in search results |

### Redis / Chat Sessions

| Variable | Default | Required | Description |
|---|---|---|---|
| `REDIS_URL` | `redis://localhost:6379/0` | Yes | Redis connection URL |
| `CHAT_SESSION_TTL_SECONDS` | `21600` | No | Session TTL (default 6 hours) |
| `CHAT_SESSION_STORAGE_TURNS` | `40` | No | Max turns stored per session |
| `CHAT_SESSION_SUMMARY_PRODUCT_LIMIT` | `6` | No | Max products included in session context summaries |
| `CHAT_SESSION_CONTEXT_WINDOW` | `20` | No | Recent turns passed to the LLM per request |
| `SHORTLIST_MAX_SIZE` | `10` | No | Max products a user can shortlist per session |

### Mem0 (Persistent Memory)

| Variable | Default | Required | Description |
|---|---|---|---|
| `MEM0_API_KEY` | _(empty)_ | No | Mem0 API key for cross-session user memory |
| `MEM0_ENABLED` | `True` | No | Toggle mem0 memory retrieval on/off |

### CORS

| Variable | Default | Required | Description |
|---|---|---|---|
| `CORS_ORIGINS` | _(empty)_ | No | Comma-separated list of additional allowed origins. `http://localhost:5173` and `http://127.0.0.1:5173` are always allowed. |

### Tavily (Trend Search)

| Variable | Default | Required | Description |
|---|---|---|---|
| `TAVILY_API_KEY` | _(empty)_ | No | Tavily API key |
| `TAVILY_SEARCH_ENABLED` | `True` | No | Enable/disable Tavily trend enrichment |

---

## Switching LLM Providers

The stylist supports OpenAI and Anthropic Claude interchangeably. The switch is controlled entirely by environment variables — no code changes required.

**OpenAI (default):**
```dotenv
STYLIST_PROVIDER=openai
STYLIST_MODEL_NAME=gpt-4.1-mini
TEXT_EMBEDDING_API_KEY=sk-proj-...
```

**Anthropic Claude:**
```dotenv
STYLIST_PROVIDER=anthropic
STYLIST_MODEL_NAME=claude-sonnet-4-6
ANTHROPIC_API_KEY=sk-ant-...
```

> Text and image embeddings always use OpenAI and Replicate respectively — they are not affected by `STYLIST_PROVIDER`.

All prompts in the codebase already include explicit JSON output instructions, so Claude follows them without needing OpenAI's `response_format` parameter.

---

## Contributing

1. Fork the repository and create a feature branch
2. Install deps: `pip install -r requirements.txt`
3. Make your changes, keeping the existing code style
4. Test locally against a full stack (PostgreSQL + Redis + OpenSearch)
5. Open a pull request with a clear description of the change
