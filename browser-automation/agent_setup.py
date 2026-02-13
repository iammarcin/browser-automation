"""Agent setup functions for Browser Automation API."""

import json
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from llm_factory import create_llm

from models import TaskRequest
from utils import normalize_use_vision

logger = logging.getLogger(__name__)


def setup_llms(request: TaskRequest) -> tuple:
    """Set up main and page extraction LLMs."""
    # Create main LLM
    llm = create_llm(
        provider=request.llm_provider,
        model=request.llm_model,
    )

    # Create page extraction LLM (optional)
    page_extraction_llm = None
    if request.page_extraction_llm_provider:
        page_extraction_llm = create_llm(
            provider=request.page_extraction_llm_provider,
            model=request.page_extraction_llm_model,
        )

    return llm, page_extraction_llm


def setup_directories(request: TaskRequest) -> tuple:
    """Set up conversation and download directories."""
    # Generate conversation path if requested
    conversation_path = None
    if request.save_conversation:
        # Create customer-specific subdirectory
        customer_dir = f"customer_{request.customer_id}" if request.customer_id else "default"
        conv_dir = Path("/home/browseruser/.conversations") / customer_dir
        conv_dir.mkdir(parents=True, exist_ok=True)

        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        task_id = uuid.uuid4().hex[:8]
        conversation_path = str(conv_dir / f"task_{task_id}_{timestamp}.json")

        logger.info("Conversation will be saved to: %s", conversation_path)

    # Create customer/task-specific download directory
    download_dir = None
    task_dir_name = None
    if request.customer_id:
        customer_dir = f"customer_{request.customer_id}"
        task_dir_name = f"task_{uuid.uuid4().hex[:8]}"
        download_dir = Path("/home/browseruser/Downloads") / customer_dir / task_dir_name
        download_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Downloads will be saved to: %s", download_dir)
    else:
        task_dir_name = f"task_{uuid.uuid4().hex[:8]}"
        download_dir = Path("/home/browseruser/Downloads") / "default" / task_dir_name
        download_dir.mkdir(parents=True, exist_ok=True)

    # Set working directory to download_dir so agent file writes go here
    os.chdir(str(download_dir))
    logger.info("Changed working directory to: %s", download_dir)

    return conversation_path, download_dir, task_dir_name


def setup_browser_profile(request: TaskRequest) -> tuple[Optional[Path], Optional[Path]]:
    """Set up storage_state and session_storage paths for session persistence."""
    if not request.session_enabled:
        logger.info("Session persistence disabled; browser will start without state")
        return None, None

    base_dir = Path("/storage/auth")
    customer_dir = base_dir / (f"customer_{request.customer_id}" if request.customer_id else "default")
    customer_dir.mkdir(parents=True, exist_ok=True)

    storage_state_path = customer_dir / "storage_state.json"
    session_storage_path = customer_dir / "session_storage.json"

    logger.info("Using storage_state file: %s", storage_state_path)
    logger.info("Using session_storage file: %s", session_storage_path)

    return storage_state_path, session_storage_path


def create_browser(request: TaskRequest, download_dir: Path, storage_state_path: Optional[Path]):
    """Create and configure the browser instance."""
    from browser_use import Browser

    storage_state = None
    if storage_state_path and storage_state_path.exists():
        storage_state = str(storage_state_path)
        logger.info("Loading existing storage_state: %s", storage_state_path)
    elif storage_state_path:
        logger.info("No storage_state file found yet at %s; starting fresh session", storage_state_path)
    else:
        logger.info("Running without storage_state; session persistence disabled")

    browser = Browser(
        headless=request.headless,
        window_size={
            "width": request.window_width,
            "height": request.window_height,
        },
        # Chrome needs these in Docker
        chromium_sandbox=False,
        # Enable for AI
        highlight_elements=True,
        # Downloads
        accept_downloads=True,
        downloads_path=str(download_dir),  # Will be ignored by browser-use, but set anyway
        # Use storage_state-based persistence to comply with Chrome 136+ restrictions
        storage_state=storage_state,
        user_data_dir=None,
        # Keep browser alive after agent completes so we can save storage_state
        keep_alive=True,
    )

    return browser


async def restore_session_storage(browser, session_storage_path: Path):
    """Restore sessionStorage to the browser using CDP init script."""
    if not session_storage_path.exists():
        logger.info("No sessionStorage file found at %s", session_storage_path)
        return

    try:
        # Load sessionStorage data
        with open(session_storage_path, 'r') as f:
            session_data = json.load(f)

        logger.info("DEBUG: Loaded session_data type: %s", type(session_data))
        logger.info("DEBUG: session_data content: %s", session_data)

        origin = session_data.get('origin')
        data = session_data.get('data', {})

        logger.info("DEBUG: origin=%s, data keys=%s", origin, list(data.keys()) if data else None)

        if not data:
            logger.info("SessionStorage file exists but contains no data")
            return

        # Inject sessionStorage restoration script BEFORE any page loads
        # Using browser-use's CDP-based init script method
        script = f"""
(function() {{
    // Only restore for matching origin
    if (window.location.origin === '{origin}') {{
        const storage = {json.dumps(data)};
        for (const [key, value] of Object.entries(storage)) {{
            window.sessionStorage.setItem(key, value);
        }}
        console.log('[BrowserAutomation] Restored ' + Object.keys(storage).length + ' sessionStorage items');
    }}
}})();
        """

        await browser._cdp_add_init_script(script)

        logger.info("Prepared sessionStorage restoration for origin: %s (%d items)",
                   origin, len(data))
    except Exception as e:
        logger.warning("Failed to restore sessionStorage: %s", e, exc_info=True)


def create_agent(request: TaskRequest, llm, page_extraction_llm, browser, download_dir: Path, task_dir_name: str, conversation_path: str = None):
    """Create and configure the agent."""
    from browser_use import Agent

    # Normalize use_vision
    use_vision = normalize_use_vision(request.use_vision)

    # Prepare agent kwargs
    agent_kwargs = {
        "task": request.task,
        "llm": llm,
        "browser": browser,
        "use_vision": use_vision,
        "calculate_cost": request.calculate_cost,
        "llm_timeout": request.llm_timeout,
        "step_timeout": request.step_timeout,
        "available_file_paths": [str(download_dir)],  # Restrict file writes to download directory
    }

    # Add conversation path if specified
    if conversation_path:
        agent_kwargs["save_conversation_path"] = conversation_path

    # Add optional parameters
    if page_extraction_llm:
        agent_kwargs["page_extraction_llm"] = page_extraction_llm

    if request.generate_gif:
        # Save GIF in the same task directory
        gif_filename = f"task_{task_dir_name}.gif"  # Use task_dir_name as ID
        gif_path = download_dir / gif_filename
        agent_kwargs["generate_gif"] = str(gif_path)

    if request.debug_mode:
        logger.info("=== DEBUG: Agent Kwargs ===")
        logger.info("Agent parameters:")
        for key, value in agent_kwargs.items():
            if key == "task":
                logger.info("  task: %s", str(value)[:100])
            else:
                logger.info("  %s: %s", key, value)
        logger.info(
            "Timeout configuration: llm_timeout=%ds, step_timeout=%ds",
            request.llm_timeout,
            request.step_timeout,
        )
        logger.info("===========================")

    # Create agent
    agent = Agent(**agent_kwargs)

    return agent, gif_path if request.generate_gif else None
