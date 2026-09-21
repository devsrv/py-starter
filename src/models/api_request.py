from typing import Any

from pydantic import Field

from src.models.base_request import BaseRequest


class ApiRequest(BaseRequest):
    """Sample request body used by the `/test` endpoint."""

    org_id: int = Field(..., gt=0, description="Organization ID must be positive")
    metadata: dict[str, Any] | None = Field(None, description="Optional metadata")
