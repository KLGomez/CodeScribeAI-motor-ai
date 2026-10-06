"""Pruebas unitarias de la integración LCEL con LangChain 1.x (M-11)."""

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import FakeListChatModel, GenericFakeChatModel
from langchain_core.messages import AIMessage

from app.services.llm_service import LLMService, ModuleSummarySchema


class FailingChatModel(BaseChatModel):
    """Modelo simulado que siempre falla para probar conmutación a fallbacks."""

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        raise RuntimeError("Primary model unavailable 503")

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        raise RuntimeError("Primary model unavailable 503")

    @property
    def _llm_type(self) -> str:
        return "failing_chat_model"


@pytest.mark.asyncio
async def test_lcel_direct_route_with_fake_chat_model():
    """Verifica la generación directa de documentación con modelo falso de LangChain."""
    expected_doc = (
        "# Documentación Técnica: demo-app\n\n"
        "## 1. Propósito General del Sistema\nSistema de demostración.\n\n"
        "## 2. Arquitectura y Flujo de Datos\nPatrón cliente-servidor.\n\n"
        "## 3. Stack Tecnológico y Dependencias\nPython 3.12.\n\n"
        "## 4. Mapa de Responsabilidades por Directorio\nDirectorio app/.\n\n"
        "## 5. Análisis de Módulos y Componentes de Negocio\n### `main`\nLógica principal.\n\n"
        "## 6. Guía de Puesta en Marcha y Entorno\npython app/main.py\n"
    )

    fake_llm = FakeListChatModel(responses=[expected_doc])
    service = LLMService(custom_llm=fake_llm)

    doc, tokens = await service.generate_full_architecture_docs(
        repo_url="https://github.com/test/demo-app",
        repo_name="demo-app",
        file_tree="app/main.py",
        manifest_content="requirements.txt",
        readme_content="Demo readme",
        source_code_bundle="print('hello')",
    )

    assert "## 1. Propósito General del Sistema" in doc
    assert "## 6. Guía de Puesta en Marcha y Entorno" in doc
    assert isinstance(tokens, int)


@pytest.mark.asyncio
async def test_lcel_usage_metadata_token_accumulation():
    """Verifica que los tokens reales de usage_metadata en AIMessage se extraigan y contabilicen (M-11.5)."""
    fake_msg = AIMessage(
        content="Documentación técnica simulada ## 1. Propósito",
        usage_metadata={"input_tokens": 120, "output_tokens": 80, "total_tokens": 200},
    )

    fake_llm = GenericFakeChatModel(messages=iter([fake_msg]))
    service = LLMService(custom_llm=fake_llm)

    doc, tokens = await service.generate_full_architecture_docs(
        repo_url="https://github.com/test/token-app",
        repo_name="token-app",
        file_tree="app/main.py",
        manifest_content="",
        readme_content="",
        source_code_bundle="code",
    )

    assert tokens == 200
    assert "## 1. Propósito" in doc


@pytest.mark.asyncio
async def test_lcel_map_reduce_group_summary_and_compose():
    """Verifica las cadenas de resumen grupal (MAP) y consolidación final (REDUCE) (M-11.3)."""
    fake_summary = "Resumen del módulo de autenticación con JWT."
    fake_final_doc = "# Documentación Final Consolidada\n## 1. Propósito\nSistema integrado."

    fake_llm = FakeListChatModel(responses=[fake_summary, fake_final_doc])
    service = LLMService(custom_llm=fake_llm)

    # 1. Fase MAP
    summary, tokens_map = await service.summarize_group(
        group_name="auth",
        repo_name="my-app",
        group_files_bundle="auth_service.py content",
    )
    assert "autenticación con JWT" in summary

    # 2. Fase REDUCE
    composed_doc, tokens_reduce = await service.compose_from_summaries(
        repo_url="https://github.com/test/my-app",
        repo_name="my-app",
        file_tree="auth/\nmain.py",
        manifest_content="",
        readme_content="",
        modules_summaries=f"### auth\n{summary}",
    )
    assert "Documentación Final Consolidada" in composed_doc


@pytest.mark.asyncio
async def test_lcel_model_fallback_on_primary_failure():
    """Verifica que el mecanismo .with_fallbacks pase al siguiente modelo ante fallo (M-6, M-11.2)."""
    failing_primary = FailingChatModel()
    successful_fallback = FakeListChatModel(responses=["Documento generado por modelo secundario"])

    fallback_chain = failing_primary.with_fallbacks([successful_fallback])
    service = LLMService(custom_llm=fallback_chain)

    doc, _tokens = await service.generate_full_architecture_docs(
        repo_url="https://github.com/test/fallback-app",
        repo_name="fallback-app",
        file_tree="",
        manifest_content="",
        readme_content="",
        source_code_bundle="",
    )

    assert "modelo secundario" in doc


@pytest.mark.asyncio
async def test_lcel_structured_output_module_schema():
    """Verifica que el schema Pydantic estructurado sea compatible y válido (M-11.4)."""
    schema = ModuleSummarySchema(
        module_name="auth.service",
        purpose="Autenticación segura de usuarios mediante JWT",
        inputs_outputs="Recibe credenciales, devuelve tokens firmados",
        dependencies=["users.service", "crypto.util"],
    )

    assert schema.module_name == "auth.service"
    assert "crypto.util" in schema.dependencies


def test_no_deprecated_langchain_prompts_imported():
    """Asegura que no exista ningún import obsoleto de 'langchain.prompts' en la aplicación (M-11)."""
    import os

    app_dir = os.path.join(os.path.dirname(__file__), "..", "app")
    for root, _, files in os.walk(app_dir):
        for f in files:
            if f.endswith(".py"):
                path = os.path.join(root, f)
                with open(path, "r", encoding="utf-8") as file_obj:
                    content = file_obj.read()
                    assert "from langchain.prompts" not in content, f"Import obsoleto en {path}"
                    assert "import langchain.prompts" not in content, f"Import obsoleto en {path}"
