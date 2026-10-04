import pytest

from cnpjaberto import Client


@pytest.fixture
def sdk(httpx_mock):
    with Client(api_key="test-key", base_url="https://api.example.test") as client:
        yield client
