import os
import uuid
import logging
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from crewai import Agent, Task, Crew, LLM
from crewai.mcp import MCPServerHTTP

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [EXTERNAL-A2A] %(levelname)s: %(message)s",
)
logger = logging.getLogger("external_a2a")

app = FastAPI(
    title="External Specialist A2A Agent (Backed by Remote Complex MCP)",
    version="2.0.0",
)

EXPECTED_TOKEN = os.getenv("A2A_BEARER_TOKEN", "a2a-shared-bearer-token-7766")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "groq/llama-3.3-70b-versatile")
REMOTE_MCP_URL = os.getenv(
    "REMOTE_MCP_URL",
    "https://mcpplaygroundonline.com/mcp-complex-server",
)


# --- A2A Protocol Models ---
class AgentSkill(BaseModel):
    id: str
    name: str
    description: str
    tags: List[str]


class AgentCard(BaseModel):
    name: str
    description: str
    url: str
    version: str
    protocolVersion: str = "0.2.5"
    capabilities: Dict[str, Any]
    defaultInputModes: List[str] = ["text/plain"]
    defaultOutputModes: List[str] = ["text/plain"]
    skills: List[AgentSkill]


def verify_bearer_token(authorization: Optional[str]) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization.split(" ", 1)[1].strip()
    if token != EXPECTED_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid A2A Bearer token")


@app.get("/health")
async def health():
    return {"status": "healthy", "remote_mcp": REMOTE_MCP_URL}


# 1. A2A Capability Discovery Endpoint
@app.get("/.well-known/agent-card.json", response_model=AgentCard)
async def get_agent_card(request: Request):
    base_url = str(request.base_url).rstrip("/")
    return AgentCard(
        name="External Complex-Server Specialist Agent",
        description=(
            "Independent external A2A specialist connected to mcpplaygroundonline.com/mcp-complex-server. "
            "Performs complex external tool execution, multi-step diagnostics, and threat/data verification."
        ),
        url=f"{base_url}/a2a",
        version="2.0.0",
        capabilities={"streaming": False, "pushNotifications": False},
        skills=[
            AgentSkill(
                id="remote-mcp-complex-execution",
                name="External Complex MCP Tool Execution",
                description=(
                    "Discovers and executes tools on the remote MCP complex server to enrich internal "
                    "investigations with external calculations, lookups, and verifications."
                ),
                tags=["a2a", "remote-mcp", "external-specialist", "diagnostics"],
            )
        ],
    )


def run_external_mcp_specialist(user_query: str) -> str:
    """Executes an independent CrewAI + Groq agent wired to the remote MCP complex server."""
    if not GROQ_API_KEY:
        return (
            "EXTERNAL AGENT NOTICE: GROQ_API_KEY is not set on the external A2A server. "
            f"Received query safely: {user_query[:200]}"
        )

    llm = LLM(
        model=GROQ_MODEL,
        provider="openai",
        base_url="https://api.groq.com/openai/v1",
        api_key=GROQ_API_KEY,
        temperature=0.1,
        max_retries=3,
    )

    remote_mcp = MCPServerHTTP(
        url=REMOTE_MCP_URL,
        streamable=True,
        cache_tools_list=True,
    )

    external_specialist = Agent(
        role="External Complex-Server Specialist",
        goal="Inspect and execute relevant tools on the remote MCP complex server to fulfill the delegated A2A request.",
        backstory=(
            "You are an autonomous external specialist agent. You connect to the remote MCP complex server, "
            "examine its available tools, invoke the ones relevant to the incoming request with valid parameters, "
            "and synthesize a clear, factual report for the calling coordinator agent."
        ),
        mcps=[remote_mcp],
        llm=llm,
        max_iter=5,
        verbose=True,
    )

    task = Task(
        description=(
            "An internal Coordinator Agent delegated the following request over the A2A protocol:\n\n"
            f"'{user_query}'\n\n"
            "1. Inspect the tools available on your connected remote MCP server.\n"
            "2. Execute any tools relevant to evaluating or enriching this request.\n"
            "3. Return a structured, factual summary of the tools called, their outputs, and your external verdict."
        ),
        expected_output="A concise, evidence-backed summary of remote MCP tool outputs and external conclusions.",
        agent=external_specialist,
    )

    crew = Crew(
        agents=[external_specialist],
        tasks=[task],
        verbose=True,
    )

    try:
        result = crew.kickoff()
        return str(result)
    except Exception as exc:
        logger.exception("Error invoking remote MCP complex server inside External A2A Agent")
        return (
            f"External A2A Agent connected and evaluated request, but encountered a remote MCP transport "
            f"or execution error ({type(exc).__name__}: {exc}). Fallback assessment: treat unknown external "
            f"endpoints and newly introduced dependencies as untrusted until isolated."
        )


def _extract_query_text(params: Dict[str, Any]) -> str:
    message = params.get("message", {})
    parts = message.get("parts", [])
    extracted = []
    for part in parts:
        if isinstance(part, dict):
            if "text" in part:
                extracted.append(str(part["text"]))
        elif isinstance(part, str):
            extracted.append(part)
    text = " ".join(extracted).strip()
    return text if text else str(params)


# 2. A2A JSON-RPC 2.0 Task Execution Endpoint
@app.post("/a2a")
async def handle_a2a_rpc(request: Request, authorization: Optional[str] = Header(None)):
    verify_bearer_token(authorization)
    payload = await request.json()

    rpc_id = payload.get("id", str(uuid.uuid4()))
    method = payload.get("method", "message/send")
    params = payload.get("params", {})

    logger.info(f"Inbound A2A RPC method='{method}' id='{rpc_id}'")

    user_query = _extract_query_text(params)
    verdict = await run_in_threadpool(run_external_mcp_specialist, user_query)

    message = params.get("message", {})
    task_id = params.get("id", f"task-{uuid.uuid4().hex[:8]}")
    context_id = message.get("contextId", f"ctx-{uuid.uuid4().hex[:8]}")

    return {
        "jsonrpc": "2.0",
        "id": rpc_id,
        "result": {
            "id": task_id,
            "contextId": context_id,
            "status": {
                "state": "completed",
                "message": {
                    "role": "agent",
                    "parts": [{"kind": "text", "text": verdict}],
                },
            },
            "artifacts": [
                {
                    "artifactId": f"art-{uuid.uuid4().hex[:6]}",
                    "name": "external_remote_mcp_report",
                    "parts": [{"kind": "text", "text": verdict}],
                }
            ],
        },
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=9000, reload=True)
