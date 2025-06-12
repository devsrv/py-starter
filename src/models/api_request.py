from pydantic import field_validator, Field
from .base_request import BaseRequest
from typing import Optional, Dict, Any

class ApiRequest(BaseRequest):
    org_id: int = Field(..., gt=0, description="Organization ID must be positive")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Optional metadata")
    
    @field_validator('org_id')
    @classmethod
    def validate_org_id(cls, v: int) -> int:
        if v <= 0:
            raise ValueError('org_id must be positive')
        return v
    
    @field_validator('metadata')
    @classmethod
    def validate_metadata(cls, v: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if v is not None and not isinstance(v, dict):
            raise ValueError('metadata must be a dictionary')
        return v