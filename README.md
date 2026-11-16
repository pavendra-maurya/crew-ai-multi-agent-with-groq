#  Multi-Agent System (CrewAI + Groq + MCP + A2A + FastAPI)

A production-ready hierarchical multi-agent incident triage and diagnostics platform combining **CrewAI**, **Groq LPU inference**, **Model Context Protocol (MCP)**, **Agent-to-Agent (A2A) Protocol**, and **FastAPI**.

---

## System Architecture & Hierarchy

This system decouples API ingestion, multi-agent orchestration, private local tooling, and external partner agents across four architectural tiers:

```text
                                ┌─────────────────────────────────────────┐
                                │          CLIENT / API CONSUMER          │
                                │ POST /api/v1/triage | GET /stream/{id}  │
                                └────────────────────┬────────────────────┘
                                                     │ HTTP / SSE
                                                     ▼
┌───────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                 TIER 1: FASTAPI GATEWAY (Port 8000)                               │
│   • Async Request Ingestion (202 Accepted)   • Threadpool Execution   • Live SSE Event Streamer   │
└────────────────────────────────────────────────────┬──────────────────────────────────────────────┘
                                                     │
                                                     ▼
┌───────────────────────────────────────────────────────────────────────────────────────────────────┐
│                        TIER 2: INTERNAL CREWAI HIERARCHY (Groq LPU Engine)                        │
│                                                                                                   │
│                          ┌───────────────────────────────────────────────────┐                    │
│                          │      ROOT: INTERNAL COORDINATOR AGENT (Agent 1)   │                    │
│                          │  • Model: Groq (openai/gpt-oss-120b)              │                    │
│                          │  • Role: Decomposes goals, delegates, validates,  │                    │
│                          │    and synthesizes the final structured output.   │                    │
│                          └─────────┬───────────────────────────────┬─────────┘                    │
│                                    │                               │                              │
│          Internal Delegation       │                               │ External A2A Delegation      │
│       (CrewAI Co-worker Tools)     │                               │ (HTTP JSON-RPC + BearerAuth) │
│                                    ▼                               │                              │
│  ┌───────────────────────────────────────────────────┐             │                              │
│  │   WORKER: INTERNAL TELEMETRY SPECIALIST (Agent 2) │             │                              │
│  │  • Model: Groq (openai/gpt-oss-120b)              │             │                              │
│  │  • Role: Queries private infrastructure logs,     │             │                              │
│  │    deployments, and runbooks.                     │             │                              │
│  └─────────────────────────┬─────────────────────────┘             │                              │
└────────────────────────────┼───────────────────────────────────────┼──────────────────────────────┘
                             │                                       │
              MCP Protocol   │ (Local Stdio)                         │ A2A Protocol
              (tools/call)   │                                       │ (GET /.well-known/agent-card.json)
                             ▼                                       ▼
┌──────────────────────────────────────────┐   ┌────────────────────────────────────────────────────┐
│    TIER 3A: INTERNAL LOCAL MCP SERVER    │   │   TIER 3B: EXTERNAL A2A AGENT SERVER (Port 9000)   │
│           (internal_mcp.py)              │   │        (Remote Opaque Peer - Agent 3)              │
│                                          │   │                                                    │
│  • fetch_service_logs()                  │   │  • Advertises Agent Card & Skills                  │
│  • get_recent_deployments()              │   │  • Runs independent Groq Agent                     │
│  • query_internal_runbook()              │   │  • Connects to Remote MCP over HTTP/SSE            │
└──────────────────────────────────────────┘   └─────────────────────────┬──────────────────────────┘
                                                                         │
                                                          MCP Protocol   │ (Streamable HTTP)
                                                          (tools/list &  │
                                                           tools/call)   ▼
                                               ┌────────────────────────────────────────────────────┐
                                               │      TIER 4: REMOTE PUBLIC/PARTNER MCP SERVER      │
                                               │   https://mcpplaygroundonline.com/                 │
                                               │   mcp-complex-server                               │
                                               └────────────────────────────────────────────────────┘
```

### Architectural Roles & Protocol Boundaries

| Tier | Component | Protocol / Transport | Responsibility |
| :--- | :--- | :--- | :--- |
| **Tier 1** | **FastAPI Gateway** (`app/main.py`) | REST (`POST`/`GET`) + Server-Sent Events (`SSE`) | Validates `X-API-Key`, assigns a unique `job_id`, offloads blocking CrewAI execution to a worker threadpool (`202 Accepted`), and streams live agent steps. |
| **Tier 2 (Root)** | **Internal Coordinator Agent** *(Agent 1)* | CrewAI Delegation + `A2AClientConfig` | **Root Orchestrator.** Holds zero direct MCP tools. Splits the alert into internal vs. external workstreams, delegates to Agent 2 and Agent 3, cross-verifies answers, and outputs a validated `StructuredRCAReport`. |
| **Tier 2 (Worker)** | **Internal Telemetry Specialist** *(Agent 2)* | CrewAI Co-worker Q&A + `MCPServerStdio` | **Private Evidence Gatherer.** Connects exclusively to the local stdio MCP server to inspect service logs, deployment history, and internal runbooks. |
| **Tier 3A** | **Internal Local MCP Server** (`app/internal_mcp.py`) | JSON-RPC over `stdin`/`stdout` | Isolates internal data access behind schema-validated MCP tools (`fetch_service_logs`, `get_recent_deployments`, `query_internal_runbook`). |
| **Tier 3B (Remote)** | **External Specialist Agent** *(Agent 3)* | A2A (`/.well-known/agent-card.json` & `/a2a`) | **Opaque Remote Peer.** Runs on port `9000`, authenticates callers via `BearerTokenAuth`, and executes an independent Groq agent backed by a remote HTTP MCP server. |
| **Tier 4** | **Remote Complex MCP Server** | Streamable HTTP / SSE MCP | External tool server (`https://mcpplaygroundonline.com/mcp-complex-server`) providing multi-step external tools to Agent 3 without exposing them to the internal network. |

### End-to-End Request Lifecycle

1. **Async Ingestion:** Client sends `POST /api/v1/triage`; FastAPI returns `202 Accepted` with `job_id` and `stream_url`.
2. **Top-Down Decomposition:** The **Internal Coordinator Agent** inspects the alert and delegates internal log/deployment checks to the **Internal Telemetry Specialist**.
3. **Local MCP Execution:** Agent 2 invokes `fetch_service_logs`, `get_recent_deployments`, and `query_internal_runbook` over local `stdio` MCP and returns extracted artifacts (IPs, package versions, deploy IDs) to the Coordinator.
4. **Cross-Boundary A2A Delegation:** The Coordinator discovers Agent 3 via `/.well-known/agent-card.json` and sends an authenticated A2A JSON-RPC task (`POST /a2a`) containing the uncovered artifacts.
5. **Remote MCP Execution:** Inside `external-a2a-agent`, Agent 3 connects via `MCPServerHTTP` to `https://mcpplaygroundonline.com/mcp-complex-server`, runs relevant tools, and returns an A2A `Artifact`.
6. **Bottom-Up Synthesis:** The Coordinator reconciles internal MCP findings with external A2A intelligence and publishes the final Pydantic-validated `StructuredRCAReport`.

---

## Project Directory Structure

```text
prod-hierarchical-agentic-system/
├── README.md                           # Architecture overview & setup instructions
├── .env.example                        # Environment configuration template
├── docker-compose.yml                  # Multi-service orchestration with healthchecks
│
├── external_a2a_agent/                 # SERVICE A: Remote A2A Server (Port 9000)
│   ├── Dockerfile
│   ├── requirements.txt
│   └── server.py                       # Agent Card discovery + /a2a endpoint + Remote MCP client
│
└── internal_crew_service/              # SERVICE B: FastAPI + CrewAI + Local MCP (Port 8000)
    ├── Dockerfile
    ├── requirements.txt
    └── app/
        ├── __init__.py
        ├── config.py                   # Pydantic Settings (.env loader)
        ├── schemas.py                  # Request, JobStatus & StructuredRCAReport schemas
        ├── internal_mcp.py             # Local FastMCP server (stdio)
        ├── event_bus.py                # Thread-safe Pub/Sub for live SSE streaming
        ├── crew_hierarchy.py           # Root Coordinator Agent + Internal Telemetry Worker
        └── main.py                     # FastAPI async endpoints (/triage, /status, /stream)
```

---

## Quick Start (Docker Compose)

1. **Configure Environment:**
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and set your active Groq API key and model:
   ```env
   GROQ_API_KEY=gsk_your_actual_groq_api_key_here
   GROQ_MODEL=openai/gpt-oss-120b
   ```

2. **Build and Start Both Services:**
   ```bash
   docker compose up --build
   ```

---

## Quick Start (Local Development)

### Terminal 1: Start External A2A Agent (Port 9000)
```bash
cd external_a2a_agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port 9000 --reload
```

### Terminal 2: Start Internal CrewAI + MCP + FastAPI Service (Port 8000)
```bash
cd internal_crew_service
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## API Reference & Testing

### 1. Health Checks
* **Internal Service:** `GET http://localhost:8000/health`
* **External A2A Agent:** `GET http://localhost:9000/health`
* **A2A Agent Card Discovery:** `GET http://localhost:9000/.well-known/agent-card.json`

### 2. Submit a Triage Job
```bash
curl -X POST "http://localhost:8000/api/v1/triage" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: prod-internal-secret-key-9988" \
  -d '{
    "service_name": "auth-service",
    "alert_description": "Anomalous outbound traffic from auth-service to 185.220.101.42 after Deploy #418. Run full internal telemetry and external complex diagnostics."
  }'
```

### 3. Stream Live Agent-to-Agent Events (SSE)
Replace `<JOB_ID>` with the `job_id` returned from step 2:
```bash
curl -N -H "X-API-Key: prod-internal-secret-key-9988" \
  "http://localhost:8000/api/v1/triage/<JOB_ID>/stream"
```

### 4. Retrieve Final Structured RCA Report
```bash
curl -H "X-API-Key: prod-internal-secret-key-9988" \
  "http://localhost:8000/api/v1/triage/<JOB_ID>"
```ß