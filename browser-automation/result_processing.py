"""Result processing functions for Browser Automation API."""

import logging
from datetime import datetime
from pathlib import Path
import shutil

from models import TaskRequest
from utils import is_empty_json_error, is_rate_limit_error

logger = logging.getLogger(__name__)


def handle_downloads(download_dir: Path) -> list:
    """Handle downloads workaround for browser-use."""
    # ===== DOWNLOADS WORKAROUND (Chromium CDP Limitation) =====
    # browser-use downloads to /tmp/browser-use-downloads-* (ignores downloads_path)
    # We detect these directories and move files to our target location
    # See: https://github.com/microsoft/playwright/issues/23776

    downloaded_files = []
    tmp_download_dirs = list(Path("/tmp").glob("browser_use_agent_*/browseruse_agent_data"))

    if tmp_download_dirs:
        logger.info("Found %d browser-use download directories in /tmp", len(tmp_download_dirs))

        for tmp_dir in tmp_download_dirs:
            if not tmp_dir.exists() or not tmp_dir.is_dir():
                continue

            logger.info("Processing download directory: %s", tmp_dir)

            # Move all files from temp directory to target download directory
            for file in tmp_dir.iterdir():
                if file.is_file():
                    # Destination path
                    dest_file = download_dir / file.name

                    # Handle file name conflicts
                    if dest_file.exists():
                        # Append timestamp to avoid overwriting
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        stem = dest_file.stem
                        suffix = dest_file.suffix
                        dest_file = download_dir / f"{stem}_{timestamp}{suffix}"
                        logger.warning("File conflict, renaming: %s → %s", file.name, dest_file.name)

                    # Move file
                    try:
                        shutil.move(str(file), str(dest_file))
                        logger.info("Moved downloaded file: %s → %s", file.name, dest_file)

                        # Track relative path for response
                        relative_path = dest_file.relative_to(Path("/home/browseruser/Downloads"))
                        downloaded_files.append(str(relative_path))
                    except Exception as e:
                        logger.error("Failed to move file %s: %s", file, e)

            # Clean up temp directory
            try:
                shutil.rmtree(tmp_dir)
                logger.info("Cleaned up temp directory: %s", tmp_dir)
            except Exception as e:
                logger.warning("Failed to remove temp directory %s: %s", tmp_dir, e)
    else:
        logger.debug("No browser-use download directories found in /tmp")

    # ===== END DOWNLOADS WORKAROUND =====

    return downloaded_files


def extract_basic_results(history, request: TaskRequest, gif_path=None) -> dict:
    """Extract basic results from agent history."""
    errors = [str(e) for e in history.errors() if e]

    # Detect Claude schema validation issues for better messaging
    openai_empty_json = False
    openai_rate_limit = False
    if errors:
        if request.llm_provider == "openai":
            openai_empty_json = any(is_empty_json_error(err) for err in errors)
            openai_rate_limit = any(is_rate_limit_error(err) for err in errors)

    result = {
        "final_result": history.final_result(),
        "is_done": history.is_done(),
        "is_successful": history.is_successful(),
        "has_errors": history.has_errors(),
        "urls": history.urls(),
        "steps": history.number_of_steps(),
        "duration": history.total_duration_seconds(),
        "errors": errors,
        "openai_empty_json": openai_empty_json,
        "openai_rate_limit": openai_rate_limit,
    }

    # Extract judge verdict if available
    judge_verdict = None
    try:
        if hasattr(history, "judgement"):
            judgement_dict = history.judgement()
        else:
            judgement_dict = None

        if judgement_dict:
            judge_verdict = format_judge_verdict(judgement_dict)
            logger.info(
                "Judge verdict extracted: %s",
                "PASS" if judgement_dict.get("verdict") else "FAIL",
            )
    except Exception as e:
        logger.warning("Could not extract judge verdict: %s", e)

    result["judge_verdict"] = judge_verdict

    # Get GIF path if generated
    if request.generate_gif and gif_path:
        result["gif_path"] = str(gif_path)

    return result


def extract_cost_data(history, request: TaskRequest) -> dict:
    """Extract cost data from agent history."""
    cost_data = {}

    if request.calculate_cost:
        try:
            # Cost data is in the usage attribute
            if hasattr(history, 'usage') and history.usage:
                usage = history.usage

                # Extract cost if available
                if hasattr(usage, 'total_cost'):
                    cost_data["cost"] = float(usage.total_cost)
                    cost_data["cost_currency"] = "USD"
                elif hasattr(usage, 'cost'):
                    cost_data["cost"] = float(usage.cost)
                    cost_data["cost_currency"] = "USD"

                # Extract token counts
                if hasattr(usage, 'input_tokens') and hasattr(usage, 'output_tokens'):
                    cost_data["llm_calls"] = 1  # Will be updated if we track per-call
                    logger.info(
                        "Cost calculated: cost=%.4f, input_tokens=%d, output_tokens=%d",
                        cost_data.get("cost", 0),
                        usage.input_tokens,
                        usage.output_tokens
                    )

            # Fallback: Try to estimate from steps
            if "cost" not in cost_data or cost_data["cost"] is None:
                logger.warning("No cost data available in history.usage")
                cost_data["cost"] = None
                cost_data["llm_calls"] = history.number_of_steps()

        except Exception as e:
            logger.error("Failed to extract cost data: %s", e, exc_info=True)
            cost_data["cost"] = None
            cost_data["llm_calls"] = history.number_of_steps()
    else:
        cost_data["cost"] = None
        cost_data["llm_calls"] = 0

    return cost_data


def extract_debug_data(history, request: TaskRequest) -> dict:
    """Extract debug data from agent history."""
    if not request.debug_mode:
        return {"debug_data": None}

    logger.info("Extracting debug data for task")
    debug_data = {}

    # Extract content
    try:
        if hasattr(history, 'extracted_content'):
            extracted = history.extracted_content()
            debug_data["extracted_content"] = extracted if isinstance(extracted, list) else list(extracted)
            logger.debug("Extracted %d content items", len(debug_data["extracted_content"]))
    except Exception as e:
        logger.warning("Could not extract content: %s", e)
        debug_data["extracted_content"] = []

    # Extract model thoughts/reasoning
    try:
        if hasattr(history, 'model_thoughts'):
            thoughts = history.model_thoughts()
            # AgentBrain objects - convert to dict
            debug_data["model_thoughts"] = [
                {
                    "step": i,
                    "thought": str(thought) if hasattr(thought, '__str__') else repr(thought),
                    # Try to extract structured data if available
                    "action": getattr(thought, 'action', None),
                    "reasoning": getattr(thought, 'reasoning', None),
                }
                for i, thought in enumerate(thoughts, 1)
            ]
            logger.debug("Extracted %d reasoning steps", len(debug_data["model_thoughts"]))
    except Exception as e:
        logger.warning("Could not extract model thoughts: %s", e)
        debug_data["model_thoughts"] = []

    # Add performance metrics
    debug_data["performance"] = {
        "total_duration": history.total_duration_seconds(),
        "steps": history.number_of_steps(),
        "urls_visited": len(history.urls()),
        "has_errors": history.has_errors(),
    }

    return {"debug_data": debug_data}


def assemble_final_result(basic_result: dict, cost_data: dict, debug_data: dict, downloaded_files: list, conversation_path: str = None) -> dict:
    """Assemble the final result dictionary."""
    result = {**basic_result, **cost_data, **debug_data}
    result["downloaded_files"] = downloaded_files
    result["conversation_path"] = conversation_path

    return result


def format_judge_verdict(judgement_dict: dict) -> str:
    """Format judge verdict as human-readable text with emojis."""
    verdict = bool(judgement_dict.get("verdict"))
    verdict_emoji = "✅" if verdict else "❌"
    verdict_status = "PASS" if verdict else "FAIL"

    judge_parts = [f"⚖️  Judge Verdict: {verdict_emoji} {verdict_status}"]

    reasoning = judgement_dict.get("reasoning")
    if reasoning:
        judge_parts.append(f"Reasoning: {reasoning}")

    failure_reason = judgement_dict.get("failure_reason")
    if failure_reason:
        judge_parts.append(f"Failure Reason: {failure_reason}")

    if judgement_dict.get("impossible_task"):
        judge_parts.append("⚠️ Task was impossible to complete")

    if judgement_dict.get("reached_captcha"):
        judge_parts.append("🤖 Encountered CAPTCHA")

    return "\n".join(judge_parts)
