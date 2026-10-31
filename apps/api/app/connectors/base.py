import hashlib
import json


class ProviderTimeout(Exception):
    """The request may or may not have been applied. Callers must reconcile, never blindly resend."""


class ProviderRejected(Exception):
    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


class UserActionNeeded(Exception):
    """A step only the user may perform (login, CAPTCHA, MFA, payment). Raised BEFORE any side effect; the mission pauses."""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}")
        self.reason, self.detail = reason, detail
