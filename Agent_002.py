"""
Agent_002 - HTTP / HTML / CSS Web Controller

Responsible for:
- Serving web pages over HTTP
- Rendering HTML templates
- Serving static CSS/JS assets
- Routing requests to the correct page handlers
"""

import http.server
import json
import logging
import mimetypes
import os
import socket
import threading
from pathlib import Path
from string import Template
from typing import Callable

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [Agent_002] %(levelname)s: %(message)s",
)
logger = logging.getLogger("Agent_002")

# ---------------------------------------------------------------------------
# Default embedded HTML / CSS so the agent works out-of-the-box
# ---------------------------------------------------------------------------

_DEFAULT_CSS = """\
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: 'Segoe UI', Arial, sans-serif;
    background: #f4f6f9;
    color: #333;
    display: flex;
    flex-direction: column;
    min-height: 100vh;
}
header {
    background: #2c3e50;
    color: #fff;
    padding: 1rem 2rem;
    font-size: 1.4rem;
    font-weight: bold;
    letter-spacing: 0.05em;
}
main { flex: 1; padding: 2rem; max-width: 900px; margin: auto; width: 100%; }
h1 { margin-bottom: 1rem; color: #2c3e50; }
p  { line-height: 1.6; margin-bottom: 0.8rem; }
footer {
    background: #2c3e50;
    color: #aaa;
    text-align: center;
    padding: 0.8rem;
    font-size: 0.85rem;
}
"""

_DEFAULT_HOME_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>$title</title>
  <style>$css</style>
</head>
<body>
  <header>$site_name</header>
  <main>
    <h1>$heading</h1>
    <p>$body_text</p>
    <p><a href="/payment">Go to Payment →</a></p>
  </main>
  <footer>$footer_text</footer>
</body>
</html>
"""

_DEFAULT_PAYMENT_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Payment – $site_name</title>
  <style>$css</style>
</head>
<body>
  <header>$site_name – Payment</header>
  <main>
    <h1>Complete Your Purchase</h1>
    <p>Thank you for choosing us! Please fill in your payment details below.</p>
    <form method="POST" action="/payment/process">
      <label for="card">Card number</label><br />
      <input id="card" type="text" name="card" placeholder="xxxx xxxx xxxx xxxx"
             maxlength="19" style="width:100%;padding:0.5rem;margin:0.5rem 0 1rem;" /><br />
      <label for="expiry">Expiry (MM/YY)</label><br />
      <input id="expiry" type="text" name="expiry" placeholder="MM/YY"
             maxlength="5" style="width:100%;padding:0.5rem;margin:0.5rem 0 1rem;" /><br />
      <label for="cvv">CVV</label><br />
      <input id="cvv" type="text" name="cvv" placeholder="123"
             maxlength="4" style="width:100%;padding:0.5rem;margin:0.5rem 0 1rem;" /><br />
      <button type="submit"
              style="background:#27ae60;color:#fff;border:none;padding:0.75rem 2rem;
                     font-size:1rem;cursor:pointer;border-radius:4px;">
        Pay Now
      </button>
    </form>
  </main>
  <footer>$footer_text</footer>
</body>
</html>
"""

_DEFAULT_CONTEXT = {
    "site_name": "AwesomeShell Store",
    "title": "Welcome",
    "heading": "Welcome to AwesomeShell Store",
    "body_text": (
        "Browse our products and click below to proceed to checkout "
        "once you are ready."
    ),
    "footer_text": "© 2025 AwesomeShell Store. All rights reserved.",
    "css": _DEFAULT_CSS,
}


# ---------------------------------------------------------------------------
# HTTP request handler
# ---------------------------------------------------------------------------

def _make_handler(agent: "Agent002"):
    """Factory that returns an HTTPRequestHandler bound to *agent*."""

    class _Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # suppress default access log
            logger.debug("%s - %s", self.address_string(), fmt % args)

        # ------------------------------------------------------------------
        def do_GET(self):  # noqa: N802
            path = self.path.split("?")[0].rstrip("/") or "/"
            route_fn = agent._routes.get(path)
            if route_fn:
                body = route_fn()
                self._send(200, body, "text/html; charset=utf-8")
            else:
                self._send(404, b"<h1>404 Not Found</h1>", "text/html; charset=utf-8")

        def do_POST(self):  # noqa: N802
            path = self.path.split("?")[0].rstrip("/") or "/"
            route_fn = agent._post_routes.get(path)
            if route_fn:
                length = int(self.headers.get("Content-Length", 0))
                body_bytes = self.rfile.read(length) if length else b""
                response = route_fn(body_bytes)
                self._send(200, response, "text/html; charset=utf-8")
            else:
                self._send(404, b"<h1>404 Not Found</h1>", "text/html; charset=utf-8")

        def _send(self, code: int, body, content_type: str):
            if isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return _Handler


# ---------------------------------------------------------------------------
# Agent_002 class
# ---------------------------------------------------------------------------

class Agent002:
    """HTTP / HTML / CSS web controller agent."""

    def __init__(self, context: dict | None = None, static_dir: str | None = None):
        self._context = {**_DEFAULT_CONTEXT, **(context or {})}
        self._static_dir = Path(static_dir) if static_dir else None
        self._server: http.server.HTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._routes: dict[str, Callable] = {}
        self._post_routes: dict[str, Callable] = {}
        self._register_default_routes()

    # ------------------------------------------------------------------
    # Route registration
    # ------------------------------------------------------------------

    def add_route(self, path: str, handler: Callable) -> None:
        """Register a GET handler for *path*."""
        self._routes[path] = handler
        logger.info("GET route registered: %s", path)

    def add_post_route(self, path: str, handler: Callable) -> None:
        """Register a POST handler for *path*."""
        self._post_routes[path] = handler
        logger.info("POST route registered: %s", path)

    def _register_default_routes(self) -> None:
        self.add_route("/", self._render_home)
        self.add_route("/payment", self._render_payment)
        self.add_post_route("/payment/process", self._handle_payment)

    # ------------------------------------------------------------------
    # Page renderers
    # ------------------------------------------------------------------

    def render_template(self, template: str, extra: dict | None = None) -> bytes:
        """Substitute *template* variables with the current context."""
        ctx = {**self._context, **(extra or {})}
        return Template(template).safe_substitute(ctx).encode("utf-8")

    def _render_home(self) -> bytes:
        return self.render_template(_DEFAULT_HOME_HTML)

    def _render_payment(self) -> bytes:
        return self.render_template(_DEFAULT_PAYMENT_HTML)

    def _handle_payment(self, body: bytes) -> bytes:
        logger.info("Payment form submitted (%d bytes)", len(body))
        html = (
            "<!DOCTYPE html><html><body>"
            "<h1>Payment Received</h1>"
            "<p>Thank you! Your order is being processed.</p>"
            "<p><a href='/'>Return home</a></p>"
            "</body></html>"
        )
        return html.encode("utf-8")

    # ------------------------------------------------------------------
    # Server lifecycle
    # ------------------------------------------------------------------

    def serve(
        self,
        host: str = "0.0.0.0",
        port: int = 8080,
        blocking: bool = True,
    ) -> None:
        """Start the HTTP server.

        If *blocking* is False the server runs in a background thread and
        this method returns immediately.
        """
        handler_cls = _make_handler(self)
        self._server = http.server.HTTPServer((host, port), handler_cls)
        logger.info("Agent_002 serving on http://%s:%d", host, port)
        if blocking:
            try:
                self._server.serve_forever()
            except KeyboardInterrupt:
                logger.info("Server shutdown requested.")
            finally:
                self._server.server_close()
        else:
            self._thread = threading.Thread(
                target=self._server.serve_forever, daemon=True
            )
            self._thread.start()

    def stop(self) -> None:
        """Stop a non-blocking server."""
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            logger.info("Agent_002 server stopped.")

    def status(self) -> dict:
        """Return a dict describing the agent's current state."""
        return {
            "running": self._server is not None,
            "routes": list(self._routes.keys()),
            "post_routes": list(self._post_routes.keys()),
        }


# ---------------------------------------------------------------------------
# Entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Agent_002 web controller")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host")
    parser.add_argument("--port", type=int, default=8080, help="Bind port")
    parser.add_argument("--site-name", default="AwesomeShell Store", help="Site name")
    args = parser.parse_args()

    agent = Agent002(context={"site_name": args.site_name})
    agent.serve(host=args.host, port=args.port)
