"""Deterministic citation validation. Text may cite only sources that exist in this tenant's RegSource table."""
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import RegSource


class CitationError(Exception):
    pass


def assert_valid(db: Session, tenant_id: str, text: str, allowed_ids: list[str]) -> None:
    cited = set(re.findall(r"\[(src_[0-9a-f]{16})\]", text))
    known = set(db.scalars(select(RegSource.id).where(RegSource.tenant_id == tenant_id, RegSource.id.in_(allowed_ids or [""]))))
    unknown = cited - known
    if unknown:
        raise CitationError(f"unverified citation(s): {sorted(unknown)}")
