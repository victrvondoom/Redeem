from typing import Literal

from pydantic import BaseModel, Field, field_validator

Lang = Literal["en", "hi", "hinglish", "ta", "te"]


class _Strict(BaseModel):
    model_config = {"extra": "forbid"}


class RegisterIn(_Strict):
    email: str = Field(min_length=5, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=10, max_length=200)
    name: str = Field(min_length=1, max_length=120)
    language: Lang = "en"

    @field_validator("email")
    @classmethod
    def lower(cls, v):
        return v.strip().lower()


class LoginIn(_Strict):
    email: str = Field(max_length=320)
    password: str = Field(max_length=200)


class LangIn(_Strict):
    language: Lang


class MissionIn(_Strict):
    intent: str = Field(min_length=3, max_length=2000)
    language: Lang = "en"
    source: Literal["text", "voice"] = "text"
    transcript_confidence: float | None = Field(None, ge=0, le=1)
    document_id: str | None = None


class ReviseIn(_Strict):
    intent: str | None = Field(None, min_length=3, max_length=2000)
    confirm_transcript: bool = False


class BindIn(_Strict):
    role: str = Field(max_length=40)
    value: str = Field(max_length=120)


class ApprovalItem(_Strict):
    action_id: str
    digest: str = Field(min_length=64, max_length=64)


class ApproveIn(_Strict):
    approvals: list[ApprovalItem] = Field(min_length=1, max_length=20)


class FaultIn(_Strict):
    kind: Literal["ack_loss", "silent_drop"]


class ConsentIn(_Strict):
    purpose: Literal["voice_call", "call_recording"]
    granted: bool


class AttachIn(_Strict):
    execution_id: str = Field(min_length=3, max_length=80, pattern=r"^[A-Za-z0-9_\-]+$")


class OutboundIn(_Strict):
    phone: str = Field(pattern=r"^\+[1-9]\d{7,14}$")
    mission_id: str | None = None
    language: Lang = "en"


class ScanIn(_Strict):
    text: str = Field(min_length=1, max_length=5000)


class StartWorkflowIn(_Strict):
    inputs: dict[str, str] = Field(default_factory=dict, max_length=10)


class UrlCheckIn(_Strict):
    url: str = Field(min_length=1, max_length=2000)


class RejectIn(_Strict):
    action_ids: list[str] = Field(min_length=1, max_length=20)
    reason: str = Field("", max_length=200)


class CaseIn(_Strict):
    text: str = Field(min_length=10, max_length=4000)
    domain: str | None = Field(None, pattern="^(travel|banking|insurance|telecom|ecommerce|housing|government|healthcare)$")
    intake: dict[str, str] | None = Field(None, max_length=30)
    document_ids: list[str] = Field(default_factory=list, max_length=20)


class IntakeIn(_Strict):
    fields: dict[str, str] = Field(min_length=1, max_length=30)


class DraftIn(_Strict):
    body: str = Field(min_length=20, max_length=12000)


class RankIn(_Strict):
    weights: dict[str, float] | None = None


class ApproveCaseIn(_Strict):
    action_key: str = Field(max_length=60)
    digest: str = Field(min_length=64, max_length=64)


class TrackIn(_Strict):
    kind: Literal["acknowledgement", "response", "escalated", "resolved", "rejected"]
    reference: str | None = Field(None, max_length=80)
    note: str = Field("", max_length=1000)
    document_id: str | None = None
    amount_inr: float | None = Field(None, ge=0, le=1e9)


class KbSearchIn(_Strict):
    query: str = Field(min_length=2, max_length=400)
    domains: list[str] | None = Field(None, max_length=8)
    k: int = Field(6, ge=1, le=15)
