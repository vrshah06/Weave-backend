import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

DEFAULT_MESSAGE_TEMPLATE = (
    "This is a friendly reminder that you have an appointment scheduled on {appointment_date} "
    "at {appointment_time} with {business_name}.\n\n"
    "Should you need to reschedule or have any questions, please do not hesitate to contact us.\n\n"
    "Thank you for choosing {business_name}. We look forward to seeing you!\n\n"
    "Reply STOP to unsubscribe."
)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value else default


def _env_list(name: str, default: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


@dataclass(frozen=True)
class AppConfig:
    environment: str = field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))

    mongodb_uri: str = field(default_factory=lambda: os.getenv("MONGODB_URI", "mongodb://localhost:27017/weave_automation"))
    api_key: str = field(default_factory=lambda: os.getenv("API_KEY", ""))
    cors_origins: list[str] = field(default_factory=lambda: _env_list("CORS_ORIGINS", os.getenv("FRONTEND_URL", "*")))

    default_business_name: str = field(default_factory=lambda: os.getenv("BUSINESS_NAME", "MD Primary Care Inc."))
    default_time_zone: str = field(default_factory=lambda: os.getenv("TIME_ZONE", "America/New_York"))

    weave_email: str = field(default_factory=lambda: os.getenv("WEAVE_EMAIL", ""))
    weave_password: str = field(default_factory=lambda: os.getenv("WEAVE_PASSWORD", ""))
    weave_app_url: str = field(default_factory=lambda: os.getenv("WEAVE_APP_URL", "https://app.getweave.com"))
    weave_messages_url: str = field(default_factory=lambda: os.getenv("WEAVE_MESSAGES_URL", "https://app.getweave.com/messages/inbox"))

    browser_headless: bool = field(default_factory=lambda: _env_bool("HEADLESS", True))
    browser_slow_mo_ms: int = field(default_factory=lambda: _env_int("SLOW_MO_MS", 0))
    browser_timeout_ms: int = field(default_factory=lambda: _env_int("BROWSER_TIMEOUT_MS", 20000))
    browser_profile_dir: Path = field(default_factory=lambda: Path(os.getenv("BROWSER_PROFILE_DIR", str(BASE_DIR / "weave-profile"))))

    # Real SMS are only sent when this is explicitly enabled on the worker.
    sending_enabled: bool = field(default_factory=lambda: _env_bool("SENDING_ENABLED", False))
    worker_poll_interval_seconds: int = field(default_factory=lambda: _env_int("WORKER_POLL_INTERVAL_SECONDS", 3))
    worker_heartbeat_interval_seconds: int = field(default_factory=lambda: _env_int("WORKER_HEARTBEAT_INTERVAL_SECONDS", 10))
    worker_lock_ttl_seconds: int = field(default_factory=lambda: _env_int("WORKER_LOCK_TTL_SECONDS", 60))
    worker_max_consecutive_errors: int = field(default_factory=lambda: _env_int("WORKER_MAX_CONSECUTIVE_ERRORS", 3))


config = AppConfig()
