"""Constructor y compilador del grafo de análisis orquestado con LangGraph (M-12)."""

import os
from typing import Any, List, Optional, Union

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy, Send

from app.config import get_settings
from app.core.exceptions import (
    AiTimeoutException,
    AiUnavailableException,
    GitHubRateLimitException,
    RepoEmptyException,
    RepoNotFoundException,
)
from app.graph.nodes import (
    compose_node,
    fetch_repo_node,
    plan_groups_node,
    select_files_node,
    summarize_group_node,
    validate_node,
)
from app.graph.state import AnalysisState, GroupPayload
from app.services.llm_service import LLMService


def is_transient_error(exc: Exception) -> bool:
    """Filtro para RetryPolicy: reintenta únicamente errores transitorios (M-12.4)."""
    if isinstance(exc, (RepoNotFoundException, RepoEmptyException)):
        return False
    if isinstance(exc, (AiTimeoutException, AiUnavailableException, GitHubRateLimitException)):
        return True
    err_str = str(exc).lower()
    return any(
        k in err_str
        for k in ["429", "503", "504", "timeout", "timed out", "rate limit", "quota", "temporarily unavailable"]
    )


def route_after_select_files(state: AnalysisState) -> str:
    """Arista condicional 1: bifurca a Map-Reduce o a composición directa (M-12.2)."""
    if state.get("requires_map_reduce", False):
        return "plan_groups"
    return "compose"


def fan_out_groups(state: AnalysisState) -> Union[List[Send], str]:
    """Arista condicional 2: Fan-out paralelo hacia summarize_group vía Send (M-12.2)."""
    groups = state.get("groups", [])
    if not groups:
        return "compose"

    sends: List[Send] = []
    repo_name = state.get("repo_name", "")
    job_id = state.get("job_id", "")

    for group in groups:
        payload: GroupPayload = {
            "group_name": group["group_name"],
            "repo_name": repo_name,
            "files_bundle": group["files_bundle"],
            "job_id": job_id,
        }
        sends.append(Send("summarize_group", payload))

    return sends


def route_after_validate(state: AnalysisState) -> str:
    """Arista condicional 3: Evalúa si el Markdown es válido o reintenta compose (M-12.3)."""
    if state.get("is_valid", False):
        return END

    # Si aún no se alcanza el máximo de intentos (tope MAX_COMPOSE_ATTEMPTS=2), reintentar compose con feedback
    if state.get("attempts", 1) < 2:
        return "compose"

    return END


def build_analysis_graph(
    llm_service: Optional[LLMService] = None,
    checkpointer: Optional[Any] = None,
) -> Any:
    """Construye y compila el StateGraph de análisis de repositorio (M-12)."""
    settings = get_settings()
    service = llm_service or LLMService()

    builder = StateGraph(AnalysisState)

    # Políticas de reintento ante errores transitorios de red o cuota (M-12.4)
    llm_retry_policy = RetryPolicy(
        max_attempts=3,
        initial_interval=1.0,
        backoff_factor=2.0,
        retry_on=is_transient_error,
    )
    github_retry_policy = RetryPolicy(
        max_attempts=2,
        initial_interval=1.0,
        backoff_factor=2.0,
        retry_on=is_transient_error,
    )

    # 1. Registro de nodos
    builder.add_node("fetch_repo", fetch_repo_node, retry_policy=github_retry_policy)
    builder.add_node("select_files", select_files_node)
    builder.add_node("plan_groups", plan_groups_node)

    async def _bound_summarize_group(payload: GroupPayload):
        return await summarize_group_node(payload, llm_service=service)

    builder.add_node("summarize_group", _bound_summarize_group, retry_policy=llm_retry_policy)

    async def _bound_compose(state: AnalysisState):
        return await compose_node(state, llm_service=service)

    builder.add_node("compose", _bound_compose, retry_policy=llm_retry_policy)
    builder.add_node("validate", validate_node)

    # 2. Conexión de aristas del flujo
    builder.add_edge(START, "fetch_repo")
    builder.add_edge("fetch_repo", "select_files")

    builder.add_conditional_edges(
        "select_files",
        route_after_select_files,
        {"plan_groups": "plan_groups", "compose": "compose"},
    )

    builder.add_conditional_edges(
        "plan_groups",
        fan_out_groups,
        ["summarize_group", "compose"],
    )

    builder.add_edge("summarize_group", "compose")
    builder.add_edge("compose", "validate")

    builder.add_conditional_edges(
        "validate",
        route_after_validate,
        {"compose": "compose", END: END},
    )

    # 3. Checkpointer opcional (stateless en producción, in-memory solo con DEBUG_GRAPH=true) (M-12.5)
    selected_checkpointer = checkpointer
    if selected_checkpointer is None and settings.debug_graph:
        selected_checkpointer = MemorySaver()

    return builder.compile(checkpointer=selected_checkpointer)


def generate_mermaid_diagram() -> str:
    """Genera la representación en sintaxis Mermaid del grafo compilado (M-12.6)."""
    graph = build_analysis_graph()
    return graph.get_graph().draw_mermaid()


def export_mermaid_diagram(file_path: str = "docs/graph.md") -> str:
    """Exporta el diagrama Mermaid del grafo a un archivo Markdown (M-12.6)."""
    mermaid_code = generate_mermaid_diagram()
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    content = (
        "# Diagrama de Arquitectura de LangGraph — CodeScribe AI\n\n"
        "> Grafo de orquestación stateful para el análisis arquitectónico y generación de documentación técnica.\n\n"
        "```mermaid\n"
        f"{mermaid_code}\n"
        "```\n"
    )
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    return content
