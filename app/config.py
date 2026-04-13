from pydantic import BaseModel
from dotenv import load_dotenv
import os

load_dotenv()


class Settings(BaseModel):
    app_name: str = os.getenv("APP_NAME", "Bot Bet 1x2")
    app_env: str = os.getenv("APP_ENV", "dev")
    app_host: str = os.getenv("APP_HOST", "127.0.0.1")
    app_port: int = int(os.getenv("APP_PORT", "8000"))
    
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")

    sportsdb_api_key: str = os.getenv("SPORTSDB_API_KEY", "123")
    sportsdb_base_url: str = os.getenv(
        "SPORTSDB_BASE_URL",
        "https://www.thesportsdb.com/api/v1/json",
    )
    
    

    timezone: str = os.getenv("TIMEZONE", "America/Recife")
gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

settings = Settings()