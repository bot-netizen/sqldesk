#!/usr/bin/env python3
"""
Put the `claude` command behind an OpenAI-shaped endpoint, for development.

Why this exists. SQLDesk's `cli` provider runs `claude` as a subprocess, which
needs the command on the same machine as the SQLDesk process. In Docker on
macOS it is not: Claude Code there is a Mach-O arm64 binary and the container
is Linux, so mounting it in gets you "exec format error" rather than an answer.

So the container talks to the host over HTTP instead, and this is what answers.
It speaks enough of the OpenAI chat-completions shape for SQLDesk's `local`
provider, which means no new provider and no image change:

    python3 scripts/claude-bridge.py                     # on the host
    manage ai configure local \\
      --base-url http://host.docker.internal:8808/v1 --model claude-sonnet-5

For development. It binds to localhost, has no authentication, and runs one
request at a time -- anything that reaches it can spend your Claude
subscription, so do not put it anywhere but your own machine. For a server,
install Claude Code in the image and use `--provider cli`, or use
`--provider anthropic` with a key.
"""

import argparse
import json
import shutil
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer

COMMAND = "claude"
TIMEOUT = 180


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if not self.path.endswith("/chat/completions"):
            return self._send(404, {"error": {"message": "only /v1/chat/completions"}})

        length = int(self.headers.get("content-length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return self._send(400, {"error": {"message": "not JSON"}})

        messages = body.get("messages") or []
        system = "\n".join(m["content"] for m in messages if m.get("role") == "system")
        prompt = "\n".join(m["content"] for m in messages if m.get("role") != "system")
        if not prompt:
            return self._send(400, {"error": {"message": "no user message"}})

        argv = [COMMAND, "-p"]
        if body.get("model"):
            argv += ["--model", body["model"]]
        if system:
            argv += ["--append-system-prompt", system]
        argv.append(prompt)

        try:
            finished = subprocess.run(argv, capture_output=True, text=True, timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            return self._send(504, {"error": {"message": "claude did not answer in {}s".format(TIMEOUT)}})
        except OSError as error:
            return self._send(500, {"error": {"message": "could not run {}: {}".format(COMMAND, error)}})

        if finished.returncode != 0:
            detail = (finished.stderr or finished.stdout or "").strip()[:400]
            return self._send(502, {"error": {"message": "claude exited {}: {}".format(finished.returncode, detail)}})

        self._send(
            200,
            {
                "id": "claude-bridge",
                "object": "chat.completion",
                "model": body.get("model") or "claude",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": finished.stdout.strip()}}],
            },
        )

    def log_message(self, fmt, *args):
        print("  {}".format(fmt % args))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8808)
    parser.add_argument("--command", default=COMMAND, help="the claude executable, if not on PATH")
    parser.add_argument("--timeout", type=int, default=TIMEOUT)
    args = parser.parse_args()

    global COMMAND, TIMEOUT
    COMMAND, TIMEOUT = args.command, args.timeout

    if shutil.which(COMMAND) is None:
        raise SystemExit("`{}` is not on your PATH. Install Claude Code first.".format(COMMAND))

    print("claude-bridge on http://127.0.0.1:{}/v1  (command: {})".format(args.port, COMMAND))
    print("From a container, point SQLDesk at http://host.docker.internal:{}/v1".format(args.port))
    print("Development only: no authentication, one request at a time, localhost only.")
    HTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
