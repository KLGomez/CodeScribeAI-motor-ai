import logging
import os
from google import genai
from google.genai import types
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


class LLMService:
    def __init__(self):
        settings = get_settings()
        api_key = settings.gemini_api_key or os.getenv("GOOGLE_API_KEY", "")
        self.models_to_try = [settings.gemini_model, "gemini-3.5-flash-lite", "gemini-3.8-flash"]
        # Deduplicate
        self.models_to_try = list(dict.fromkeys([m for m in self.models_to_try if m]))
        self.client = None

        if api_key:
            try:
                self.client = genai.Client(api_key=api_key)
                logger.info(f"Initialized google.genai Client with models: {self.models_to_try}")
            except Exception as e:
                logger.warning(f"Could not initialize google.genai Client: {e}")

    async def generate_full_architecture_docs(
        self,
        repo_url: str,
        repo_name: str,
        file_tree: str,
        manifest_content: str,
        readme_content: str,
        source_code_bundle: str,
    ) -> str:
        prompt = DOCUMENTATION_PROMPT.format(
            repo_url=repo_url,
            repo_name=repo_name,
            file_tree=file_tree,
            manifest_content=manifest_content[:4000],
            readme_content=readme_content[:4000] if readme_content else "Sin README provisto.",
            source_code_bundle=source_code_bundle[:80000],
        )

        if self.client:
            for model_name in self.models_to_try:
                try:
                    logger.info(f"Generating architecture documentation using model {model_name}...")
                    response = self.client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=SYSTEM_PROMPT,
                            temperature=0.1,
                        ),
                    )
                    text = response.text or ""
                    if text.strip() == "[OMITIR_DOCUMENTACION]":
                        return f"# Documentación: {repo_name}\n\n*El repositorio contiene únicamente archivos de configuración o manifiestos sin lógica de negocio documentable.*"
                    if text.strip():
                        return text
                except Exception as exc:
                    logger.warning(f"Model {model_name} call failed: {exc}. Trying next model...")

        # Fallback local
        return f"""# Documentación Técnica: {repo_name}

> Documentación básica generada por CodeScribe AI · [Repositorio]({repo_url})

## Propósito General
Repositorio analizado: `{repo_name}`.

## Archivos Detectados
```
{file_tree}
```
"""
