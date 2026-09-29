import logging
from app.config import get_settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Eres un Tech Lead y Arquitecto experto en documentación técnica de software.
Tu objetivo es generar documentación concisa, estructurada y en formato Markdown en español.

Pautas:
- Usa títulos jerárquicos (##, ###).
- Describe el propósito general, clases, métodos y parámetros relevantes.
- Incluye ejemplos o snippets de código con el lenguaje indicado si aportan claridad.
- Sé riguroso y profesional.
"""

OVERVIEW_PROMPT = """Basándote en el siguiente árbol de archivos del repositorio y en el README principal,
genera una sección de OVERVIEW completa:
1. Resumen y propósito general del software.
2. Arquitectura de alto nivel identificada.
3. Principales dependencias o stacks tecnológicos.
4. Organización de directorios relevante.
"""


class LLMService:
    def __init__(self):
        settings = get_settings()
        self.api_key = settings.gemini_api_key
        self.model_name = settings.gemini_model
        self.llm = None

        if self.api_key and not self.api_key.startswith("your_"):
            try:
                from langchain_google_genai import ChatGoogleGenerativeAI
                self.llm = ChatGoogleGenerativeAI(
                    model=self.model_name,
                    google_api_key=self.api_key,
                    temperature=0.2,
                )
                logger.info(f"Initialized Gemini model: {self.model_name}")
            except Exception as e:
                logger.warning(f"Could not initialize Gemini LLM: {e}. Falling back to smart offline analyzer.")

    async def generate_overview(self, file_tree: str, readme: str) -> str:
        if self.llm:
            try:
                from langchain_core.messages import SystemMessage, HumanMessage
                prompt = (
                    f"{OVERVIEW_PROMPT}\n\n"
                    f"**Árbol de archivos:**\n```\n{file_tree}\n```\n\n"
                    f"**Contenido del README:**\n```markdown\n{readme[:4000]}\n```"
                )
                response = await self.llm.ainvoke([
                    SystemMessage(content=SYSTEM_PROMPT),
                    HumanMessage(content=prompt),
                ])
                return str(response.content)
            except Exception as exc:
                logger.warning(f"Gemini API invocation failed ({exc}), generating structured overview locally.")

        # Smart fallback generator
        lines = [
            "## 🎯 Resumen y Propósito General",
            "Este repositorio contiene la implementación del proyecto analizado por **CodeScribe AI**.",
            "",
            "### 🏛️ Arquitectura y Componentes Clave",
            "- **Módulos detectados:**",
        ]
        sample_tree = [f"- `{line}`" for line in file_tree.split("\n")[:12] if line.strip()]
        lines.extend(sample_tree)
        lines.append("")
        if readme:
            lines.append("### 📖 Extracto del README Principal")
            lines.append(f"> {readme.splitlines()[0] if readme.splitlines() else 'Sin descripción inicial'}")
            lines.append("")
        return "\n".join(lines)

    async def document_chunk(self, filepath: str, chunk: str, chunk_index: int) -> str:
        if self.llm:
            try:
                from langchain_core.messages import SystemMessage, HumanMessage
                prompt = (
                    f"Documenta técnicamente el siguiente bloque ({chunk_index + 1}) del archivo `{filepath}`:\n\n"
                    f"```\n{chunk}\n```"
                )
                response = await self.llm.ainvoke([
                    SystemMessage(content=SYSTEM_PROMPT),
                    HumanMessage(content=prompt),
                ])
                return str(response.content)
            except Exception as exc:
                logger.warning(f"Gemini chunk failed ({exc}), generating structural docs locally.")

        # Local structural documentation
        doc_lines = [
            f"Análisis estructural del bloque {chunk_index + 1} en `{filepath}`.",
            "",
            "#### Elementos Identificados:",
        ]
        for line in chunk.split("\n"):
            line_str = line.strip()
            if line_str.startswith(("def ", "class ", "function ", "export function ", "export const ", "interface ", "type ")):
                doc_lines.append(f"- **Definición:** `{line_str[:80]}`")

        if len(doc_lines) == 3:
            doc_lines.append("- Lógica interna o constantes de soporte del módulo.")

        doc_lines.append("\n```" + filepath.split(".")[-1])
        doc_lines.append(chunk[:400] + ("\n... [truncado]" if len(chunk) > 400 else ""))
        doc_lines.append("```")

        return "\n".join(doc_lines)
