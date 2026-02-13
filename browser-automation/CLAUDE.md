# CLAUDE.md

## Browser Automation Container

Isolated FastAPI service for browser automation tasks using the `browser-use` library. Runs in its own Docker container with VNC/noVNC visual access and provides HTTP API for executing browser automation tasks with multiple LLM providers.

## Architecture Overview

**Core Pipeline**: Request → LLM Setup → Browser Profile Setup → Agent Creation → Task Execution → Result Processing

### Layer 1: API Entry Point (`browser_api.py`)
- FastAPI application with three endpoints:
  - `POST /execute` - Execute browser automation task (returns `TaskResponse`)
  - `GET /health` - Health check with browser-use version
  - `GET /providers` - List available LLM providers
- Handles request logging, timeout management, and response assembly
- Returns structured JSON with task results, URLs visited, costs, and debug data

### Layer 2: Task Execution (`agent_runner.py`)
- Orchestrates the complete task execution flow:
  1. LLM initialization via `llm_factory`
  2. Directory structure setup (conversations, downloads, task directories)
  3. Browser profile initialization (for session persistence)
  4. Browser and Agent creation
  5. Agent execution with `await agent.run(max_steps)`
  6. Result post-processing (downloads, cost calculation, debug extraction)

### Layer 3: Agent Setup (`agent_setup.py`)
- **`setup_llms(request)`** - Creates main LLM and optional page extraction LLM
- **`setup_directories(request)`** - Creates customer-specific subdirectories:
  - Conversations: `/home/browseruser/.conversations/customer_{id}/`
  - Downloads: `/home/browseruser/Downloads/customer_{id}/task_{id}/`
  - Stores conversation JSON if `save_conversation=True`
- **`setup_browser_profile(request)`** - Manages persistent browser sessions:
  - **Enabled with customer_id**: `~/.browser-sessions/customer_{id}/profile` (isolated per customer)
  - **Enabled without customer_id**: `~/.browser-sessions/Default` (shared across all users)
  - **Disabled**: Temporary profile per task (cleared after execution)
- **`create_browser(request, download_dir, browser_profile_dir)`** - Browser configuration:
  - Window size (default 1920x1080, configurable)
  - Headless mode toggle (False default for VNC viewing)
  - Sandbox disabled for Docker compatibility
  - Element highlighting enabled for AI perception
  - Download path set to task directory
- **`create_agent(request, llm, ...)`** - Agent initialization with:
  - Task description
  - Main and optional page extraction LLMs
  - Vision capability (auto/true/false)
  - GIF generation (saved to task directory)
  - Cost calculation flag
  - File write restrictions to download directory

### Layer 4: LLM Factory (`llm_factory.py`)
- Factory function for native browser-use LLM classes (no Langchain):
  - `ChatBrowserUse` - Optimized for browser-use (requires `BROWSER_USE_API_KEY`)
  - `ChatGoogle` - Gemini models (requires `GOOGLE_API_KEY`)
  - `ChatOpenAI` - GPT models (requires `OPENAI_API_KEY`)
  - `ChatAnthropic` - Claude models (requires `ANTHROPIC_API_KEY`)
- Defaults to Gemini if provider unknown (free tier available)
- Temperature hardcoded to 0.0 for deterministic output

### Layer 5: Data Models (`models.py`)
- **`TaskRequest`** - Input validation:
  - Task and LLM configuration (provider, model, page extraction LLM)
  - Agent settings (max_steps, generate_gif, timeout, vision mode)
  - Browser settings (headless, window dimensions)
  - Persistence settings (session_enabled, save_conversation, customer_id)
  - Debug mode for detailed logging
- **`TaskResponse`** - Structured output:
  - Success status, final result, URLs visited
  - Execution time, steps taken, GIF path
  - Cost data (amount, currency, LLM calls)
  - Error messages, debug data, conversation path
  - Downloaded files list

### Layer 6: Result Processing (`result_processing.py`)
- **`handle_downloads()`** - Works around Chromium CDP download limitation:
  - Detects browser-use temp downloads in `/tmp/browser_use_agent_*/`
  - Moves files to task download directory
  - Handles filename conflicts with timestamp suffixes
  - Returns relative paths from `/home/browseruser/Downloads/`
- **`extract_basic_results()`** - Gets final result, completion status, visited URLs, errors, step count
- **`extract_cost_data()`** - Extracts token counts and cost from `history.usage`
- **`extract_debug_data()`** - In debug mode, extracts extracted_content, model_thoughts, performance metrics
- **`assemble_final_result()`** - Merges all data sources into single response dict

### Layer 7: Infrastructure
- **`Dockerfile`** - Multi-service container setup:
  - Base: `browseruse/browseruse:latest` (includes browser-use + virtual X server)
  - Additional services: Xvfb, fluxbox WM, x11vnc, noVNC, supervisord
  - Exposes: 5900 (VNC), 6080 (noVNC web), 8001 (API)
  - Health check: `curl http://localhost:8001/health`
- **`supervisord.conf`** - Process management (Xvfb, fluxbox, x11vnc, noVNC, FastAPI)
- **`entrypoint.sh`** - Container startup:
  - Sets up X11 display and dbus
  - Creates/permissions directory structure (conversations, sessions, downloads)
  - Creates symbolic links for browser-use config
  - Configures fluxbox window manager
  - Verifies volume mounts

## Key Design Decisions

### Session Persistence Strategy (Chrome 136+ Compatible)
- **Implementation**: Uses `storage_state` approach instead of `user_data_dir` to bypass Chrome CDP security restrictions
- **Per-customer isolation**: Each customer gets separate `storage_state.json` file in `/storage/auth/customer_{id}/`
- **Shared default**: When enabled without customer_id, uses `/storage/auth/default/storage_state.json`
- **Stateless mode**: When disabled, no storage_state saved (fresh session each time)
- **Browser lifecycle**: `keep_alive=True` keeps CDP connection active → export storage_state → explicit `browser.stop()`
- **Storage format**: Lightweight JSON files (~15KB) containing cookies, localStorage, sessionStorage
- **Chrome 136+ fix**: No `user_data_dir` means no CDP blocking on reused profiles

### Download Handling Workaround
Browser-use ignores the `downloads_path` parameter due to Chromium CDP limitation (see playwright issue #23776). Solution: detect temp downloads in `/tmp` and move to target directory after task completion.

### LLM Flexibility
- Native browser-use LLM classes avoid Langchain dependency and overhead
- Temperature fixed at 0.0 to ensure deterministic agent behavior
- Fallback to Gemini (free tier) for unknown providers

### File Organization
- Customer-scoped downloads: `Downloads/customer_{id}/task_{id}/`
- Customer-scoped conversations: `.conversations/customer_{id}/`
- Customer-scoped sessions: `/storage/auth/customer_{id}/storage_state.json` (persistent authentication)
- Task directories created with 8-character hex identifiers for uniqueness

### Result Success Logic
Task marked successful if:
1. `is_successful()` returns True explicitly, OR
2. `is_done()` returns True (task marked complete), OR
3. Has final_result AND no errors

## Common Development Tasks

### Testing the API
```bash
# Health check
curl http://localhost:8001/health

# List providers
curl http://localhost:8001/providers
```

### Visual Access
- **VNC**: Connect to `localhost:5900` with VNC viewer (no password by default)
- **noVNC Web**: Open http://localhost:6080 in browser (no password by default)
- **VNC Password**: Set `VNC_PASSWORD` environment variable before startup

### Debugging
- Enable `debug_mode=true` in TaskRequest for detailed logging
- Logs written to stdout (configured in supervisor)
- Conversation history saved as JSON if `save_conversation=true`
- Browser GIF generated if `generate_gif=true` (large files, use sparingly)

### Adding a New LLM Provider
1. Add provider to `LLMProvider` type in `llm_factory.py`
2. Implement `create_llm()` branch with native browser-use class
3. Update default model in `get_default_model()`
4. Update `/providers` endpoint documentation in `browser_api.py`
5. Document required environment variable (API key)

## File Size Guidelines
Keep Python files under 200 lines. Current state:
- `browser_api.py`: 205 lines (at limit, consider splitting if adding features)
- `agent_setup.py`: 169 lines (good)
- `result_processing.py`: 193 lines (good)
- `agent_runner.py`: 60 lines (good)
- `llm_factory.py`: 82 lines (good)
- All others well under limit

## Important Notes

### Volume Mount Points (for persistence)
```
Host Path                          Container Path
./storage-browser-conversations    →   /home/browseruser/.conversations  (conversation history)
./storage-auth                     →   /storage/auth                     (storage_state.json files)
./storage-browser-downloads        →   /home/browseruser/Downloads       (downloaded files)
./storage-common                   →   /storage                          (common storage)
```

**Note:** Session persistence now uses `storage_state` files (Chrome 136+ compatible) instead of full browser profiles. Each customer gets an isolated `storage_state.json` containing cookies, localStorage, and sessionStorage.
