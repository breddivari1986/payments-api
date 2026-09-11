"""Payments API — a small, honest sample service for the delivery pipeline.

Creates and reads payments held in memory. No card data is ever accepted: a payment names a
customer, an amount in minor units, a currency and an idempotency key, which is all a
downstream processor needs from this layer. /healthz answers liveness, /readyz answers
readiness, /metrics answers Prometheus.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VERSION = os.environ.get("APP_VERSION", "dev")
CURRENCIES = {"USD", "EUR", "GBP", "INR"}
_LOCK = threading.Lock()
_PAYMENTS: dict[str, dict] = {}
_BY_KEY: dict[str, str] = {}
_COUNTS = {"created": 0, "rejected": 0, "read": 0}
_STARTED = time.time()


def create_payment(body: dict) -> tuple[int, dict]:
    key = str(body.get("idempotency_key") or "").strip()
    customer = str(body.get("customer_id") or "").strip()
    currency = str(body.get("currency") or "").upper()
    amount = body.get("amount_minor")
    if not key or not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", key):
        return 400, {"error": "idempotency_key is required: 8-64 letters, digits, _ or -"}
    if not customer:
        return 400, {"error": "customer_id is required"}
    if currency not in CURRENCIES:
        return 400, {"error": f"currency must be one of {sorted(CURRENCIES)}"}
    if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0 or amount > 10_000_000:
        return 400, {"error": "amount_minor must be an integer between 1 and 10000000"}
    with _LOCK:
        if key in _BY_KEY:
            return 200, _PAYMENTS[_BY_KEY[key]]
        pid = f"pay_{uuid.uuid4().hex[:16]}"
        payment = {"id": pid, "customer_id": customer, "amount_minor": amount, "currency": currency,
                   "status": "authorized", "idempotency_key": key, "created_at": time.time()}
        _PAYMENTS[pid] = payment
        _BY_KEY[key] = pid
        _COUNTS["created"] += 1
    return 201, payment


def get_payment(pid: str) -> tuple[int, dict]:
    with _LOCK:
        p = _PAYMENTS.get(pid)
        if p:
            _COUNTS["read"] += 1
    return (200, p) if p else (404, {"error": "no such payment"})


def metrics() -> str:
    with _LOCK:
        c = dict(_COUNTS)
    return "\n".join([
        "# HELP payments_created_total Payments created.", "# TYPE payments_created_total counter",
        f"payments_created_total {c['created']}",
        "# HELP payments_rejected_total Requests rejected by validation.", "# TYPE payments_rejected_total counter",
        f"payments_rejected_total {c['rejected']}",
        "# HELP payments_uptime_seconds Seconds since start.", "# TYPE payments_uptime_seconds gauge",
        f"payments_uptime_seconds {time.time() - _STARTED:.0f}",
        "",
    ])


class Handler(BaseHTTPRequestHandler):
    server_version = f"payments-api/{VERSION}"

    def _json(self, code: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/healthz":
            return self._json(200, {"status": "ok", "version": VERSION})
        if self.path == "/readyz":
            return self._json(200, {"ready": True})
        if self.path == "/metrics":
            data = metrics().encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        m = re.fullmatch(r"/payments/(pay_[0-9a-f]{16})", self.path)
        if m:
            return self._json(*get_payment(m.group(1)))
        return self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/payments":
            return self._json(404, {"error": "not found"})
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return self._json(400, {"error": "body must be JSON"})
        code, out = create_payment(body if isinstance(body, dict) else {})
        if code == 400:
            with _LOCK:
                _COUNTS["rejected"] += 1
        return self._json(code, out)

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        print(f'{self.address_string()} {fmt % args}', flush=True)


def main() -> None:
    port = int(os.environ.get("PORT", "8080"))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
