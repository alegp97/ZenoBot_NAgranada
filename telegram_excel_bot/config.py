import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


def _parse_bool(v: str | None, default: bool = False) -> bool:
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "y", "on"}


def _parse_int_set(csv: str | None) -> set[int]:
    if not csv:
        return set()
    out: set[int] = set()
    for part in csv.split(","):
        p = part.strip()
        if p:
            out.add(int(p))
    return out


@dataclass(frozen=True)
class Settings:
    telegram_token: str
    excel_path: str
    excel_sheet: str
    allowed_chat_ids: set[int]
    disable_auth: bool
    openai_api_key: str
    openai_model: str
    env_path: str
    admin_chat_id: int | None


def get_settings() -> Settings:
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not telegram_token:
        raise RuntimeError("Falta TELEGRAM_BOT_TOKEN en .env")

    excel_path = os.getenv("EXCEL_PATH", "./data/catalogo.xlsx").strip()
    excel_sheet = os.getenv("EXCEL_SHEET", "Catalogo").strip()

    allowed_chat_ids = _parse_int_set(os.getenv("ALLOWED_CHAT_IDS", "").strip())
    disable_auth = _parse_bool(os.getenv("DISABLE_AUTH", "false"), default=False)

    openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not openai_api_key:
        raise RuntimeError("Falta OPENAI_API_KEY en .env")

    openai_model = os.getenv("OPENAI_MODEL", "gpt-5.2-mini").strip()

    admin_chat_ids_raw = os.getenv("ADMIN_CHAT_IDS", "").strip()
    admin_chat_ids = int(admin_chat_ids_raw) if admin_chat_ids_raw else None

    env_path = os.getenv("ENV_PATH", ".env")

    return Settings(
        telegram_token=telegram_token,
        excel_path=excel_path,
        excel_sheet=excel_sheet,
        allowed_chat_ids=allowed_chat_ids,
        disable_auth=disable_auth,
        openai_api_key=openai_api_key,
        openai_model=openai_model,
        admin_chat_id=admin_chat_ids,
        env_path=env_path,
    )
