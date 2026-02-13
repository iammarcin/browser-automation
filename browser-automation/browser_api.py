"""Browser Automation API - Native browser-use implementation.

This API runs inside the dedicated browser-automation container and provides
endpoints for executing browser automation tasks using the browser-use library.

Key features:
- Native browser-use LLM classes (no Langchain!)
- Configurable agent parameters (use_vision, max_steps, generate_gif)
- Configurable browser parameters (window_size, headless)
- Rich response with execution history
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import time
import uuid
from typing import Dict, List, Optional

from fastapi import FastAPI

from llm_factory import create_llm

from models import TaskRequest, TaskResponse, HealthResponse
from agent_runner import run_agent_task
from logging_config import setup_logging
from utils import format_openai_error_message

# Global registry of active tasks
active_tasks: Dict[str, "BrowserTask"] = {}


class BrowserTask:
    """Track active browser automation task."""

    def __init__(self, task_id: str, agent):
        self.task_id = task_id
        self.agent = agent
        self.browser_process = None
        self.status = "running"
        self.partial_result = None
        self.cancelled = False

    def cancel(self):
        """Cancel this task."""
        self.cancelled = True
        self.status = "cancelled"

        # Kill browser if running
        if self.browser_process:
            try:
                self.browser_process.send_signal(signal.SIGTERM)
                logger.info("Sent SIGTERM to browser process")
            except Exception as exc:
                logger.warning("Failed to kill browser: %s", exc)

    def get_partial_result(self) -> Optional[str]:
        """Get any partial results collected before cancellation."""
        if self.agent:
            # Extract partial state from agent
            return self.agent.get_current_state()
        return self.partial_result


# Configure logging once at module import
setup_logging()

logger = logging.getLogger(__name__)
logger.info("Browser API initialized")

app = FastAPI(
    title="Browser Automation API",
    version="2.0.0",
    description="Browser automation using native browser-use library",
)


# --- API Endpoints ---

@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    try:
        import browser_use
        version = getattr(browser_use, "__version__", "unknown")
    except Exception:
        version = "unknown"

    return HealthResponse(
        status="healthy",
        display=os.environ.get("DISPLAY", "not set"),
        browser_use_version=version,
    )


@app.post("/execute", response_model=TaskResponse)
async def execute_task(request: TaskRequest) -> TaskResponse:
    """Execute a browser automation task."""
    task_id = request.task_id or f"browser_{uuid.uuid4().hex[:12]}"
    start_time = time.time()

    logger.info(
        "Starting task %s: %s (provider=%s, model=%s, max_steps=%d)",
        task_id,
        request.task[:100],
        request.llm_provider,
        request.llm_model or "default",
        request.max_steps,
    )

    # CRITICAL: Log ALL settings to see what's being received
    logger.info("📋 Request settings: debug_mode=%s generate_gif=%s calculate_cost=%s save_conversation=%s customer_id=%s",
                request.debug_mode, request.generate_gif, request.calculate_cost, request.save_conversation, request.customer_id)

    # ADD THIS: Log full request for debugging
    if request.debug_mode:
        logger.info("=== DEBUG: Full Request ===")
        logger.info("Task: %s", request.task[:200])
        logger.info("LLM: provider=%s model=%s", request.llm_provider, request.llm_model)
        logger.info("Agent: max_steps=%d timeout=%d use_vision=%s",
                    request.max_steps, request.timeout, request.use_vision)
        logger.info("Features: generate_gif=%s calculate_cost=%s save_conversation=%s",
                    request.generate_gif, request.calculate_cost, request.save_conversation)
        logger.info("Session: session_enabled=%s customer_id=%s",
                    request.session_enabled, request.customer_id)
        logger.info("Browser: headless=%s window=%dx%d",
                    request.headless, request.window_width, request.window_height)
        logger.info("=========================")

    try:
        # Register task before running
        browser_task = BrowserTask(task_id=task_id, agent=None)
        active_tasks[task_id] = browser_task

        # Run with timeout
        result = await asyncio.wait_for(
            run_agent_task(request),
            timeout=request.timeout,
        )

        # Check if cancelled during execution
        if browser_task.cancelled:
            logger.info("Task was cancelled during execution (task_id=%s)", task_id)
            return TaskResponse(
                task_id=task_id,
                success=False,
                error="Task cancelled",
                partial_result=browser_task.get_partial_result(),
            )

        execution_time = time.time() - start_time

        # Determine success - consider it successful if:
        # 1. is_successful() explicitly returns True, OR
        # 2. is_done() is True (task marked itself complete), OR
        # 3. We have a final_result and no critical errors
        success = result.get("is_successful")
        if success is None:
            is_done = result.get("is_done", False)
            has_result = bool(result.get("final_result"))
            has_errors = result.get("has_errors", False)
            # Success if done, or if we have results without errors
            success = is_done or (has_result and not has_errors)

        logger.info(
            "Task %s completed in %.2fs (steps=%d, success=%s)",
            task_id,
            execution_time,
            result.get("steps", 0),
            success,
        )

        # Log judge verdict if available
        if result.get("judge_verdict"):
            logger.info(
                "✅ Judge verdict available for task %s (%s)",
                task_id,
                "PASS" if "✅" in result.get("judge_verdict") else "FAIL"
            )

        if request.debug_mode:
            logger.info("=== DEBUG: Timing Breakdown ===")
            logger.info("Total execution time: %.2fs", execution_time)
            steps_taken = result.get("steps", 0) or 0
            logger.info("Steps taken: %d", steps_taken)
            if steps_taken > 0:
                logger.info("Average time per step: %.2fs", execution_time / steps_taken)
            logger.info("LLM calls: %d", result.get("llm_calls", 0))
            logger.info("===============================")

        error_messages = result.get("errors", [])
        error = None
        if error_messages:
            joined_errors = "; ".join(error_messages)
            if result.get("openai_rate_limit"):
                error = format_openai_error_message(joined_errors, "rate_limit")
                logger.warning(
                    "OpenAI rate limit detected for task %s: %s",
                    task_id,
                    error_messages[0][:150],
                )
            elif result.get("openai_empty_json"):
                error = format_openai_error_message(joined_errors, "empty_json")
                logger.warning(
                    "OpenAI empty JSON response detected for task %s: %s",
                    task_id,
                    error_messages[0][:150],
                )
            else:
                error = joined_errors

        return TaskResponse(
            task_id=task_id,
            success=success,
            result=result.get("final_result"),
            final_url=result.get("urls", [None])[-1] if result.get("urls") else None,
            urls_visited=result.get("urls", []),
            steps_taken=result.get("steps", 0),
            execution_time=execution_time,
            gif_path=result.get("gif_path"),
            error=error,
            judge_verdict=result.get("judge_verdict"),
            cost=result.get("cost"),
            cost_currency=result.get("cost_currency", "USD"),
            llm_calls=result.get("llm_calls", 0),
            debug_data=result.get("debug_data"),
            conversation_path=result.get("conversation_path"),
            downloaded_files=result.get("downloaded_files", []),
        )

    except asyncio.TimeoutError:
        execution_time = time.time() - start_time
        logger.warning("Task %s timed out after %.2fs", task_id, execution_time)
        return TaskResponse(
            task_id=task_id,
            success=False,
            error=f"Task timed out after {request.timeout} seconds",
            execution_time=execution_time,
        )

    except Exception as e:
        execution_time = time.time() - start_time
        logger.error("Task %s failed: %s", task_id, e, exc_info=True)
        return TaskResponse(
            task_id=task_id,
            success=False,
            error=str(e),
            execution_time=execution_time,
        )


@app.post("/cancel/{task_id}")
async def cancel_browser_task(task_id: str):
    """Cancel a running browser automation task."""

    logger.info("Cancel request received (task_id=%s)", task_id)

    task = active_tasks.get(task_id)
    if not task:
        logger.warning("Task not found for cancellation (task_id=%s)", task_id)
        return {
            "success": False,
            "error": "Task not found or already completed",
            "task_id": task_id,
        }

    # Cancel task
    task.cancel()

    logger.info("Browser task cancelled (task_id=%s)", task_id)

    return {
        "success": True,
        "task_id": task_id,
        "message": "Task cancelled",
        "partial_result": task.get_partial_result(),
    }


@app.get("/providers")
async def list_providers():
    """List available LLM providers and their default models."""
    return {
        "providers": {
            "browseruse": {
                "description": "Browser Use optimized LLM (fastest, recommended)",
                "default_model": "browseruse-default",
                "requires": "BROWSER_USE_API_KEY",
            },
            "gemini": {
                "description": "Google Gemini models (free tier available)",
                "default_model": "gemini-flash-latest",
                "requires": "GOOGLE_API_KEY",
            },
            "openai": {
                "description": "OpenAI GPT models",
                "default_model": "gpt-4.1-mini",
                "requires": "OPENAI_API_KEY",
            },
            "anthropic": {
                "description": "Anthropic Claude models",
                "default_model": "claude-sonnet-4-0",
                "requires": "ANTHROPIC_API_KEY",
            },
        },
        "recommended": "gemini",
        "fastest": "browseruse",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
