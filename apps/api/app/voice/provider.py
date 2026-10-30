"""Provider-independent voice interface. Domain logic depends on this Protocol, never on Bolna directly."""
from typing import Protocol

from . import bolna


class VoiceProvider(Protocol):
    name: str

    def mint_web_session(self, user_data: dict | None = None) -> dict: ...
    def start_outbound(self, phone: str, user_data: dict | None = None) -> dict: ...
    def get_execution(self, execution_id: str) -> dict: ...


def get_provider() -> VoiceProvider:
    return bolna.make_client()  # resolved at call time so tests/other providers can substitute
