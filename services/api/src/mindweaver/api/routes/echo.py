"""Small dev utility endpoint used to exercise structured validation errors."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(tags=["system"])


class EchoRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)


@router.post("/echo", summary="Echo a message back")
def echo(payload: EchoRequest) -> dict[str, str]:
    return {"message": payload.message}
