import logging
import os
from typing import Dict, List
from app.config import get_settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Rol: Eres un Arquitecto de Software y Technical Writer Senior. Tu objetivo es analizar código fuente y redactar documentación técnica de alto nivel orientada al comportamiento, no a la sintaxis.

REGLAS ESTRICTAS DE RESPUESTA:

1. Cero Transcripción de Código: Tienes estrictamente prohibido devolver el código fuente original. Tu trabajo es explicar la lógica, no repetirla. No incluyas bloques de código a menos que sea un ejemplo de uso muy breve e indispensable.

2. Estructura Obligatoria: Para cada módulo, componente o función principal, debes documentar:
   - **Propósito:** ¿Qué hace este módulo y qué responsabilidad tiene en el sistema?
   - **Entradas y Salidas:** Props (si es frontend), parámetros, argumentos y tipos de retorno.
   - **Gestión de Estado y Lógica:** Cómo manipula los datos o el estado interno.
   - **Dependencias y Efectos:** Con qué otros servicios, hooks, o componentes interactúa.

3. Filtro Anti-Ruido: Si el archivo o bloque corresponde a un archivo de configuración, listado de dependencias (lockfiles), variables de entorno o manifiestos que no contienen lógica de negocio, responde única y exactamente con la cadena: [OMITIR_DOCUMENTACION].

4. Diagramas de Comportamiento: Genera diagramas de flujo de datos y arquitectura en sintaxis Mermaid (```mermaid ... ```).

5. Tono y Formato: Usa Markdown limpio, con listas estructuradas y lenguaje técnico preciso. Omite saludos, introducciones o conclusiones genéricas.
"""

DOCUMENTATION_PROMPT = """Analiza el siguiente repositorio de software y redacta una Documentación Técnica de Alto Nivel orientada al comportamiento:

REPOSITORIO:
- URL: {repo_url}
- Nombre: {repo_name}

ESTRUCTURA DEL PROYECTO:
```
{file_tree}
```

MANIFIESTO / DEPENDENCIAS (package.json / pyproject.toml):
```
{manifest_content}
```

README ORIGINAL:
```
{readme_content}
```

CÓDIGO FUENTE REAL:
{source_code_bundle}

INSTRUCCIONES DE REDACCIÓN:
Genera la documentación siguiendo estrictamente este formato:

# Documentación Técnica: {repo_name}

> Documentación de arquitectura orientada al comportamiento · [Repositorio GitHub]({repo_url})

---

## 1. Propósito General del Sistema
- Descripción clara del problema que resuelve y funcionalidad central.
- Flujo principal de usuario/negocio.

## 2. Arquitectura y Flujo de Datos
- Patrón de diseño identificado.
- Diagrama conceptual en Mermaid (```mermaid graph TD o sequenceDiagram).
- Ciclo de vida y comunicación entre capas.

## 3. Stack Tecnológico y Dependencias
- Tabla técnica de tecnologías y bibliotecas clave (Tecnología | Versión | Rol en el sistema).

## 4. Mapa de Responsabilidades por Directorio
- Responsabilidad arquitectónica de cada carpeta principal del proyecto.

## 5. Análisis de Módulos y Componentes de Negocio
Para cada componente, hook, servicio o módulo de código fuente analizado (excluyendo configuración):
### `[Nombre del Módulo o Componente]`
- **Propósito:** Responsabilidad específica dentro de la aplicación.
- **Entradas y Salidas:** Props, parámetros recibidos, tipos y valores de retorno.
- **Gestión de Estado y Lógica:** Variables de estado manejadas, mutaciones, transformaciones de datos o cálculos.
- **Dependencias y Efectos:** Hooks invocados, servicios consumidos, eventos disparados y efectos secundarios.

## 6. Guía de Puesta en Marcha y Entorno
- Requisitos mínimos de entorno.
- Comandos para instalación de dependencias, modo desarrollo y compilación de producción.
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
                    temperature=0.1,
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
                    source_code_bundle=source_code_bundle[:80000],
                )
                response = await self.llm.ainvoke([
                    SystemMessage(content=SYSTEM_PROMPT),
                    HumanMessage(content=prompt),
                ])
                result_text = _extract_text(response.content)
                if result_text.strip() == "[OMITIR_DOCUMENTACION]":
                    return f"# Documentación: {repo_name}\n\n*El repositorio contiene únicamente archivos de configuración o manifiestos sin lógica de negocio documentable.*"
                return result_text
            except Exception as exc:
                logger.error(f"Error calling Gemini for behavior-oriented docs: {exc}", exc_info=True)

        return f"""# Documentación Técnica: {repo_name}

> Documentación básica generada por CodeScribe AI · [Repositorio]({repo_url})

## Propósito General
Repositorio analizado: `{repo_name}`.

## Archivos Detectados
```
{file_tree}
```
"""
