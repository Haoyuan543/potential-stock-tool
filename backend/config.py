from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8-sig", extra="ignore")

    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-5.5", alias="OPENAI_MODEL")
    finmind_token: str = Field(default="", alias="FINMIND_TOKEN")
    news_api_key: str = Field(default="", alias="NEWS_API_KEY")
    serpapi_api_key: str = Field(default="", alias="SERPAPI_API_KEY")
    tavily_api_key: str = Field(default="", alias="TAVILY_API_KEY")
    brave_search_api_key: str = Field(default="", alias="BRAVE_SEARCH_API_KEY")
    default_ticker: str = Field(default="2603", alias="DEFAULT_TICKER")
    request_timeout: float = 8.0
    openai_timeout_seconds: float = Field(default=180.0, alias="OPENAI_TIMEOUT_SECONDS")
    openai_max_output_tokens: int = Field(default=4000, alias="OPENAI_MAX_OUTPUT_TOKENS")
    cron_job_secret: str = Field(default="", alias="CRON_JOB_SECRET")
    dashboard_username: str = Field(default="admin", alias="DASHBOARD_USERNAME")
    dashboard_password: str = Field(default="", alias="DASHBOARD_PASSWORD")
    storage_backend: str = Field(default="local", alias="STORAGE_BACKEND")
    supabase_url: str = Field(default="", alias="SUPABASE_URL")
    supabase_service_role_key: str = Field(default="", alias="SUPABASE_SERVICE_ROLE_KEY")
    supabase_records_table: str = Field(default="potential_stock_records", alias="SUPABASE_RECORDS_TABLE")
    smtp_host: str = Field(default="", alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_user: str = Field(default="", alias="SMTP_USER")
    smtp_password: str = Field(default="", alias="SMTP_PASSWORD")
    smtp_starttls: bool = Field(default=True, alias="SMTP_STARTTLS")
    report_email_from: str = Field(default="", alias="REPORT_EMAIL_FROM")
    report_email_to: str = Field(default="", alias="REPORT_EMAIL_TO")
    send_cron_email: bool = Field(default=True, alias="SEND_CRON_EMAIL")


@lru_cache
def get_settings() -> Settings:
    return Settings()
