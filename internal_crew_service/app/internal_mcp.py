from mcp.server.fastmcp import FastMCP

mcp = FastMCP("InternalTelemetryMCP")


@mcp.tool()
def fetch_service_logs(service_name: str) -> str:
    """Fetch recent security, latency, and egress logs for an internal microservice."""
    logs_db = {
        "auth-service": (
            "[2026-11-16T09:41:02Z] INFO: Pod auth-service-7d9f8b-xk2p9 started with image auth-service:v2.14.0 (Deploy #418)\n"
            "[2026-11-16T09:41:08Z] WARN: Unexpected outbound TLS session initiated by worker to 185.220.101.42:443\n"
            "[2026-11-16T09:41:12Z] ERROR: Egress policy alert triggered — unauthorized external destination 185.220.101.42"
        ),
        "payment-gateway": (
            "[2026-11-16T09:42:01Z] ERROR: Upstream HTTP 503 from auth-service during /v1/session/verify\n"
            "[2026-11-16T09:42:05Z] WARN: Circuit breaker tripped for auth-service"
        ),
    }
    return logs_db.get(
        service_name.lower().strip(),
        f"No anomalous logs found for service '{service_name}'.",
    )


@mcp.tool()
def get_recent_deployments(service_name: str) -> str:
    """Retrieve recent CI/CD deployment history and dependency diffs for a service."""
    deployments_db = {
        "auth-service": (
            "Deploy #418 (09:40 UTC) by ci-release-bot:\n"
            "  + Added dependency: xyz-token-helper==1.4.2\n"
            "  + Updated token-cache TTL from 300s to 600s"
        ),
        "payment-gateway": "Deploy #209 (48h ago): Routine security patch, healthy until 09:42 UTC.",
    }
    return deployments_db.get(
        service_name.lower().strip(),
        f"No deployments recorded in the last 24h for '{service_name}'.",
    )


@mcp.tool()
def query_internal_runbook(incident_category: str) -> str:
    """Search approved internal SRE & SecOps remediation runbooks."""
    return (
        "RUNBOOK-SEC-09 (Unauthorized Egress / Compromised Dependency):\n"
        "1. Apply Kubernetes NetworkPolicy `deny-all-egress` to isolate affected pods immediately.\n"
        "2. Roll back deployment to last verified digest (`kubectl rollout undo deployment/auth-service`).\n"
        "3. Rotate JWT signing keys and service credentials mounted into the compromised pod."
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
