import logging
import os
from typing import Dict, List
from app.config import get_settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Eres un Senior Software Architect y Tech Lead de clase mundial.
Tu misión es generar Documentación Técnica de Software de nivel profesional, exhaustiva y estructurada para desarrolladores y líderes técnicos.

Reglas Obligatorias:
1. IDIOMA: Todo el documento debe estar redactado en ESPAÑOL técnico impecable.
2. ENFOQUE: No te limites a enumerar archivos. Explica la lógica de negocio, arquitectura, flujo de datos, estado y diseño.
3. DIAGRAMAS: Incluye al menos un diagrama conceptual de arquitectura o flujo de componentes en sintaxis Mermaid (fenced code block ```mermaid ... ```).
4. CÓDIGO: Cuando expliques componentes o funciones clave, muestra fragmentos reales relevantes con sintaxis resaltada (ej: ```tsx, ```python, etc.).
5. FORMATO: Usa Markdown profesional con encabezados estructurados (##, ###), tablas de dependencias y bloques legibles.
"""

DOCUMENTATION_PROMPT = """Analiza a fondo el siguiente repositorio de código y genera una Documentación Técnica Completa de Arquitectura.

INFORMACIÓN DEL REPOSITORIO:
- URL: {repo_url}
- Nombre: {repo_name}

ÁRBOL DE DIRECTORIOS RELEVANTE:
```
{file_tree}
```

MANIFEST / DEPENDENCIAS (package.json / pyproject.toml):
```
{manifest_content}
```

README PRINCIPAL:
```
{readme_content}
```

CÓDIGO FUENTE REAL DEL PROYECTO:
{source_code_bundle}

Genera la documentación técnica completa siguiendo esta estructura:
# 📘 Documentación Técnica: {repo_name}

> Documentación de arquitectura generada automáticamente por **CodeScribe AI** · [Ver Repositorio Original]({repo_url})

---

## 1. 🎯 Resumen Ejecutivo y Propósito del Software
- ¿Qué problema resuelve este proyecto y qué valor entrega?
- Funcionalidades principales detectadas en el código.

## 2. 🏛️ Arquitectura del Sistema y Diagrama
- Patrón de arquitectura identificado (ej: SPA en React con Vite, arquitectura por capas, etc.).
- Diagrama de arquitectura o flujo de componentes en bloque Mermaid (usa ```mermaid graph TD o sequenceDiagram).
- Flujo de datos y ciclo de vida de la aplicación.

## 3. 🛠️ Stack Tecnológico y Dependencias
- Tabla detallada de tecnologías y bibliotecas clave (Nombre | Versión | Rol en el sistema).

## 4. 📂 Mapa de Estructura del Proyecto
- Detalle de los directorios clave y la responsabilidad técnica de cada uno.

## 5. 🧩 Análisis Detallado de Componentes y Lógica de Negocio
- Análisis profundo de los archivos reales del código fuente (en `src/` u otros directorios de negocio).
- Explicación de componentes, hooks, estado, interfaces y funciones críticas.
- Incluye snippets de código ilustrativos.

## 6. ⚙️ Configuración y Estilos
- Explicación de la configuración de compilación, estilos (Tailwind, CSS) y herramientas de calidad de código.

## 7. 🚀 Guía de Instalación y Puesta en Marcha
- Prerrequisitos de entorno.
- Comandos paso a paso para instalación, modo desarrollo y compilación para producción.
"""


def _extract_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for p in content:
            if isinstance(p, dict):
                parts.append(p.get("text", ""))
            else:
                parts.append(str(p))
        return "".join(parts)
    return str(content)


class LLMService:
    def __init__(self):
        settings = get_settings()
        api_key = settings.gemini_api_key or os.getenv("GOOGLE_API_KEY", "")
        self.model_name = settings.gemini_model or "gemini-3.8-flash"
        self.llm = None

        if api_key:
            try:
                from langchain_google_genai import ChatGoogleGenerativeAI
                self.llm = ChatGoogleGenerativeAI(
                    model=self.model_name,
                    google_api_key=api_key,
                    temperature=0.2,
                )
                logger.info(f"Initialized Gemini model: {self.model_name}")
            except Exception as e:
                logger.warning(f"Could not initialize Gemini LLM: {e}")

    async def generate_full_architecture_docs(
        self,
        repo_url: str,
        repo_name: str,
        file_tree: str,
        manifest_content: str,
        readme_content: str,
        source_code_bundle: str,
    ) -> str:
        if self.llm:
            try:
                from langchain_core.messages import SystemMessage, HumanMessage
                prompt = DOCUMENTATION_PROMPT.format(
                    repo_url=repo_url,
                    repo_name=repo_name,
                    file_tree=file_tree,
                    manifest_content=manifest_content[:4000],
                    readme_content=readme_content[:4000] if readme_content else "Sin README provisto.",
                    source_code_bundle=source_code_bundle[:80000], # Up to ~80k chars of clean source code
                )
                response = await self.llm.ainvoke([
                    SystemMessage(content=SYSTEM_PROMPT),
                    HumanMessage(content=prompt),
                ])
                return _extract_text(response.content)
            except Exception as exc:
                logger.error(f"Error calling Gemini for full docs: {exc}", exc_info=True)

        # Fallback local in case LLM is completely unreachable
        return f"""# 📘 Documentación Técnica: {repo_name}

> Documentación básica generada por CodeScribe AI · [Repositorio]({repo_url})

## 🎯 Resumen del Proyecto
Repositorio analizado: `{repo_name}`.

## 📂 Archivos Detectados
```
{file_tree}
```
"""
