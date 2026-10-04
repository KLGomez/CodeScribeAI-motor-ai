# CodeScribe AI — AI Service

> **Microservicio de Inspección de Código Fuente y Generación de Documentación Técnica con FastAPI, Google GenAI SDK (Gemini) y PyGithub.**

---

## 🧠 Descripción del Servicio

El **Servicio de IA de CodeScribe** es el motor cognitivo encargado de:
- **Descarga y Rastreo de Repositorios:** Recorrido recursivo de repositorios mediante la API REST de GitHub (con soporte para acceso autenticado o anónimo).
- **Filtrado Semántico Anti-Ruido:** Exclusión automática de binarios, mapas, lockfiles, código compilado y dependencias externas.
- **Priorización Inteligente de Archivos:** Ordenamiento semántico que ubica manifiestos (`package.json`, `pyproject.toml`) y código fuente de negocio prioritario en las primeras posiciones.
- **Generación de Documentación con Google Gemini:** Ejecución de prompts con rol de *Senior Software Architect*, exigiendo cero transcripción de código, diagramas Mermaid interactivos y detalle de entradas/salidas/efectos.
- **Seguridad Interna:** Validación obligatoria de la cabecera `X-Internal-Secret` para autorizar las peticiones provenientes del backend.

---

## 🛠️ Stack Tecnológico

- **Framework Web:** [FastAPI](https://fastapi.tiangolo.com/) (>= 0.115)
- **Servidor ASGI:** [Uvicorn](https://www.uvicorn.org/) (>= 0.32)
- **SDK de Inteligencia Artificial:** [google-genai](https://pypi.org/project/google-genai/) (Gemini 3.8 Flash / 3.5 Flash)
- **Cliente de GitHub:** [PyGithub](https://pygithub.readthedocs.io/) (>= 2.5)
- **Validación de Datos:** [Pydantic v2](https://docs.pydantic.dev/) + [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)

---

## 📁 Estructura del Código

```text
app/
├── api/
│   └── routes/
│       ├── analyze.py      # Endpoint POST /analyze
│       └── health.py       # Endpoint GET /health (diagnóstico de Gemini y servicio)
├── core/
│   ├── github_client.py    # Conexión Git Trees API (recursiva, 1 request) y filtros
│   ├── prioritizer.py      # Ponderación semántica de importancia de archivos
│   └── security.py         # Verificación de cabecera X-Internal-Secret
├── schemas/
│   ├── request.py          # Modelo de entrada AnalyzeRequest
│   └── response.py         # Modelo de salida AnalyzeResponse
├── services/
│   ├── analyzer.py         # Orquestador del flujo con asyncio.to_thread
│   └── llm_service.py      # Invocación de Google Gemini y fallback de modelos
├── config.py               # Variables de entorno gestionadas por BaseSettings
└── main.py                 # Instancia de FastAPI, CORS restrictivo y lifespan
```

---

## ⚙️ Configuración del Entorno (`.env`)

Crea un archivo `.env` en la raíz de `documentador-ai-service`:

```env
PORT=8000
GEMINI_API_KEY=tu_clave_de_google_gemini
GEMINI_MODEL=gemini-2.5-flash
AI_SERVICE_SECRET=shared_secret

# Límites de análisis de repositorio
MAX_FILE_SIZE_KB=100
MAX_FILES_PER_REPO=200
```

---

## 🚀 Puesta en Marcha

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
pip install -r requirements.txt
```

### 3. Iniciar el Servidor de Desarrollo
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
El servicio estará disponible en `http://localhost:8000`.

---

## 📡 Endpoints Disponibles

| Verbo | Ruta | Cabecera | Descripción |
|---|---|---|---|
| `GET` | `/health` | Ninguna | Diagnóstico de salud, servicio y modelo de Gemini configurado |
| `POST` | `/analyze` | `X-Internal-Secret` | Analiza el repositorio de GitHub y retorna la documentación técnica en Markdown |

### Ejemplo de respuesta `/health`:
```json
{
  "status": "ok",
  "service": "ai-service",
  "gemini_model": "gemini-2.5-flash",
  "gemini_configured": true
}
```

---

## 🔍 Alcance y Límites del Análisis

- **Rastreo Eficiente vía Git Trees API:** La indexación de directorios utiliza `get_git_tree(recursive=True)` de GitHub, reduciendo las llamadas de API a una sola petición para obtener la estructura completa del árbol y evitar el agotamiento de cuotas.
- **Ventana de Contexto Focalizada:** Se seleccionan hasta **20 archivos prioritarios** (manifiestos de paquetes, puntos de entrada, controladores, servicios principales), con un tope de **6.000 caracteres por archivo**. Esto garantiza una alta densidad de información relevante para el modelo de lenguaje sin saturar la ventana de contexto ni transcribir código redundante.
- **Asincronía Real:** Todas las llamadas síncronas de PyGithub y Google GenAI se ejecutan delegadas en hilos secundarios mediante `asyncio.to_thread`, manteniendo el event loop liberado para responder a health checks y peticiones concurrentes.

---

## 🐳 Despliegue con Docker

```bash
# Construir la imagen optimizada (multi-stage con usuario sin privilegios)
docker build -t codescribe-ai-service .

# Ejecutar el contenedor
docker run -d -p 8000:8000 --env-file .env --name codescribe-ai codescribe-ai-service
```
