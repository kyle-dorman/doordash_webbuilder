"""Serve a generated storefront and forward checkout to its local mock backend."""

import argparse
import json
from contextlib import closing
from functools import partial
from http.client import HTTPConnection, HTTPException
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from socket import socket
from socketserver import BaseServer


class StorefrontHandler(SimpleHTTPRequestHandler):
    def __init__(
        self,
        request: socket,
        client_address: tuple[str, int],
        server: BaseServer,
        *,
        directory: Path,
        mock_port: int,
    ) -> None:
        self.mock_port = mock_port
        super().__init__(request, client_address, server, directory=directory)

    def send_json(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def checkout_error(self, status: int, message: str) -> None:
        self.send_json(status, json.dumps({"error": message}).encode())

    def do_POST(self) -> None:
        if self.path != "/orders":
            self.send_error(404)
            return
        if self.headers.get_content_type() != "application/json":
            self.checkout_error(415, "Submit the order as JSON.")
            return
        try:
            length = int(self.headers.get("Content-Length", ""))
            if length < 0:
                raise ValueError
        except ValueError:
            self.checkout_error(400, "The order needs a valid content length.")
            return
        if length > 64 * 1024:
            self.checkout_error(413, "The order is too large.")
            return
        body = self.rfile.read(length)
        if len(body) != length:
            self.checkout_error(400, "The order was incomplete.")
            return
        try:
            with closing(HTTPConnection("127.0.0.1", self.mock_port, timeout=5)) as mock:
                mock.request("POST", "/orders", body, {"Content-Type": "application/json"})
                response = mock.getresponse()
                payload = response.read()
        except (OSError, HTTPException):
            self.checkout_error(502, "Couldn’t reach the mock checkout.")
            return
        self.send_json(response.status, payload)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True, help="Storefront output directory")
    parser.add_argument("--port", type=int, default=8000, help="Local port (default: 8000)")
    parser.add_argument(
        "--mock-port", type=int, default=8001, help="Local mock port (default: 8001)"
    )
    args = parser.parse_args()
    directory = args.directory.resolve()
    if not (directory / "index.html").is_file():
        parser.error(f"no storefront index.html in {directory}")
    if not 0 <= args.port <= 65535:
        parser.error("--port must be between 0 and 65535")
    if not 1 <= args.mock_port <= 65535 or args.port == args.mock_port:
        parser.error("--mock-port must be between 1 and 65535 and differ from --port")

    handler = partial(StorefrontHandler, directory=directory, mock_port=args.mock_port)
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
