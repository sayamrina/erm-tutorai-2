from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Without a key the app runs in demo mode: keyword retrieval, no generated answers.
    openai_api_key: str = ""
    chat_model: str = "gpt-4o"
    embedding_model: str = "text-embedding-3-small"

    session_limit_per_hour: int = 20
    global_limit_per_day: int = 300


settings = Settings()
