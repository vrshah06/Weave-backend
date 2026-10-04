import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"
SCREENSHOT_DIR = LOG_DIR / "screenshots"
PROFILE_DIR = BASE_DIR / "weave-profile"

LOG_DIR.mkdir(parents=True, exist_ok=True)
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

CORS_ORIGINS = [
    o.strip() for o in os.getenv("CORS_ORIGINS", os.getenv("FRONTEND_URL", "*")).split(",") if o.strip()
]

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/weave_automation")

WEAVE_EMAIL = os.getenv("WEAVE_EMAIL", "")
WEAVE_PASSWORD = os.getenv("WEAVE_PASSWORD", "")

WEAVE_APP_URL = os.getenv("WEAVE_APP_URL", "https://app.getweave.com")
WEAVE_MESSAGES_URL = os.getenv("WEAVE_MESSAGES_URL", "https://app.getweave.com/messages/inbox")

headless_env = os.getenv("HEADLESS", "True" if os.name != "nt" or os.getenv("NODE_ENV") == "production" else "False").lower()
HEADLESS = headless_env in ("true", "1", "t", "yes")
SLOW_MO = int(os.getenv("SLOW_MO", "100"))
DEFAULT_TIMEOUT = int(os.getenv("DEFAULT_TIMEOUT", "15000"))
SEARCH_TIMEOUT = int(os.getenv("SEARCH_TIMEOUT", "20000"))
MESSAGE_LOAD_TIMEOUT = int(os.getenv("MESSAGE_LOAD_TIMEOUT", "30000"))
SCREENSHOT_ON_ERROR = os.getenv("SCREENSHOT_ON_ERROR", "True").lower() in ("true", "1", "t")

BUSINESS_NAME = os.getenv("BUSINESS_NAME", "MD Primary Care Inc.")

DEFAULT_MESSAGE_TEMPLATE = (
    "This is a friendly reminder that you have an appointment scheduled on {appointment_date} "
    "at {appointment_time} with {business_name}.\n\n"
    "Should you need to reschedule or have any questions, please do not hesitate to contact us.\n\n"
    "Thank you for choosing {business_name}. We look forward to seeing you!\n\n"
    "Reply STOP to unsubscribe."
)

REMINDER_LOG_PATH = LOG_DIR / "reminder_log.csv"
APPLICATION_LOG_PATH = LOG_DIR / "application.log"
