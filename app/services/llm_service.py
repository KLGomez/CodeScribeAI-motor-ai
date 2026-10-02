import logging
import os
from google import genai
from google.genai import types
try:
    from langchain_core.prompts import PromptTemplate
except ImportError:
    from langchain.prompts import PromptTemplate
from app.config import get_settings

logger = logging.getLogger(__name__)

# ==============================================================================
# PROMPTS LANGCHAIN: MAP-REDUCE PIPELINE (ANÁLISIS ARQUITECTÓNICO Y DE NEGOCIO)
# ==============================================================================

map_template = """Actúa como un Tech Lead Senior y Arquitecto de Software. Tu tarea es analizar en profundidad el siguiente fragmento o módulo de código fuente y documentar su comportamiento técnico, flujo de datos y lógica de dominio.

CÓDIGO FUENTE DEL MÓDULO:
{text}

REGLAS ESTRICTAS DE ANÁLISIS:
1. Propósito del Módulo: Documenta con precisión cuál es la responsabilidad única del módulo y qué rol desempeña en el sistema.
2. Gestión de Estado: Explica detalladamente cómo maneja el estado interno, reactivo o global (ej. mutaciones, stores, ciclo de vida de los datos, persistencia o caché).
3. Dependencias Críticas: Identifica las dependencias arquitectónicas e integraciones clave (servicios internos, endpoints de backend, contratos de datos u otros módulos del dominio).
4. Regla de Negocio Resuelta: Describe de manera explícita qué regla, validación, cálculo o flujo de negocio implementa o resuelve este módulo.

PROHIBICIONES ESTRICTAS Y FILTRO ANTI-RUIDO:
- Está PROHIBIDO listar imports de React o librerías estándar (ej. React, useState, useEffect, lodash, utilidades genéricas). No enumeres dependencias obvias ni transcribas sintaxis básica.
- Si el archivo analizado es solo de configuración básica (ej. tsconfig, eslint, bundlers), estilos vacíos o puramente decorativos sin lógica de negocio, responde ÚNICA Y EXACTAMENTE con el siguiente token:
[OMITIR_DOCUMENTACION]
- Cero transcripción de código: no copies bloques de código fuente; tu tarea es explicar el diseño y comportamiento.

FORMATO DE SALIDA:
Genera un análisis técnico en Markdown estructurado, directo y profesional, sin preámbulos ni despedidas."""

map_prompt = PromptTemplate(
    template=map_template,
    input_variables=["text"],
)

reduce_template = """Actúa como el Chief Technology Officer (CTO) de una compañía de software de alto impacto. Tu misión es sintetizar los análisis técnicos modulares que se presentan a continuación para generar un Resumen Ejecutivo y Arquitectónico integral del producto.

ANÁLISIS MODULARES PREVIOS:
{text}

REGLAS ESTRICTAS DE SÍNTESIS:
1. Propósito General del Producto: Deduce y define con visión de negocio y producto la naturaleza de la solución (ej. SaaS de finanzas gamificado, plataforma e-commerce B2B, gestor colaborativo en tiempo real), explicando qué necesidad de mercado resuelve y su propuesta de valor.
2. Arquitectura de Alto Nivel: Describe la arquitectura global del sistema, los patrones de diseño predominantes (ej. Arquitectura Limpia, Modular, Event-Driven, Microfrontends), la separación entre capas y la interacción entre subsistemas.
3. Flujos Principales del Sistema: Explica en detalle los flujos troncales del negocio y de datos (ej. Autenticación y Autorización, Gestión de Estado Global, Ciclo de Ingesta y Sincronización de Datos, etc.).

PROHIBICIÓN ABSOLUTA:
ESTÁ ESTRICTAMENTE PROHIBIDO generar listas crudas de archivos o rutas (como .tsx, .ts, .md). Tu tarea es abstraer y explicar, no listar.

FORMATO Y ESTILO:
- Utiliza Markdown estructurado y jerárquico, priorizando claridad técnica, visión estratégica y síntesis de alto valor.
- Evita introducciones robóticas como "Aquí tienes el resumen", "A continuación presento...", saludos o despedidas. Comienza directamente con el encabezado ejecutivo y el análisis técnico."""

reduce_prompt = PromptTemplate(
    template=reduce_template,
    input_variables=["text"],
)


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
