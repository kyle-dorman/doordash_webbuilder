import pytest

pytest_plugins = ("sdk_responses",)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
