"""Serve a generated storefront over local HTTP."""

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True, help="Storefront output directory")
    parser.add_argument("--port", type=int, default=8000, help="Local port (default: 8000)")
    args = parser.parse_args()
    directory = args.directory.resolve()
    if not (directory / "index.html").is_file():
        parser.error(f"no storefront index.html in {directory}")
    if not 0 <= args.port <= 65535:
        parser.error("--port must be between 0 and 65535")

    handler = partial(SimpleHTTPRequestHandler, directory=directory)
    try:
        with ThreadingHTTPServer(("127.0.0.1", args.port), handler) as server:
            print(f"Serving {directory} at http://127.0.0.1:{server.server_port}/", flush=True)
            server.serve_forever()
    except OSError as error:
        parser.exit(1, f"{parser.prog}: {error}\n")
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
