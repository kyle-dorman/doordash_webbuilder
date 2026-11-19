from importlib import import_module

import pytest


@pytest.mark.parametrize(
    "package",
    ["webbuilder_agent", "webbuilder_mock_backend", "webbuilder_site_server", "webbuilder_shopper"],
)
def test_workspace_package_is_importable(package: str) -> None:
    import_module(package)
