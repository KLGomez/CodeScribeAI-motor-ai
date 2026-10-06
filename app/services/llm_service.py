"""Servicio de integración con LLM usando LangChain 1.x (LCEL) y ChatGoogleGenerativeAI (M-11)."""

import asyncio
import logging
import os
from typing import Any, List, Optional, Tuple

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from app.config import get_settings
from app.core.exceptions import AiTimeoutException, AiUnavailableException
from app.prompts.architecture_prompts import (
    CORRECTION_PROMPT_TEMPLATE,
    DOCUMENTATION_PROMPT_TEMPLATE,
    GROUP_SUMMARY_PROMPT_TEMPLATE,
    MAP_REDUCE_COMPOSE_PROMPT_TEMPLATE,
)
from app.utils.sanitizer import sanitize_llm_markdown

logger = logging.getLogger(__name__)

VERIFIED_GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
]


class ModuleSummarySchema(BaseModel):
    """Esquema estructurado para análisis de módulo o componente (M-11.4)."""

    module_name: str = Field(description="Nombre identificador del módulo o archivo analizado")
    purpose: str = Field(description="Responsabilidad técnica y propósito en el sistema")
    inputs_outputs: str = Field(description="Entradas (props, parámetros) y salidas (retornos, eventos)")
    dependencies: List[str] = Field(default_factory=list, description="Lista de módulos o dependencias consumidas")


class LLMService:
    """Gestiona la cadena LCEL y comunicación con Google Gemini usando LangChain 1.x."""

    def __init__(self, custom_llm: Optional[BaseChatModel] = None):
        self.settings = get_settings()
        self.custom_llm = custom_llm
        self._init_observability()
        self.chain = self._build_main_chain()

    def _init_observability(self) -> None:
        """Configura opcionalmente trazas con LangSmith si está habilitado sin filtrar código de usuarios."""
        if self.settings.langsmith_tracing and self.settings.langsmith_api_key:
            os.environ["LANGSMITH_TRACING"] = "true"
            os.environ["LANGSMITH_API_KEY"] = self.settings.langsmith_api_key
            logger.info("Observabilidad con LangSmith activada mediante variables de entorno")
        else:
            os.environ["LANGSMITH_TRACING"] = "false"

    def _build_llm(self, model_name: str) -> BaseChatModel:
        """Construye una instancia de ChatGoogleGenerativeAI con timeout explícito y reintentos (M-6)."""
        api_key = self.settings.gemini_api_key or os.getenv("GOOGLE_API_KEY", "")
        if not api_key:
            raise AiUnavailableException(
                "La clave de Google Gemini (GEMINI_API_KEY / GOOGLE_API_KEY) no está configurada."
            )

        llm = ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=api_key,
            temperature=0.1,
            timeout=float(self.settings.gemini_timeout_seconds),
        )
        return llm

    def _build_main_chain(self) -> Any:
        """Construye la cadena principal con fallbacks entre modelos y retry con backoff (M-6, M-11.2)."""
        if self.custom_llm is not None:
            return self.custom_llm

        primary_model = self.settings.gemini_model or "gemini-2.5-flash"
        fallback_models = ["gemini-2.0-flash"]
        if primary_model in fallback_models:
            fallback_models.remove(primary_model)

        try:
            primary_llm = self._build_llm(primary_model).with_retry(
                stop_after_attempt=3,
                wait_exponential_jitter=True,
            )

            fallback_llms = [
                self._build_llm(m).with_retry(stop_after_attempt=2)
                for m in fallback_models
            ]

            if fallback_llms:
                return primary_llm.with_fallbacks(fallback_llms)
            return primary_llm
        except Exception as exc:
            logger.warning(f"No se pudo inicializar ChatGoogleGenerativeAI en constructor: {exc}")
            return None

    def get_llm(self) -> BaseChatModel:
        """Devuelve el modelo configurado o genera una excepción tipificada si no está disponible."""
        if self.custom_llm is not None:
            return self.custom_llm
        if self.chain is None:
            self.chain = self._build_main_chain()
        if self.chain is None:
            raise AiUnavailableException(
                "El cliente de Google Gemini no está inicializado. Verifica GEMINI_API_KEY o GOOGLE_API_KEY."
            )
        return self.chain

    def build_runnable_chain(
        self, prompt_template: Any, llm: Optional[BaseChatModel] = None
    ) -> Any:
        """Cadena estándar LCEL: prompt | llm | StrOutputParser() (M-11.2)."""
        model = llm or self.get_llm()
        return prompt_template | model | StrOutputParser()

    async def _invoke_chain_with_tokens(
        self,
        prompt_template: Any,
        inputs: dict,
        llm: Optional[BaseChatModel] = None,
    ) -> Tuple[str, int]:
        """Invoca un Runnable LCEL interceptando el AIMessage para extraer tokens reales de usage_metadata (M-11.5)."""
        model = llm or self.get_llm()
        chain = prompt_template | model

        try:
            response = await chain.ainvoke(inputs)

            if isinstance(response, AIMessage):
                text = response.content if isinstance(response.content, str) else str(response.content)
                metadata = getattr(response, "usage_metadata", None) or {}
                tokens_used = metadata.get("total_tokens", 0)
            elif isinstance(response, str):
                text = response
                tokens_used = len(response) // 4
            else:
                text = str(response)
                tokens_used = 0

            return text, tokens_used

        except asyncio.TimeoutError:
            logger.error(f"Timeout de {self.settings.gemini_timeout_seconds}s en llamada LCEL a Gemini")
            raise AiTimeoutException(
                f"El tiempo de espera para generar la documentación ha expirado ({self.settings.gemini_timeout_seconds}s)."
            )
        except Exception as exc:
            err_str = str(exc).lower()
            if "timeout" in err_str or "timed out" in err_str:
                raise AiTimeoutException(
                    "El tiempo de espera de la solicitud a Gemini ha expirado."
                ) from exc
            logger.error(f"Error invocando cadena LCEL: {exc}")
            raise AiUnavailableException(
                f"Fallo en la generación de documentación con Gemini ({exc})."
            ) from exc

    async def generate_full_architecture_docs(
        self,
        repo_url: str,
        repo_name: str,
        file_tree: str,
        manifest_content: str,
        readme_content: str,
        source_code_bundle: str,
        llm: Optional[BaseChatModel] = None,
    ) -> Tuple[str, int]:
        """Ruta directa LCEL: genera el documento completo cuando el contenido cabe en MAX_BUNDLE_CHARS (M-11.2)."""
        inputs = {
            "repo_url": repo_url,
            "repo_name": repo_name,
            "file_tree": file_tree,
            "manifest_content": manifest_content[:4000] if manifest_content else "Sin manifiesto.",
            "readme_content": readme_content[:4000] if readme_content else "Sin README provisto.",
            "source_code_bundle": source_code_bundle[: self.settings.max_bundle_chars],
        }

        text, tokens_used = await self._invoke_chain_with_tokens(
            DOCUMENTATION_PROMPT_TEMPLATE, inputs, llm=llm
        )

        stripped = text.strip()
        if stripped == "[OMITIR_DOCUMENTACION]":
            return (
                f"# Documentación: {repo_name}\n\n*El repositorio contiene únicamente archivos de configuración o manifiestos sin lógica de negocio documentable.*",
                tokens_used,
            )

        sanitized = sanitize_llm_markdown(text)
        return sanitized, tokens_used

    async def summarize_group(
        self,
        group_name: str,
        repo_name: str,
        group_files_bundle: str,
        llm: Optional[BaseChatModel] = None,
    ) -> Tuple[str, int]:
        """Fase MAP de Map-Reduce: resume un grupo de archivos en paralelo (M-11.3)."""
        inputs = {
            "group_name": group_name,
            "repo_name": repo_name,
            "group_files_bundle": group_files_bundle,
        }
        text, tokens_used = await self._invoke_chain_with_tokens(
            GROUP_SUMMARY_PROMPT_TEMPLATE, inputs, llm=llm
        )
        return text.strip(), tokens_used

    async def compose_from_summaries(
        self,
        repo_url: str,
        repo_name: str,
        file_tree: str,
        manifest_content: str,
        readme_content: str,
        modules_summaries: str,
        llm: Optional[BaseChatModel] = None,
    ) -> Tuple[str, int]:
        """Fase REDUCE de Map-Reduce: consolida los resúmenes en el documento arquitectónico final (M-11.3)."""
        inputs = {
            "repo_url": repo_url,
            "repo_name": repo_name,
            "file_tree": file_tree,
            "manifest_content": manifest_content[:4000] if manifest_content else "Sin manifiesto.",
            "readme_content": readme_content[:4000] if readme_content else "Sin README provisto.",
            "modules_summaries": modules_summaries,
        }
        text, tokens_used = await self._invoke_chain_with_tokens(
            MAP_REDUCE_COMPOSE_PROMPT_TEMPLATE, inputs, llm=llm
        )
        sanitized = sanitize_llm_markdown(text)
        return sanitized, tokens_used

    async def correct_document(
        self,
        previous_draft: str,
        validation_feedback: str,
        llm: Optional[BaseChatModel] = None,
    ) -> Tuple[str, int]:
        """Repetición correctiva tras fallo de validación (M-12.3)."""
        inputs = {
            "previous_draft": previous_draft,
            "validation_feedback": validation_feedback,
        }
        text, tokens_used = await self._invoke_chain_with_tokens(
            CORRECTION_PROMPT_TEMPLATE, inputs, llm=llm
        )
        sanitized = sanitize_llm_markdown(text)
        return sanitized, tokens_used

    async def summarize_module_structured(
        self,
        module_name: str,
        code_content: str,
        llm: Optional[BaseChatModel] = None,
    ) -> ModuleSummarySchema:
        """Salida estructurada con Pydantic para módulos individuales (M-11.4)."""
        model = llm or self.get_llm()
        structured_llm = model.with_structured_output(ModuleSummarySchema)
        prompt = (
            f"Extrae la estructura del módulo '{module_name}':\n```\n{code_content[:6000]}\n```"
        )
        return await structured_llm.ainvoke(prompt)
