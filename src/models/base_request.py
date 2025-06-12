from pydantic import BaseModel, ConfigDict

class BaseRequest(BaseModel):
    """Base class for all API requests"""
    
    model_config = ConfigDict(
        validate_assignment=True,
        use_enum_values=True,
        populate_by_name=True,
        str_strip_whitespace=True,
        validate_default=True
    )