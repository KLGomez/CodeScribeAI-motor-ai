from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from app.config import get_settings

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
        self.llm = ChatGoogleGenerativeAI(
            model=settings.gemini_model,
            google_api_key=settings.gemini_api_key,
            temperature=0.2,
        )

    async def generate_overview(self, file_tree: str, readme: str) -> str:
        prompt = (
            f"{OVERVIEW_PROMPT}\n\n"
            f"**Árbol de archivos:**\n```\n{file_tree}\n```\n\n"
            f"**Contenido del README:**\n```markdown\n{readme[:4000]}\n```"
        )
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ]
        response = await self.llm.ainvoke(messages)
        return str(response.content)

    async def document_chunk(self, filepath: str, chunk: str, chunk_index: int) -> str:
        prompt = (
            f"Documenta técnicamente el siguiente bloque ({chunk_index + 1}) del archivo `{filepath}`:\n\n"
            f"```\n{chunk}\n```"
        )
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ]
        response = await self.llm.ainvoke(messages)
        return str(response.content)
