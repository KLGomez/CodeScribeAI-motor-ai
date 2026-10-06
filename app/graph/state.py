"""Estado tipado para el grafo de análisis de arquitectura con LangGraph (M-12.1)."""

import operator
from typing import Annotated, Any, Dict, List, Optional, TypedDict

from pydantic import SecretStr


class GroupPayload(TypedDict, total=False):
    """Payload enviado a cada nodo paralelo summarize_group vía Send."""

    group_name: str
    repo_name: str
    files_bundle: str
    job_id: str


class AnalysisState(TypedDict, total=False):
    """Estado global del grafo de análisis orquestado por LangGraph."""

    # Identificadores y credenciales protegidas
    repo_url: str
    repo_name: str
    github_token: SecretStr
    job_id: str

    # Datos brutos del repositorio
    raw_files: Dict[str, str]
    files_total: int
    files_analyzed: int
    truncated: bool

    # Categorización y selección de archivos
    file_tree: str
    manifest_content: str
    readme_content: str
    source_code_bundle: str
    requires_map_reduce: bool

    # Planificación y ejecución Map-Reduce
    groups: List[Dict[str, Any]]
    summaries: Annotated[List[str], operator.add]

    # Documento y control de calidad
    document: str
    sections: List[str]
    attempts: int
    validation_error: Optional[str]
    is_valid: bool

    # Contabilidad acumulada de tokens
    tokens_used: Annotated[int, operator.add]
