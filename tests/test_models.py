import pytest
from pydantic import ValidationError

from src.models.api_request import ApiRequest
from src.models.base_request import BaseRequest


def test_valid_request():
    req = ApiRequest(org_id=5, metadata={"a": 1})
    assert req.org_id == 5
    assert req.metadata == {"a": 1}


def test_metadata_optional():
    assert ApiRequest(org_id=1).metadata is None


@pytest.mark.parametrize("bad", [0, -1])
def test_org_id_must_be_positive(bad):
    with pytest.raises(ValidationError):
        ApiRequest(org_id=bad)


def test_org_id_required():
    with pytest.raises(ValidationError):
        ApiRequest()


def test_metadata_must_be_dict():
    with pytest.raises(ValidationError):
        ApiRequest(org_id=1, metadata=["not", "a", "dict"])


def test_base_request_strips_whitespace_and_validates_assignment():
    class Named(BaseRequest):
        name: str

    n = Named(name="  hello  ")
    assert n.name == "hello"
    with pytest.raises(ValidationError):
        n.name = 123
