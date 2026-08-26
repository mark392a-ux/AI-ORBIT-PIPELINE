"""Central configuration, loaded from environment variables (.env)."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    github_token: str | None = os.getenv("GITHUB_TOKEN")
    huggingface_token: str | None = os.getenv("HUGGINGFACE_TOKEN")
    youtube_api_key: str | None = os.getenv("YOUTUBE_API_KEY")

    request_timeout: int = int(os.getenv("REQUEST_TIMEOUT", "15"))
    max_retries: int = int(os.getenv("MAX_RETRIES", "4"))

    target_total_records: int = int(os.getenv("TARGET_TOTAL_RECORDS", "280"))
    recent_days_threshold: int = int(os.getenv("RECENT_DAYS_THRESHOLD", "30"))

    data_dir: str = os.getenv("DATA_DIR", "data")
    raw_dir: str = os.getenv("RAW_DIR", "data/raw")


CONFIG = Config()
