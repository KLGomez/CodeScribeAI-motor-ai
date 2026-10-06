# CodeScribe AI — AI Service (`CodeScribeAI-motor-ai`)

> **Microservicio de Inspección de Código Fuente y Generación de Documentación Técnica con FastAPI, Google GenAI SDK (Gemini) y PyGithub.**

---

## 🧠 Descripción del Servicio

El **Servicio de IA de CodeScribe** es el motor cognitivo encargado de:
- **Rastreo Eficiente mediante Git Trees API:** Indexación recursiva de árboles de directorios con una sola petición HTTP (`recursive=True`), protegiendo las cuotas de peticiones a GitHub.
- **Filtrado Semántico Anti-Ruido:** Exclusión automática de binarios, archivos de mapas, lockfiles, código compilado y dependencias externas.
- **Priorización Inteligente de Archivos:** Ordenamiento heurístico que sitúa manifiestos (`package.json`, `pyproject.toml`, etc.), puntos de entrada y lógica de negocio en la ventana de contexto prioritario.
- **Síntesis Arquitectónica con Google Gemini:** Modelos `gemini-2.5-flash` (principal) y `gemini-2.5-pro` (fallback) configurados con rol de *Senior Software Architect*, exigiendo cero transcripción de código, diagramas Mermaid interactivos y detalle de entradas/salidas/efectos.
- **Concurrencia y Resiliencia:** Control de concurrencia mediante semáforo (`MAX_CONCURRENT_ANALYSES=3`), retroceso exponencial ante rate limits de Gemini y ejecución asíncrona no bloqueante con `asyncio.to_thread`.
- **Seguridad en Red Privada:** Acceso protegido obligatoriamente por la cabecera `X-Internal-Secret`. El servicio no debe tener puertos expuestos a internet público; opera exclusivamente dentro de la red interna de contenedores.

---

## 🛠️ Stack Tecnológico

- **Framework Web:** [FastAPI](https://fastapi.tiangolo.com/) (0.115+)
- **Servidor ASGI:** [Uvicorn](https://www.uvicorn.org/) (0.34+)
- **SDK de Inteligencia Artificial:** [google-genai](https://pypi.org/project/google-genai/) (Gemini 2.5 Flash / 2.5 Pro)
- **Cliente de GitHub:** [PyGithub](https://pygithub.readthedocs.io/) (2.5+)
- **Validación y Configuración:** [Pydantic v2](https://docs.pydantic.dev/) + [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- **Linter y Pruebas:** Ruff, Pytest

---

## ⚙️ Variables de Entorno

| Variable | Tipo / Valor | Obligatoria en Prod | Descripción |
|---|---|:---:|---|
| `PORT` | `8000` | No | Puerto interno ASGI en el que escucha Uvicorn (default: `8000`). |
| `ENVIRONMENT` | `production` / `development` | **Sí** | Entorno de ejecución (habilita validaciones estrictas al iniciar). |
| `GEMINI_API_KEY` | String secreto | **Sí** | Clave de API oficial de Google AI Studio / Gemini API. |
| `GEMINI_MODEL` | `gemini-2.5-flash` | No | Modelo de lenguaje primario para generación (default: `gemini-2.5-flash`). |
| `GEMINI_FALLBACK_MODEL` | `gemini-2.5-pro` | No | Modelo de respaldo si el principal se agota (default: `gemini-2.5-pro`). |
| `AI_SERVICE_SECRET` | String (>= 16 chars) | **Sí** | Secreto requerido en la cabecera HTTP `X-Internal-Secret`. |
| `GITHUB_FALLBACK_TOKEN` | Token GitHub | No | Token de lectura para repositorios analizados sin token de usuario. |
| `ALLOWED_ORIGINS` | Lista separada por comas | **Sí** | Orígenes autorizados por CORS (en producción: URL del backend). |
| `MAX_CONCURRENT_ANALYSES` | `3` | No | Límite de análisis simultáneos para proteger memoria y cuotas. |
| `MAX_SOURCE_FILES` | `20` | No | Máximo de archivos fuente incluidos en el prompt de contexto. |
| `MAX_CHARS_PER_FILE` | `6000` | No | Límite de caracteres capturados por archivo individual. |
| `MAX_BUNDLE_CHARS` | `80000` | No | Tamaño máximo en caracteres del paquete total enviado al LLM. |

---

## 📡 Endpoints del Servicio

| Verbo | Ruta | Cabecera Requerida | Descripción |
|---|---|:---:|---|
| `GET` | `/health` | Ninguna | Diagnóstico de salud, modelo de Gemini configurado y estado de la API. |
| `POST` | `/analyze` | `X-Internal-Secret` | Analiza el repositorio de GitHub y genera la documentación técnica. |

### Contrato de Respuesta `POST /analyze`:
```json
{
  "documentation": "# Arquitectura del Sistema...",
  "filesAnalyzed": 14,
  "filesTotal": 42,
  "truncated": false
}
```

En caso de error, responde con formato tipificado:
```json
{
  "detail": {
    "code": "REPO_NOT_FOUND",
    "message": "El repositorio solicitado no existe o es privado."
  }
}
```

---

## 🔍 Alcance y Límites del Análisis

- **Capacidad de Contexto:** El servicio procesa hasta un máximo de **20 archivos prioritarios** con un tope de **6.000 caracteres por archivo** y un límite acumulado de **80.000 caracteres**. Repositorios que superen estos límites serán documentados con base en los archivos más críticos de su arquitectura, marcando la propiedad `truncated: true`.
- **Aislamiento de Red:** Este contenedor no expone puertos públicos. Se comunica exclusivamente a través de la red privada interna de Docker con el contenedor del Backend.

---

## 🚀 Puesta en Marcha Local

### 1. Crear y Activar Entorno Virtual
```bash
python -m venv .venv

# En Windows:
.venv\Scripts\activate

# En Linux / macOS:
source .venv/bin/activate
```

### 2. Instalar Dependencias
```bash
pip install -r requirements.txt -r requirements-dev.txt
```

### 3. Iniciar Servidor ASGI
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 🧪 Pruebas y Calidad de Código

```bash
# Ejecutar suite de pruebas con Pytest
pytest -q

# Validar estilo y sintaxis con Ruff
ruff check .

# Compilación y verificación de contenedor Docker (no-root)
docker build -t codescribe-ai .
```
