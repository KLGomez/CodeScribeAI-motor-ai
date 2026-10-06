"""Pruebas exhaustivas para la orquestación con LangGraph StateGraph (M-12)."""

import os
from unittest.mock import patch

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from pydantic import SecretStr

from app.core.exceptions import (
    RepoNotFoundException,
)
from app.core.github_client import RepositoryFilesResult
from app.graph.builder import build_analysis_graph, generate_mermaid_diagram
from app.services.llm_service import LLMService

SAMPLE_VALID_MARKDOWN = (
    "# Documentación Técnica: test-repo\n\n"
    "> Documentación de arquitectura orientada al comportamiento\n\n"
    "## 1. Propósito General del Sistema\nSistema de análisis.\n\n"
    "## 2. Arquitectura y Flujo de Datos\n```mermaid\ngraph TD;\nA-->B;\n```\n\n"
    "## 3. Stack Tecnológico y Dependencias\nPython, FastAPI.\n\n"
    "## 4. Mapa de Responsabilidades por Directorio\nDirectorio app/.\n\n"
    "## 5. Análisis de Módulos y Componentes de Negocio\n### `core`\nLógica central.\n\n"
    "## 6. Guía de Puesta en Marcha y Entorno\npytest\n"
)


def test_graph_mermaid_diagram_up_to_date():
    """Verifica que el diagrama Mermaid committeado en docs/graph.md coincida con el grafo (M-12.6)."""
    docs_path = os.path.join(os.path.dirname(__file__), "..", "docs", "graph.md")
    assert os.path.exists(docs_path), "El archivo docs/graph.md debe existir"

    with open(docs_path, "r", encoding="utf-8") as f:
        committed_content = f.read()

    generated_mermaid = generate_mermaid_diagram()
    assert generated_mermaid in committed_content, "El diagrama Mermaid en docs/graph.md está desactualizado"


@pytest.mark.asyncio
async def test_graph_direct_route_small_repo():
    """Verifica la ejecución directa en el grafo para un repositorio pequeño sin Map-Reduce (M-12)."""
    mock_files = {
        "src/index.ts": "export const app = 1;",
        "src/util.ts": "export const helper = 2;",
        "package.json": "{}",
        "README.md": "# Demo",
    }
    mock_result = RepositoryFilesResult(
        files=mock_files,
        files_analyzed=4,
        files_total=4,
        truncated=False,
    )

    fake_llm = FakeListChatModel(responses=[SAMPLE_VALID_MARKDOWN])
    fake_service = LLMService(custom_llm=fake_llm)
    graph = build_analysis_graph(llm_service=fake_service)

    with patch("app.services.analyzer.fetch_repository_files", return_value=mock_result):
        state = await graph.ainvoke({
            "repo_url": "https://github.com/KLGomez/small-repo",
            "github_token": SecretStr("ghp_secret_token_123"),
            "job_id": "test-job-small",
            "summaries": [],
            "tokens_used": 0,
            "attempts": 0,
        })

    assert state["is_valid"] is True
    assert "## 1. Propósito General del Sistema" in state["document"]
    assert len(state["sections"]) == 6
    assert state["files_analyzed"] == 4
    assert state.get("requires_map_reduce") is False


@pytest.mark.asyncio
async def test_graph_fanout_map_reduce_large_repo():
    """Verifica la ruta Map-Reduce con fan-out paralelo para repositorios grandes (>20 archivos) (M-12.2)."""
    # Crear 30 archivos repartidos en 3 módulos
    mock_files = {}
    for i in range(10):
        mock_files[f"auth/service_{i}.py"] = f"def auth_{i}(): pass"
    for i in range(10):
        mock_files[f"billing/service_{i}.py"] = f"def bill_{i}(): pass"
    for i in range(10):
        mock_files[f"users/service_{i}.py"] = f"def user_{i}(): pass"

    mock_result = RepositoryFilesResult(
        files=mock_files,
        files_analyzed=30,
        files_total=30,
        truncated=False,
    )

    # 3 respuestas para los grupos (fan-out) + 1 respuesta para compose consolidado
    responses = [
        "Resumen auth",
        "Resumen billing",
        "Resumen users",
        SAMPLE_VALID_MARKDOWN,
    ]
    fake_llm = FakeListChatModel(responses=responses)
    fake_service = LLMService(custom_llm=fake_llm)
    graph = build_analysis_graph(llm_service=fake_service)

    with patch("app.services.analyzer.fetch_repository_files", return_value=mock_result):
        state = await graph.ainvoke({
            "repo_url": "https://github.com/KLGomez/large-repo",
            "github_token": SecretStr("ghp_secret_token_123"),
            "job_id": "test-job-large",
            "summaries": [],
            "tokens_used": 0,
            "attempts": 0,
        })

    assert state["is_valid"] is True
    assert state.get("requires_map_reduce") is True
    # Se acumularon resúmenes de los grupos
    assert len(state["summaries"]) >= 3
    assert state["files_analyzed"] == 30


@pytest.mark.asyncio
async def test_graph_terminal_error_no_retry():
    """Verifica que errores terminales como REPO_NOT_FOUND fallen de inmediato sin reintentar (M-12.4)."""
    graph = build_analysis_graph()

    with patch(
        "app.services.analyzer.fetch_repository_files",
        side_effect=RepoNotFoundException("Repositorio inexistente"),
    ):
        with pytest.raises(RepoNotFoundException):
            await graph.ainvoke({
                "repo_url": "https://github.com/KLGomez/non-existent",
                "github_token": SecretStr("token"),
                "job_id": "test-terminal-job",
                "summaries": [],
                "tokens_used": 0,
                "attempts": 0,
            })


@pytest.mark.asyncio
async def test_graph_validation_correction_loop_success():
    """Verifica que si la validación falla en intento 1, reintente compose y apruebe en intento 2 (M-12.3)."""
    mock_files = {"src/app.py": "print(1)"}
    mock_result = RepositoryFilesResult(
        files=mock_files,
        files_analyzed=1,
        files_total=1,
        truncated=False,
    )

    # Intento 1: Markdown largo incompleto (falta sección 6)
    incomplete_draft = (
        "# Doc Incompleta\n\n"
        "## 1. Propósito\nDescripción larga " + ("x" * 400) + "\n\n"
        "## 2. Arquitectura\nFlujo.\n\n"
        "## 3. Stack\nTech.\n\n"
        "## 4. Directorios\nEstructura.\n\n"
        "## 5. Módulos\nNegocio.\n\n"
    )
    # Intento 2: Markdown completo corregido
    corrected_draft = SAMPLE_VALID_MARKDOWN

    fake_llm = FakeListChatModel(responses=[incomplete_draft, corrected_draft])
    fake_service = LLMService(custom_llm=fake_llm)
    graph = build_analysis_graph(llm_service=fake_service)

    with patch("app.services.analyzer.fetch_repository_files", return_value=mock_result):
        state = await graph.ainvoke({
            "repo_url": "https://github.com/KLGomez/repair-repo",
            "github_token": SecretStr("token"),
            "job_id": "test-repair-job",
            "summaries": [],
            "tokens_used": 0,
            "attempts": 0,
        })

    assert state["is_valid"] is True
    assert state["attempts"] == 2
    assert "## 6. Guía de Puesta en Marcha y Entorno" in state["document"]


@pytest.mark.asyncio
async def test_graph_validation_failure_warning_note_fallback():
    """Verifica que tras agotar los 2 intentos de composición, emita advertencia sin error (M-12.3)."""
    mock_files = {"src/app.py": "print(1)"}
    mock_result = RepositoryFilesResult(
        files=mock_files,
        files_analyzed=1,
        files_total=1,
        truncated=False,
    )

    # Ambos intentos devuelven markdown con secciones faltantes
    stubborn_draft = (
        "# Doc Incompleta\n\n"
        "## 1. Propósito\nDescripción muy extensa " + ("y" * 400) + "\n\n"
    )

    fake_llm = FakeListChatModel(responses=[stubborn_draft, stubborn_draft])
    fake_service = LLMService(custom_llm=fake_llm)
    graph = build_analysis_graph(llm_service=fake_service)

    with patch("app.services.analyzer.fetch_repository_files", return_value=mock_result):
        state = await graph.ainvoke({
            "repo_url": "https://github.com/KLGomez/warning-repo",
            "github_token": SecretStr("token"),
            "job_id": "test-warning-job",
            "summaries": [],
            "tokens_used": 0,
            "attempts": 0,
        })

    # El grafo concluye normalmente pero con nota de advertencia al inicio
    assert "Nota de Advertencia" in state["document"]
    assert state["is_valid"] is True
    assert state["attempts"] == 2


def test_graph_token_never_leaked_in_state():
    """Verifica que github_token como SecretStr nunca se serialice en texto plano (M-8, M-12.1)."""
    secret_val = "ghp_super_secret_github_token_98765"
    state = {
        "repo_url": "https://github.com/KLGomez/repo",
        "github_token": SecretStr(secret_val),
    }

    state_repr = str(state)
    assert secret_val not in state_repr
    assert "**********" in state_repr
