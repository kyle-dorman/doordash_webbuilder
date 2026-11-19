from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from shutil import which
from subprocess import PIPE, Popen
from sys import executable
from urllib.request import urlopen


def test_serve_storefront_serves_pages_and_assets_from_selected_directory(tmp_path: Path) -> None:
    files = {
        "index.html": b'<a href="menu.html">Menu</a>',
        "menu.html": b'<link rel="stylesheet" href="assets/storefront.css">',
        "assets/storefront.css": b"body { color: navy; }",
    }
    storefront = tmp_path / "storefront"
    (storefront / "assets").mkdir(parents=True)
    for name, content in files.items():
        (storefront / name).write_bytes(content)

    command = which("serve-storefront", path=str(Path(executable).parent))
    assert command is not None
    with (
        Popen(
            [command, "--directory", "storefront", "--port", "0"],
            cwd=tmp_path,
            stdout=PIPE,
            text=True,
        ) as server,
        ThreadPoolExecutor(max_workers=1) as reader,
    ):
        try:
            assert server.stdout is not None
            banner = reader.submit(server.stdout.readline).result(timeout=10)
            base_url = banner.strip().split()[-1]
            assert base_url.startswith("http://127.0.0.1:")
            for name, content in files.items():
                path = "" if name == "index.html" else name
                with urlopen(base_url + path, timeout=5) as response:
                    assert response.read() == content
        finally:
            server.terminate()
