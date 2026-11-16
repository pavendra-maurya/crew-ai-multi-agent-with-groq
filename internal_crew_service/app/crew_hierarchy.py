import sys
import logging
from pathlib import Path
from crewai import Agent, Task, Crew, Process, LLM
from crewai.a2a import A2AClientConfig
from crewai.a2a.auth import BearerTokenAuth
from crewai.mcp import MCPServerStdio
from crewai.mcp.filters import create_static_tool_filter

from .config import settings
from .event_bus import job_manager
from .schemas import JobStatus, StructuredRCAReport


logger = logging.getLogger("crew_hierarchy")
MCP_SCRIPT_PATH = str(Path(__file__).parent / "internal_mcp.py")


def execute_hierarchical_crew(job_id: str, service_name: str, alert_description: str) -> None:
    """
    Executes the 3-agent hierarchy:
      - Root: Internal Coordinator Agent (Agent 1) -> delegates internally & externally via A2A
      - Worker: Internal Telemetry Specialist (Agent 2) -> uses Local Stdio MCP
      - Remote Peer: External Specialist Agent (Agent 3) -> reached via A2A Protocol
    """
    try:
        job_manager.update_status(job_id, JobStatus.RUNNING)
        job_manager.publish_event(
            job_id,
            "lifecycle",
            "System",
            "Bootstrapping Groq LLM, Local Stdio MCP Server, and External A2A Client...",
        )

        # 1. Groq Inference Engine
        # 1. Groq Inference Engine
        groq_llm = LLM(
            model=settings.groq_model,
            provider="openai",
            base_url="https://api.groq.com/openai/v1",
            api_key=settings.groq_api_key,
            temperature=0.1,
            max_retries=3,
        )
        # 2. Local Stdio MCP Server (Least-Privilege: assigned ONLY to Internal Worker Agent 2)
        local_mcp = MCPServerStdio(
            command=sys.executable,
            args=[MCP_SCRIPT_PATH],
            tool_filter=create_static_tool_filter(
                allowed_tool_names=[
                    "fetch_service_logs",
                    "get_recent_deployments",
                    "query_internal_runbook",
                ]
            ),
        )

        # 3. External A2A Protocol Client (Assigned ONLY to Root Coordinator Agent 1)
        external_a2a = A2AClientConfig(
            endpoint=settings.external_a2a_endpoint,
            auth=BearerTokenAuth(token=settings.external_a2a_token),
            timeout=settings.external_a2a_timeout,
            max_turns=3,
            fail_fast=False,  # Graceful degradation if external A2A peer is unavailable
        )

        def on_step_callback(step_output):
            agent_role = getattr(step_output, "agent", "Agent")
            thought = getattr(step_output, "thought", None) or str(step_output)[:400]
            job_manager.publish_event(job_id, "agent_step", str(agent_role), thought)

        # 4. WORKER (Agent 2): Internal Telemetry & Runbook Specialist
        internal_telemetry_worker = Agent(
            role="Internal Telemetry Specialist",
            goal="Query internal service logs, deployment history, and runbooks using local MCP tools.",
            backstory=(
                "You are an internal SRE & SecOps specialist with exclusive access to private infrastructure "
                "telemetry via MCP. You gather exact timestamps, IPs, deployment diffs, and runbook steps, "
                "and respond clearly whenever the Coordinator Agent delegates work or asks follow-up questions."
            ),
            mcps=[local_mcp],
            llm=groq_llm,
            allow_delegation=False,  # Worker focuses strictly on internal MCP execution
            max_iter=5,
            step_callback=on_step_callback,
            verbose=True,
        )

        # 5. ROOT (Agent 1): Internal Coordinator Agent
        coordinator_agent = Agent(
            role="Internal Coordinator Agent",
            goal=(
                "Act as the root orchestrator: delegate internal log/deployment inspection to the Internal "
                "Telemetry Specialist, delegate external complex diagnostics to the remote A2A agent, and "
                "synthesize all evidence into a validated RCA report."
            ),
            backstory=(
                "You are the Lead Incident Coordinator at the top of the operational hierarchy. You have NO "
                "direct low-level MCP tools. Instead, you decompose problems cleanly:\n"
                "1) Delegate internal telemetry & runbook lookups to your coworker 'Internal Telemetry Specialist'.\n"
                "2) Delegate external complex analysis, threat evaluation, or remote tool tasks to the external "
                "specialist over the A2A protocol.\n"
                "3) Cross-verify findings between both specialists before producing the final structured RCA."
            ),
            llm=groq_llm,
            allow_delegation=True,  # Enables internal delegation & Q&A with Agent 2
            a2a=[external_a2a],      # Enables cross-boundary A2A delegation to Agent 3
            max_iter=8,
            step_callback=on_step_callback,
            verbose=True,
        )

        # 6. Top-Level Hierarchical Objective Owned by Coordinator Agent
        orchestration_task = Task(
            description=(
                f"Coordinate a full root-cause investigation for service '{service_name}'.\n"
                f"Alert Details: {alert_description}\n\n"
                "Execution Plan:\n"
                "Step 1: Delegate to the 'Internal Telemetry Specialist' to fetch logs, recent deployments, "
                "and security runbooks for this service.\n"
                "Step 2: Using the concrete artifacts uncovered (IP addresses, package versions, error signatures), "
                "consult the external specialist agent via A2A to execute complex external diagnostics.\n"
                "Step 3: If needed, ask the 'Internal Telemetry Specialist' follow-up questions to reconcile "
                "external findings with local state.\n"
                "Step 4: Synthesize everything into the final StructuredRCAReport."
            ),
            expected_output="A complete, verified Root Cause Analysis conforming to StructuredRCAReport.",
            agent=coordinator_agent,
            output_pydantic=StructuredRCAReport,
        )

        # 7. Assemble & Run Hierarchical Crew
        crew = Crew(
            agents=[coordinator_agent, internal_telemetry_worker],
            tasks=[orchestration_task],
            process=Process.sequential,  # Coordinator leads the task and delegates dynamically via tools/A2A
            verbose=True,
        )

        job_manager.publish_event(
            job_id,
            "lifecycle",
            "Internal Coordinator Agent",
            "Starting hierarchical orchestration across Internal MCP Worker and External A2A Peer...",
        )
        result = crew.kickoff()

        final_report = result.pydantic if result.pydantic else None
        job_manager.update_status(job_id, JobStatus.COMPLETED, report=final_report)
        job_manager.publish_event(job_id, "lifecycle", "System", "Hierarchical triage completed.")

    except Exception as exc:
        logger.exception(f"Hierarchical workflow failed for job {job_id}")
        job_manager.update_status(job_id, JobStatus.FAILED, error=str(exc))
        job_manager.publish_event(job_id, "error", "System", f"Workflow failed: {exc}")
