# Browser Automation API

A production-ready REST API that enables AI agents to autonomously control a web browser. Give it a task in plain English, and an LLM-powered agent navigates websites, fills forms, extracts data, and downloads files — all inside a Dockerized container with live VNC viewing.

Built with [FastAPI](https://fastapi.tiangolo.com/) and the [browser-use](https://github.com/browser-use/browser-use) library.

## Key Features

- **Natural language browser control** — describe what you want done, the AI agent figures out how
- **Multi-LLM support** — swap between GPT, Gemini, Claude, or the browser-use optimized model
- **Session persistence** — maintain authenticated sessions (cookies, localStorage) across tasks
- **Live visual debugging** — watch the browser in real-time via VNC or noVNC web viewer
- **Cost tracking** — monitor token usage and API costs per task
- **Customer isolation** — separate sessions, downloads, and conversation logs per customer
- **Task cancellation** — cancel long-running tasks mid-execution
- **GIF recording** — capture animated recordings of agent actions

## Architecture

```
POST /execute  {"task": "...", "llm_provider": "gemini"}
       │
       ▼
┌─────────────────────────────────────────────────────┐
│  FastAPI Server (browser_api.py)                    │
│    ├── Request validation (Pydantic models)         │
│    ├── Timeout management                           │
│    └── Response assembly                            │
├─────────────────────────────────────────────────────┤
│  Agent Runner (agent_runner.py)                     │
│    ├── LLM initialization (llm_factory.py)          │
│    ├── Browser session setup (agent_setup.py)       │
│    ├── Agent execution (browser-use)                │
│    └── Result processing (result_processing.py)     │
├─────────────────────────────────────────────────────┤
│  Infrastructure (Docker)                            │
│    ├── Chromium browser                             │
│    ├── Xvfb (virtual display)                       │
│    ├── VNC + noVNC (remote viewing)                 │
│    └── Supervisor (process management)              │
└─────────────────────────────────────────────────────┘
```

The service runs as a single Docker container with multiple coordinated processes managed by Supervisor: a virtual X server, a window manager, VNC server, noVNC web proxy, and the FastAPI application.

## Quick Start

### Prerequisites

- Docker
- At least one LLM API key (Gemini has a free tier)

### Run the container

```bash
docker build -t browser-automation ./browser-automation

docker run -d \
  -p 8001:8001 \
  -p 5900:5900 \
  -p 6080:6080 \
  -e GOOGLE_API_KEY=your_key_here \
  -v ./storage-auth:/storage/auth \
  -v ./storage-browser-downloads:/home/browseruser/Downloads \
  -v ./storage-browser-conversations:/home/browseruser/.conversations \
  --name browser-automation \
  browser-automation
```

### Execute a task

```bash
curl -X POST http://localhost:8001/execute \
  -H "Content-Type: application/json" \
  -d '{
    "task": "Go to Hacker News and get the titles of the top 5 posts",
    "llm_provider": "gemini",
    "max_steps": 20
  }'
```

### Watch it work

Open http://localhost:6080 in your browser to watch the AI agent navigate in real-time via noVNC.

## API Reference

### `POST /execute`

Run a browser automation task.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `task` | string | *required* | Natural language task description |
| `llm_provider` | string | `"gemini"` | LLM provider: `gemini`, `openai`, `anthropic`, `browseruse` |
| `llm_model` | string | provider default | Specific model name |
| `max_steps` | int | `100` | Maximum agent steps (1-500) |
| `timeout` | int | `900` | Task timeout in seconds (30-1800) |
| `use_vision` | string/bool | `"auto"` | Vision mode: `"auto"`, `true`, `false` |
| `session_enabled` | bool | `true` | Persist cookies/auth across tasks |
| `customer_id` | int | `null` | Isolate sessions and files per customer |
| `generate_gif` | bool | `false` | Record agent actions as GIF |
| `debug_mode` | bool | `false` | Return detailed debug data |
| `save_conversation` | bool | `false` | Save full conversation history |
| `headless` | bool | `false` | Run browser headless (disable for VNC) |

**Response** includes: `success`, `result`, `urls_visited`, `steps_taken`, `execution_time`, `cost`, `downloaded_files`, and more.

### `GET /health`

Returns service status and browser-use library version.

### `GET /providers`

Lists available LLM providers with default models and required API keys.

### `POST /cancel/{task_id}`

Cancel a running task by ID.

## Supported LLM Providers

| Provider | Default Model | API Key Variable | Notes |
|----------|---------------|------------------|-------|
| **Gemini** | `gemini-flash-latest` | `GOOGLE_API_KEY` | Free tier available, recommended for testing |
e **OpenAI** | `gpt-4o` | `OPENAI_API_KEY` | GPT models |
| **Anthropic** | `claude-sonnet` | `ANTHROPIC_API_KEY` | Claude models |
| **browser-use** | `browseruse-default` | `BROWSER_USE_API_KEY` | Optimized for browser automation |

## Session Persistence

The service persists browser sessions (cookies, localStorage, sessionStorage) using Chrome-compatible `storage_state` files. This allows tasks to maintain authenticated sessions across multiple requests.

- **With `customer_id`** — each customer gets isolated session storage
- **Without `customer_id`** — sessions use a shared default profile
- **`session_enabled: false`** — fresh browser session every task

Session data is stored as lightweight JSON files (~15KB) and is compatible with Chrome 136+.

## Visual Access

| Method | URL | Description |
|--------|-----|-------------|
| noVNC (web) | http://localhost:6080 | Watch in any browser |
| VNC direct | `localhost:5900` | Connect with a VNC client |

Set `VNC_PASSWORD` environment variable to protect access.

## Project Structure

```
browser-automation/
├── browser_api.py          # FastAPI endpoints and request handling
├── agent_runner.py         # Task execution orchestration
├── agent_setup.py          # LLM, browser, and agent initialization
├── llm_factory.py          # Multi-provider LLM factory
├── models.py               # Pydantic request/response schemas
├── result_processing.py    # Download handling, cost extraction, debug data
├── logging_config.py       # Dual-output logging (stdout + rotating file)
├── utils.py                # Error detection helpers
├── Dockerfile              # Multi-service container setup
├── supervisord.conf        # Process management configuration
├── entrypoint.sh           # Container startup and initialization
└── requirements.txt        # Python dependencies
```

## Tech Stack

- **Python 3.11** — runtime
- **FastAPI + Uvicorn** — async HTTP API
- **browser-use** — LLM-powered browser automation
- **Pydantic v2** — request/response validation
- **Chromium** — headless browser
- **Docker** — containerization
- **Supervisor** — multi-process management
- **Xvfb + x11vnc + noVNC** — virtual display and remote viewing

## License

MIT
