"""Agent execution logic for Browser Automation API."""

import json
import logging
from pathlib import Path

import sys

from agent_setup import setup_llms, setup_directories, setup_browser_profile, create_browser, create_agent, restore_session_storage
from result_processing import handle_downloads, extract_basic_results, extract_cost_data, extract_debug_data, assemble_final_result
from models import TaskRequest

# Logging configured globally in browser_api.py via logging_config module
logger = logging.getLogger(__name__)


async def export_session_storage(browser, output_path: Path):
    """Export sessionStorage from current page."""
    try:
        # Get the current page from browser-use Browser object (async method)
        page = await browser.get_current_page()
        if not page:
            logger.warning("No active page to export sessionStorage from")
            return

        # Extract sessionStorage via JavaScript evaluation
        # Note: browser-use may return JSON string instead of dict
        result = await page.evaluate("""() => {
            const data = {};
            for (let i = 0; i < sessionStorage.length; i++) {
                const key = sessionStorage.key(i);
                data[key] = sessionStorage.getItem(key);
            }
            return JSON.stringify({
                origin: window.location.origin,
                data: data
            });
        }""")

        # Parse if it's a string, otherwise use as-is
        if isinstance(result, str):
            session_storage_data = json.loads(result)
        else:
            session_storage_data = result

        # Save to JSON file
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump(session_storage_data, f, indent=2)

        logger.info("Exported %d sessionStorage items from %s",
                   len(session_storage_data.get('data', {})),
                   session_storage_data.get('origin', 'unknown'))
    except Exception as e:
        logger.warning("Failed to export sessionStorage: %s", e)


async def run_agent_task(request: TaskRequest) -> dict:
    """Execute browser automation task."""
    # Set up LLMs
    llm, page_extraction_llm = setup_llms(request)

    # Set up directories
    conversation_path, download_dir, task_dir_name = setup_directories(request)

    # Set up storage paths for session persistence
    storage_state_path, session_storage_path = setup_browser_profile(request)

    # Create browser
    browser = create_browser(request, download_dir, storage_state_path)

    # Start browser to initialize CDP client
    await browser.start()
    logger.info("Browser started and CDP client initialized")

    # Restore sessionStorage AFTER browser start (CDP client must be ready)
    if session_storage_path:
        await restore_session_storage(browser, session_storage_path)

    # Create agent
    agent, gif_path = create_agent(request, llm, page_extraction_llm, browser, download_dir, task_dir_name, conversation_path)

    try:
        # Run agent with max_steps
        history = await agent.run(max_steps=request.max_steps)

        # Persist storage_state while CDP is still active (keep_alive=True keeps it open)
        if storage_state_path:
            try:
                storage_state_path.parent.mkdir(parents=True, exist_ok=True)
                await browser.export_storage_state(output_path=str(storage_state_path))
                logger.info("Saved storage_state to %s", storage_state_path)

                # Export sessionStorage manually (Playwright doesn't include this in storage_state)
                if session_storage_path:
                    await export_session_storage(browser, session_storage_path)
                    logger.info("Saved sessionStorage to %s", session_storage_path)
            except Exception as exc:
                logger.error("Failed to save session state: %s", exc, exc_info=True)
    finally:
        # Clean up browser (since we used keep_alive=True, must close explicitly)
        try:
            await browser.stop()
            logger.info("Browser closed successfully")
        except Exception as exc:
            logger.warning("Error closing browser: %s", exc)

    # Handle downloads workaround
    downloaded_files = handle_downloads(download_dir)

    # Extract basic results
    basic_result = extract_basic_results(history, request, gif_path)

    # Extract cost data
    cost_data = extract_cost_data(history, request)

    # Extract debug data
    debug_result = extract_debug_data(history, request)

    # Assemble final result
    result = assemble_final_result(basic_result, cost_data, debug_result, downloaded_files, conversation_path)

    return result
