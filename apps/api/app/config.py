from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    database_url: str = Field("sqlite:///./redeem.db", validation_alias="REDEEM_DATABASE_URL")
    session_ttl_hours: int = Field(168, validation_alias="REDEEM_SESSION_TTL_HOURS")
    cookie_secure: bool = Field(False, validation_alias="REDEEM_COOKIE_SECURE")
    # Fault injection is a demo/test facility acting only on stateful *fixtures*.
    allow_fault_injection: bool = Field(True, validation_alias="REDEEM_ALLOW_FAULT_INJECTION")
    approval_ttl_minutes: int = Field(30, validation_alias="REDEEM_APPROVAL_TTL_MINUTES")

    bolna_api_key: str = Field("", validation_alias="BOLNA_API_KEY")
    bolna_agent_id: str = Field("", validation_alias="BOLNA_AGENT_ID")
    bolna_base_url: str = Field("https://api.bolna.ai", validation_alias="BOLNA_BASE_URL")
    bolna_webhook_secret: str = Field("", validation_alias="BOLNA_WEBHOOK_SECRET")
    bolna_timeout_seconds: float = Field(10.0, validation_alias="BOLNA_TIMEOUT_SECONDS")
    allow_outbound_calls: bool = Field(False, validation_alias="REDEEM_ALLOW_OUTBOUND_CALLS")
    # Comma separated E.164 numbers owned/authorised by the operator. Nothing else may be dialled.
    outbound_test_numbers: str = Field("", validation_alias="REDEEM_OUTBOUND_TEST_NUMBERS")

    register_rate_limit_per_minute: int = Field(10, validation_alias="REDEEM_REGISTER_RATE_LIMIT")
    # Evaluation-only: lets the benchmark disable one control at a time. Never enable in production.
    eval_mode: bool = Field(False, validation_alias="REDEEM_EVAL_MODE")
    isolated_browser_runtime_url: str = Field("", validation_alias="REDEEM_ISOLATED_BROWSER_URL")

    @property
    def bolna_configured(self) -> bool:
        return bool(self.bolna_api_key and self.bolna_agent_id)

    @property
    def outbound_allowlist(self) -> set[str]:
        return {n.strip() for n in self.outbound_test_numbers.split(",") if n.strip()}


settings = Settings()
