"""Pydantic models for Browser Automation API."""

from typing import List, Optional, Union

from pydantic import BaseModel, Field


class TaskRequest(BaseModel):
    """Browser automation task request."""

    # Task description
    task: str = Field(..., description="Task for the agent to perform")
    task_id: Optional[str] = Field(
        default=None,
        description="Client-generated task ID for cancellation support"
    )

    # LLM configuration
    llm_provider: str = Field(
        default="gemini",
        description="LLM provider: browseruse, gemini, openai, anthropic",
    )
    llm_model: Optional[str] = Field(
        default=None,
        description="Model name (uses provider default if not set)",
    )

    # Page extraction LLM (optional, can be smaller/faster)
    page_extraction_llm_provider: Optional[str] = Field(
        default=None,
        description="LLM provider for page extraction (defaults to main LLM)",
    )
    page_extraction_llm_model: Optional[str] = Field(
        default=None,
        description="Model for page extraction",
    )

    # Agent settings
    use_vision: Union[str, bool] = Field(
        default="auto",
        description="Vision mode: 'auto', true, or false",
    )
    max_steps: int = Field(
        default=100,
        ge=1,
        le=500,
        description="Maximum agent steps",
    )
    generate_gif: bool = Field(
        default=False,
        description="Generate GIF of agent actions",
    )
    timeout: int = Field(
        default=900,
        ge=30,
        le=1800,
        description="Task timeout in seconds",
    )
    llm_timeout: int = Field(
        default=120,
        ge=30,
        le=600,
        description="Timeout for individual LLM calls in seconds (default: 120)",
    )
    step_timeout: int = Field(
        default=120,
        ge=30,
        le=600,
        description="Timeout for each agent step in seconds (default: 120)",
    )
    calculate_cost: bool = Field(
        default=True,
        description="Calculate LLM usage costs"
    )
    debug_mode: bool = Field(
        default=False,
        description="Enable detailed debug logging"
    )

    # Browser settings
    headless: bool = Field(
        default=False,
        description="Run browser in headless mode (False for VNC viewing)",
    )
    window_width: int = Field(
        default=1920,
        ge=800,
        le=3840,
        description="Browser window width",
    )
    window_height: int = Field(
        default=1080,
        ge=600,
        le=2160,
        description="Browser window height",
    )

    # Conversation settings
    save_conversation: bool = Field(
        default=False,
        description="Save full conversation history"
    )
    customer_id: Optional[int] = Field(
        default=None,
        description="Customer ID for organizing files"
    )

    # Session settings
    session_enabled: bool = Field(
        default=True,
        description="Enable persistent browser session (preserves cookies, auth tokens, local storage across tasks)"
    )


class TaskResponse(BaseModel):
    """Browser automation task response."""

    task_id: str
    success: bool
    result: Optional[str] = None
    final_url: Optional[str] = None
    urls_visited: List[str] = Field(default_factory=list)
    steps_taken: int = 0
    execution_time: float = 0.0
    gif_path: Optional[str] = None
    error: Optional[str] = None
    judge_verdict: Optional[str] = Field(
        default=None,
        description="Human-readable judge evaluation of task execution (if available)",
    )
    cost: Optional[float] = None
    cost_currency: str = "USD"
    llm_calls: int = 0
    debug_data: Optional[dict] = None
    conversation_path: Optional[str] = None
    downloaded_files: List[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    display: str
    browser_use_version: str
