"""Nodos de procesamiento funcionales y testeables para el grafo de LangGraph (M-12.2, M-12.7)."""

import asyncio
import logging
import re
from typing import Any, Dict, List, Optional

from pydantic import SecretStr

from app.config import get_settings
from app.core.exceptions import RepoEmptyException
from app.core.github_client import fetch_repository_files
from app.core.prioritizer import prioritize_files
from app.graph.state import AnalysisState, GroupPayload
from app.services.llm_service import LLMService
from app.utils.sanitizer import sanitize_llm_markdown

logger = logging.getLogger(__name__)

MANIFEST_NAMES = {"package.json", "pyproject.toml", "cargo.toml", "go.mod", "pom.xml"}
README_NAMES = {"readme.md", "readme.rst", "readme.txt"}
REQUIRED_SECTIONS = [
    "## 1. Propósito General del Sistema",
    "## 2. Arquitectura y Flujo de Datos",
    "## 3. Stack Tecnológico y Dependencias",
    "## 4. Mapa de Responsabilidades por Directorio",
    "## 5. Análisis de Módulos y Componentes de Negocio",
    "## 6. Guía de Puesta en Marcha y Entorno",
]


def extract_token_str(token_val: Any) -> str:
    """Extrae de forma segura el valor de SecretStr sin loguearlo jamás (M-8, M-12.1)."""
    if isinstance(token_val, SecretStr):
        return token_val.get_secret_value()
    if isinstance(token_val, str):
        return token_val
    return ""


async def fetch_repo_node(state: AnalysisState) -> Dict[str, Any]:
    """Nodo 1: Descarga archivos del repositorio mediante GitHub Git Trees API (M-4)."""
    repo_url = state["repo_url"]
    job_id = state.get("job_id", "job")
    token_str = extract_token_str(state.get("github_token"))

    logger.info(f"[{job_id}] LangGraph: Nodo fetch_repo para {repo_url}")
    import sys
    analyzer_mod = sys.modules.get("app.services.analyzer")
    fetch_fn = getattr(analyzer_mod, "fetch_repository_files", fetch_repository_files) if analyzer_mod else fetch_repository_files
    repo_result = await asyncio.to_thread(fetch_fn, repo_url, token_str)
    files = repo_result.files

    if not files:
        raise RepoEmptyException("El repositorio no contiene archivos de código analizables.")

    return {
        "raw_files": files,
        "files_total": repo_result.files_total,
        "files_analyzed": repo_result.files_analyzed,
        "truncated": repo_result.truncated,
    }


def select_files_node(state: AnalysisState) -> Dict[str, Any]:
    """Nodo 2: Prioriza archivos, extrae manifiestos y decide ruta directa vs Map-Reduce (M-12.2)."""
    settings = get_settings()
    repo_url = state["repo_url"]
    files = state.get("raw_files", {})
    repo_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")

    ordered_files = prioritize_files(files)

    manifest_content = ""
    readme_content = ""
    file_tree_lines: List[str] = []
    source_code_parts: List[str] = []
    total_bundle_chars = 0

    candidate_source_files: List[tuple[str, str]] = []

    for filepath, content in ordered_files:
        file_tree_lines.append(filepath)
        name_lower = filepath.lower().split("/")[-1]

        if name_lower in MANIFEST_NAMES and not manifest_content:
            manifest_content = content
        elif name_lower in README_NAMES and not readme_content:
            readme_content = content
        else:
            candidate_source_files.append((filepath, content))
            if (
                len(source_code_parts) < settings.max_source_files
                and total_bundle_chars < settings.max_bundle_chars
            ):
                ext = filepath.split(".")[-1]
                file_slice = content[: settings.max_chars_per_file]
                part_str = f"### Archivo: `{filepath}`\n```{ext}\n{file_slice}\n```"
                source_code_parts.append(part_str)
                total_bundle_chars += len(part_str)

    # Determinar si el repositorio requiere ruta Map-Reduce (más archivos de los que caben en el bundle directo)
    requires_map_reduce = (
        len(candidate_source_files) > settings.max_source_files
        or total_bundle_chars >= settings.max_bundle_chars
    )

    return {
        "repo_name": repo_name,
        "file_tree": "\n".join(file_tree_lines),
        "manifest_content": manifest_content,
        "readme_content": readme_content,
        "source_code_bundle": "\n\n".join(source_code_parts),
        "requires_map_reduce": requires_map_reduce,
    }


def plan_groups_node(state: AnalysisState) -> Dict[str, Any]:
    """Nodo 3: Agrupa archivos por módulos arquitectónicos para paralelización fan-out (M-11.3, M-12.2)."""
    settings = get_settings()
    files = state.get("raw_files", {})
    ordered_files = prioritize_files(files)

    groups_map: Dict[str, List[str]] = {}
    for filepath, content in ordered_files:
        name_lower = filepath.lower().split("/")[-1]
        if name_lower in MANIFEST_NAMES or name_lower in README_NAMES:
            continue

        parts = filepath.split("/")
        group_key = parts[0] if len(parts) > 1 else "root"
        if len(parts) > 2 and group_key in {"src", "app", "lib", "pkg"}:
            group_key = f"{group_key}/{parts[1]}"

        ext = filepath.split(".")[-1]
        file_slice = content[: settings.max_chars_per_file]
        part_str = f"### Archivo: `{filepath}`\n```{ext}\n{file_slice}\n```"

        groups_map.setdefault(group_key, []).append(part_str)

    groups_list: List[Dict[str, Any]] = []
    for g_name, g_files in groups_map.items():
        bundle = "\n\n".join(g_files)
        # Limitar tamaño de cada grupo para no sobrecargar el sub-prompt
        if len(bundle) > 25000:
            bundle = bundle[:25000]
        groups_list.append({
            "group_name": g_name,
            "files_bundle": bundle,
        })

    # Si hay demasiados grupos, consolidar a un máximo de 6 para controlar costos y cuotas
    if len(groups_list) > 6:
        groups_list = groups_list[:6]

    return {"groups": groups_list}


async def summarize_group_node(
    payload: GroupPayload,
    llm_service: Optional[LLMService] = None,
) -> Dict[str, Any]:
    """Nodo 4 (Fan-Out paralelo): Resume un grupo modular con tope de concurrencia (M-11.3, M-12.2)."""
    service = llm_service or LLMService()
    group_name = payload.get("group_name", "general")
    repo_name = payload.get("repo_name", "repo")
    files_bundle = payload.get("files_bundle", "")

    summary_text, tokens = await service.summarize_group(
        group_name=group_name,
        repo_name=repo_name,
        group_files_bundle=files_bundle,
    )

    formatted_summary = f"### Módulo o Directorio: `{group_name}`\n\n{summary_text}"
    return {
        "summaries": [formatted_summary],
        "tokens_used": tokens,
    }


async def compose_node(
    state: AnalysisState,
    llm_service: Optional[LLMService] = None,
) -> Dict[str, Any]:
    """Nodo 5: Redacta la documentación consolidada (directa, reduce o corrección) (M-11.2, M-12.2)."""
    service = llm_service or LLMService()
    validation_error = state.get("validation_error")
    current_attempts = state.get("attempts", 0)

    # 1. Si viene de un fallo de validación y hay intentos previos -> ejecutar corrección
    if validation_error and current_attempts > 0 and state.get("document"):
        logger.info(f"LangGraph: compose_node ejecutando corrección tras intento {current_attempts}")
        doc, tokens = await service.correct_document(
            previous_draft=state["document"],
            validation_feedback=validation_error,
        )
        return {
            "document": doc,
            "tokens_used": tokens,
            "attempts": current_attempts + 1,
            "validation_error": None,
        }

    # 2. Si requiere Map-Reduce -> consolidar resúmenes
    if state.get("requires_map_reduce", False) and state.get("summaries"):
        logger.info(f"LangGraph: compose_node consolidando {len(state['summaries'])} resúmenes Map-Reduce")
        modules_summaries = "\n\n".join(state["summaries"])
        doc, tokens = await service.compose_from_summaries(
            repo_url=state["repo_url"],
            repo_name=state["repo_name"],
            file_tree=state.get("file_tree", ""),
            manifest_content=state.get("manifest_content", ""),
            readme_content=state.get("readme_content", ""),
            modules_summaries=modules_summaries,
        )
        return {
            "document": doc,
            "tokens_used": tokens,
            "attempts": current_attempts + 1,
        }

    # 3. Ruta directa (el repositorio cabe en MAX_BUNDLE_CHARS)
    logger.info("LangGraph: compose_node ejecutando ruta directa de documentación")
    doc, tokens = await service.generate_full_architecture_docs(
        repo_url=state["repo_url"],
        repo_name=state["repo_name"],
        file_tree=state.get("file_tree", ""),
        manifest_content=state.get("manifest_content", ""),
        readme_content=state.get("readme_content", ""),
        source_code_bundle=state.get("source_code_bundle", ""),
    )
    return {
        "document": doc,
        "tokens_used": tokens,
        "attempts": current_attempts + 1,
    }


def validate_node(state: AnalysisState) -> Dict[str, Any]:
    """Nodo 6: Valida secciones esperadas, diagramas Mermaid cerrados y sanitiza Markdown (M-5, M-12.3)."""
    document = state.get("document", "")
    attempts = state.get("attempts", 1)

    # 1. Post-proceso de seguridad M-5
    sanitized_doc = sanitize_llm_markdown(document)

    # 2. Validar que los diagramas Mermaid estén cerrados y no vacíos
    mermaid_blocks = re.findall(r"```mermaid\s*([\s\S]*?)```", sanitized_doc)
    unclosed_mermaid = "```mermaid" in sanitized_doc and len(mermaid_blocks) < sanitized_doc.count("```mermaid")

    validation_errors: List[str] = []
    if unclosed_mermaid:
        validation_errors.append("Existen bloques de diagrama Mermaid que no fueron cerrados con ```.")

    for i, block in enumerate(mermaid_blocks):
        if not block.strip():
            validation_errors.append(f"El bloque de diagrama Mermaid #{i+1} está vacío.")

    # 3. Validar secciones mínimas esperadas (## 1. hasta ## 6.)
    sections_found: List[str] = []
    for line in sanitized_doc.splitlines():
        if line.startswith("## "):
            sections_found.append(line.replace("## ", "").strip())

    missing_sections = []
    if len(sanitized_doc) > 300:
        for num in range(1, 7):
            pattern = f"## {num}."
            if pattern not in sanitized_doc and f"## {num} " not in sanitized_doc:
                missing_sections.append(f"Sección {num}")
        if missing_sections:
            validation_errors.append(f"Faltan las siguientes secciones requeridas: {', '.join(missing_sections)}.")
    elif not sections_found:
        validation_errors.append("El documento no contiene ninguna sección con encabezado '## '.")

    is_valid = len(validation_errors) == 0

    if not is_valid:
        error_msg = " ; ".join(validation_errors)
        logger.warning(f"LangGraph validate_node: Falló validación en intento {attempts}: {error_msg}")

        # Si ya se alcanzó el tope de intentos (MAX_COMPOSE_ATTEMPTS=2), emitir advertencia sin fallar
        if attempts >= 2:
            warning_header = (
                "> ⚠️ **Nota de Advertencia:** La documentación generada a continuación fue procesada pero "
                "no superó completamente la verificación de formato estricto de todas las secciones.\n\n"
            )
            final_doc = warning_header + sanitized_doc
            return {
                "document": final_doc,
                "sections": sections_found if sections_found else ["Documentación General"],
                "is_valid": True,  # Marcar como terminal para concluir hacia END
                "validation_error": None,
            }

        return {
            "document": sanitized_doc,
            "is_valid": False,
            "validation_error": error_msg,
        }

    return {
        "document": sanitized_doc,
        "sections": sections_found if sections_found else ["Documentación General"],
        "is_valid": True,
        "validation_error": None,
    }
