"""Starts the whole prototype on this machine: the election-data tool
server, a tap that stands for the network, and the ConsequenceOS gate.

    python -m guarded_assistant.stack            # start it; Ctrl-C stops it
    python -m guarded_assistant.stack --print-keys

Everything it makes lives in .run/: the gate's keys (made once, kept
private), its audit log, the tool server's ledger, and what the tap saw.
The gate is the consequenced binary from ConsequenceOS, found as
$CONSEQUENCED, .run/bin/consequenced, or consequenced on the PATH.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / ".run"
GATE = "http://127.0.0.1:8080"
TOOLS_ADDR = "127.0.0.1:9090"
TAP_ADDR = ("127.0.0.1", 9091)

ROLES = ("voter-assistant", "results-officer", "comms-officer", "analyst")
ROLE_KEY_ENV = {r: "CONSEQUENCE_KEY_" + r.upper().replace("-", "_") for r in ROLES}
RECEIVER_KEY_ENV = "CONSEQUENCE_KEY_RECEIVER_ELECTION_DATA"


def consequenced() -> str:
    for candidate in (os.environ.get("CONSEQUENCED"), str(RUN / "bin" / "consequenced"), shutil.which("consequenced")):
        if candidate and Path(candidate).is_file():
            return candidate
    sys.exit("consequenced not found: set $CONSEQUENCED, put it in .run/bin/, or on the PATH. "
             "Get it from https://github.com/Matutozi/Consequence-OS/releases (v0.6.0 or later).")


def keys(run: Path = RUN) -> dict[str, str]:
    """The gate's secrets, made the first time and kept in run/keys.env
    (readable by you alone): its two signing keys, the admin token, the
    tool server's receiver key, and one API key per role."""
    path = run / "keys.env"
    if not path.exists():
        run.mkdir(parents=True, exist_ok=True)
        out = subprocess.run([consequenced(), "-genkeys"], check=True, capture_output=True, text=True).stdout
        lines = [line for line in out.splitlines() if line and not line.startswith("#")]
        for name in ("CONSEQUENCE_ADMIN_TOKEN", RECEIVER_KEY_ENV, *ROLE_KEY_ENV.values()):
            lines.append(f"{name}={secrets.token_urlsafe(24)}")
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write("\n".join(lines) + "\n")
    return dict(line.split("=", 1) for line in path.read_text().splitlines() if "=" in line)


def gate_config(run: Path = RUN) -> Path:
    """config/consequence.yaml, with state_dir set to run/state."""
    path = run / "consequence.yaml"
    path.write_text((ROOT / "config" / "consequence.yaml").read_text() + f"\nstate_dir: {run / 'state'}\n")
    return path


class Tap:
    """Forwards the gate's requests to the tool server, and keeps each
    tools/call it saw, headers and body: what someone listening on the
    network between them would have. With alter set, it changes each
    tools/call on the way, as someone in the middle could."""

    def __init__(self, upstream: str, record: Path) -> None:
        self.upstream, self.record, self.seen = upstream, record, []
        self.alter: Callable[[dict], dict] | None = None
        tap = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802 (the http.server name)
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                headers = {k: v for k, v in self.headers.items() if k.lower() not in ("host", "content-length", "connection")}
                try:
                    msg = json.loads(body)
                except ValueError:
                    msg = None
                if isinstance(msg, dict) and msg.get("method") == "tools/call":
                    tap.keep(headers, body)
                    if tap.alter is not None:
                        msg = tap.alter(msg)
                        body = json.dumps(msg).encode()
                        headers = {k: v for k, v in headers.items() if k.lower() != "mcp-name"}
                        headers["Mcp-Name"] = msg["params"]["name"]  # kept consistent, so only the receipt can catch it
                req = urllib.request.Request(tap.upstream + self.path, data=body, headers=headers, method="POST")
                try:
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        status, out, ctype = resp.status, resp.read(), resp.headers.get("Content-Type", "application/json")
                except urllib.error.HTTPError as e:
                    status, out, ctype = e.code, e.read(), e.headers.get("Content-Type", "application/json")
                self.send_response(status)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

            def log_message(self, *args):  # quiet
                pass

        self.server = ThreadingHTTPServer(TAP_ADDR, Handler)

    def keep(self, headers: dict, body: bytes) -> None:
        item = {"headers": headers, "body": body.decode()}
        self.seen.append(item)
        with open(self.record, "a", encoding="utf-8") as f:
            f.write(json.dumps(item) + "\n")

    def start(self) -> None:
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def stop(self) -> None:
        self.server.shutdown()


def _wait(url: str, seconds: float = 20) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
            return
        except urllib.error.HTTPError:
            return  # it answered
        except OSError:
            time.sleep(0.2)
    raise RuntimeError(f"{url} didn't come up; see the logs in .run/")


class Stack:
    """The running prototype. Use as a context manager."""

    def __init__(self, run: Path = RUN) -> None:
        self.run = run
        self.procs: list[subprocess.Popen] = []

    def __enter__(self) -> Stack:
        self.keys = keys(self.run)
        env = {**os.environ, **self.keys, "CONSEQUENCE_URL": GATE, "ELECTION_DATA_ADDR": TOOLS_ADDR,
               "ELECTION_LEDGER": str(self.run / "ledger.jsonl"), "PYTHONPATH": str(ROOT / "src")}
        logs = self.run / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        self.procs.append(subprocess.Popen([sys.executable, "-m", "guarded_assistant.server"], env=env,
                                           stdout=open(logs / "tools.log", "a"), stderr=subprocess.STDOUT))
        self.tap = Tap("http://" + TOOLS_ADDR, self.run / "wire.jsonl")
        self.tap.start()
        self.procs.append(subprocess.Popen([consequenced(), "-config", str(gate_config(self.run))], env=env,
                                           stdout=open(logs / "gate.log", "a"), stderr=subprocess.STDOUT))
        try:
            _wait(GATE + "/healthz")
            _wait("http://" + TOOLS_ADDR + "/mcp")
        except RuntimeError:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, *exc) -> None:
        for p in self.procs:
            p.send_signal(signal.SIGTERM)
        for p in self.procs:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
        self.tap.stop()

    def key(self, role: str) -> str:
        return self.keys[ROLE_KEY_ENV[role]]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--print-keys", action="store_true", help="print each role's API key and exit")
    a = ap.parse_args()
    if a.print_keys:
        for role, env in ROLE_KEY_ENV.items():
            print(f"{role}: {keys()[env]}")
        return
    with Stack():
        print(f"Running. The gate is {GATE}/mcp; approvals and the audit log are there too.")
        print("Logs: .run/logs/. Ctrl-C stops it.")
        try:
            signal.pause()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
