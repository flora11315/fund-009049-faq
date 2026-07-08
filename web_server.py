#!/usr/bin/env python3
"""Web server for the 009049 FAQ assistant prototype."""

from __future__ import annotations

import base64
import json
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from collect_fund_data import CollectionError, collect, merge_into_knowledge
from faq_assistant import answer_question, load_knowledge, run_eval


ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = ROOT / "web"


class AssistantHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_ROOT), **kwargs)

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _auth_required(self) -> bool:
        return bool(os.getenv("APP_USERNAME") and os.getenv("APP_PASSWORD"))

    def _is_authorized(self) -> bool:
        if not self._auth_required():
            return True
        header = self.headers.get("Authorization", "")
        prefix = "Basic "
        if not header.startswith(prefix):
            return False
        try:
            decoded = base64.b64decode(header[len(prefix):]).decode("utf-8")
        except Exception:
            return False
        username, _, password = decoded.partition(":")
        return username == os.getenv("APP_USERNAME") and password == os.getenv("APP_PASSWORD")

    def _require_auth(self) -> bool:
        if self._is_authorized():
            return True
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="009049 FAQ Assistant"')
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write("需要用户名和密码。".encode("utf-8"))
        return False

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/healthz":
            self._send_json({"status": "ok"})
            return
        if not self._require_auth():
            return
        if path == "/api/knowledge":
            self._send_json(load_knowledge())
            return
        if path == "/api/eval":
            self._send_json(run_eval())
            return
        return super().do_GET()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if not self._require_auth():
            return
        try:
            if path == "/api/ask":
                payload = self._read_json()
                question = str(payload.get("question", "")).strip()
                if not question:
                    self._send_json({"error": "问题不能为空。"}, 400)
                    return
                self._send_json({"question": question, "answer": answer_question(question)})
                return
            if path == "/api/collect":
                collected = collect()
                merge_into_knowledge(collected)
                self._send_json({"status": "success", "collected": collected, "knowledge": load_knowledge()})
                return
        except CollectionError as exc:
            self._send_json({"status": "error", "error": str(exc)}, 502)
            return
        except Exception as exc:
            self._send_json({"status": "error", "error": str(exc)}, 500)
            return
        self._send_json({"error": "Unknown API endpoint."}, 404)


def main() -> None:
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    server = ThreadingHTTPServer((host, port), AssistantHandler)
    print(f"009049 FAQ assistant web app: http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
