from dataclasses import dataclass, field


@dataclass
class RuntimeState:
    last_input_used_vision: bool = False
    vision_followup_turns_left: int = 0
    last_user_input: str | None = None
    last_assistant_text: str | None = None
    last_screenshot_path: str | None = None
    last_editor_file_path: str | None = None
    last_created_code_file: str | None = None
    last_rate_limit_wait_text: str | None = None
    last_provider_used: str = "groq"
    last_browser_action: dict = field(default_factory=lambda: {"target": None, "time": 0.0})
    pending_name: str | None = None
    pending_age: str | None = None

