"""
The optional interpreter: sessions that hold variables, and cells that run in them.

This runs in its own container, not in the SQLDesk image, and that is the whole
point -- the same argument as the renderer, one decision further. Running
somebody's Python inside the RQ worker would mean the process holding every
data source's decrypted credentials also runs arbitrary code. No sandbox put
around that afterwards is worth the sentence describing it.

So: a separate container, pandas and DuckDB and nothing else, no credentials,
and nothing to reach. A code cell reads an earlier cell's output and nothing
else (design §4.1), which is what removes the entire problem -- there is no
token to scope, no network path back to SQLDesk, and no permission to invent.
A cell can only ever see data a SQL cell was already permitted to fetch.

Off by default. If you do not run this, Python cells say so on the cell and
SQL cells carry on exactly as before.

**The boundary is the container, and the ceilings are the child's.** This
service holds no state worth taking and makes no outbound connection; each
session is a spawned child process with its own address-space, CPU and
file-size limits, and a stop is a signal to it. Deny this container egress and
the sandbox is complete -- see the note in `Dockerfile.executor`.
"""

import contextlib
import hmac
import logging
import os
import shutil
import signal
import tempfile
import threading
import time
import uuid
from multiprocessing import get_context

import spark
from flask import Flask, Response, jsonify, request
from runner import INPUT, PING, RUN, serve

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

#: The caller shows this. Unset, nothing is checked -- which is right only on a
#: network with nothing else on it, and the chart and the compose file both set
#: one. Same rule as the renderer.
TOKEN = os.environ.get("EXECUTOR_TOKEN", "")

#: How many sessions may be alive at once. Each is a process holding a
#: dataframe, so this is the number that decides how much memory this container
#: can be asked for: SESSIONS x MEMORY_MB is the ceiling.
MAX_SESSIONS = int(os.environ.get("EXECUTOR_MAX_SESSIONS", "8"))

#: A session with nothing asked of it for this long is ended. Opening a
#: notebook attaches nothing (design §4.4), and a session nobody is using is a
#: process holding memory for a page somebody closed an hour ago.
IDLE_SECONDS = int(os.environ.get("EXECUTOR_IDLE_SECONDS", "900"))

#: Wall clock for one cell. The child's own RLIMIT_CPU covers compute; this
#: covers a cell that is merely stuck, which no CPU limit ever catches.
RUN_SECONDS = int(os.environ.get("EXECUTOR_RUN_SECONDS", "300"))

#: The child's ceilings.
#:
#: Memory is 0 -- unset -- on purpose, and `runner.limits` carries the
#: measurement: an address-space cap small enough to be a useful per-session
#: ceiling stops the libraries loading, and reports it as a KeyboardInterrupt.
#: Limit this container's memory instead (`--memory`, or Kubernetes limits);
#: a cell that exceeds it is reported as the interpreter running out of memory,
#: which is what happened.
MEMORY_MB = int(os.environ.get("EXECUTOR_MEMORY_MB", "0"))
CPU_SECONDS = int(os.environ.get("EXECUTOR_CPU_SECONDS", "300"))
FILE_MB = int(os.environ.get("EXECUTOR_FILE_MB", "2048"))

#: Processes and threads one session may own, 0 for the container's own limit.
#: Off by default, and `runner.limits` records the measurement that is why: a
#: cap under about 128 stops `import pandas` working, and reports it as a
#: KeyboardInterrupt. Raise it deliberately or leave it alone.
MAX_PROCESSES = int(os.environ.get("EXECUTOR_MAX_PROCESSES", "0"))

#: The largest input a cell may be handed, as Parquet. A cell's dataframe is
#: several times its Parquet size in memory, so this and MEMORY_MB are two
#: halves of one decision.
MAX_INPUT_MB = int(os.environ.get("EXECUTOR_MAX_INPUT_MB", "512"))

#: How long a stopped cell is given to notice the signal before it is killed.
#: SIGINT lands as KeyboardInterrupt and the session survives; SIGKILL ends the
#: session, which is why it is second and not first.
STOP_GRACE_SECONDS = float(os.environ.get("EXECUTOR_STOP_GRACE_SECONDS", "3"))

#: Spawn, not fork. A forked child inherits this process's memory -- including
#: `TOKEN` -- its imported modules and its open sockets. Spawning starts a
#: fresh interpreter that has none of them.
CONTEXT = get_context("spawn")

_sessions = {}
_sessions_lock = threading.Lock()


class Session:
    """
    One notebook's interpreter: a child process and the pipe to it.

    The lock is per session, so two cells of the same notebook cannot run at
    once -- they share a namespace, and "at once" would make the result depend
    on which finished first -- while different notebooks do not wait on each
    other.
    """

    def __init__(self):
        self.id = uuid.uuid4().hex
        self.directory = tempfile.mkdtemp(prefix="session-")
        self.lock = threading.Lock()
        self.touched = time.monotonic()
        self.running = False
        self.dead_reason = None
        ours, theirs = CONTEXT.Pipe()
        self.pipe = ours
        self.process = CONTEXT.Process(
            target=serve,
            args=(
                theirs,
                {
                    "memory_mb": MEMORY_MB,
                    "cpu_seconds": CPU_SECONDS,
                    "file_mb": FILE_MB,
                    "max_processes": MAX_PROCESSES,
                },
            ),
            daemon=True,
        )
        self.process.start()
        # This end of the pipe is the child's. Left open here, the parent would
        # never see EOF when the child dies, so a dead session would look busy
        # instead of dead.
        theirs.close()

    @property
    def alive(self):
        return self.dead_reason is None and self.process.is_alive()

    def ask(self, message, timeout):
        """
        Send one request and wait for its answer.

        A timeout here means the cell is still running and will not stop on its
        own, so the session is ended rather than left holding a pipe nobody can
        use again: once a reply is late, every later reply is the wrong one.
        """
        self.touched = time.monotonic()
        try:
            self.pipe.send(message)
        except (BrokenPipeError, OSError):
            self.die("the interpreter stopped")
            return {"ok": False, "error": self.dead_reason}
        if not self.pipe.poll(timeout):
            self.die("the cell ran for longer than {} seconds and was stopped".format(timeout))
            return {"ok": False, "error": self.dead_reason}
        try:
            return self.pipe.recv()
        except (EOFError, OSError):
            # The usual way a memory ceiling is reported: the child died
            # mid-answer rather than raising something it could send back.
            self.die("the interpreter stopped, which usually means the cell ran out of memory")
            return {"ok": False, "error": self.dead_reason}

    def interrupt(self):
        """
        Stop the current cell without ending the session.

        SIGINT arrives in the child as `KeyboardInterrupt`, which `run_cell`
        reports like any other failure -- so the variables assigned by earlier
        cells are still there afterwards. That is what stop should mean
        (design §4.6): cancel this cell, not throw the notebook away.
        """
        if not self.alive:
            return False
        if not self.running:
            # Nothing to cancel, so nothing is signalled. A SIGINT to an idle
            # child lands in the `recv()` it is waiting on, which ends it --
            # so stop on a notebook that happened not to be running would
            # throw away every variable in it. Stop cancels a cell; with no
            # cell running it is a no-op, which is what it looks like from the
            # page anyway.
            return False
        os.kill(self.process.pid, signal.SIGINT)
        deadline = time.monotonic() + STOP_GRACE_SECONDS
        while time.monotonic() < deadline:
            if not self.running:
                return True
            time.sleep(0.05)
        # It did not notice. Nothing polite interrupts `while True: pass`.
        self.die("the cell would not stop and the interpreter was ended")
        return True

    def die(self, reason):
        # The first reason wins. Whatever ended the session, the other thread
        # waiting on the pipe sees it close a moment later and would otherwise
        # report EOF -- "the interpreter stopped, which usually means the cell
        # ran out of memory" -- over the top of "the cell would not stop and
        # the interpreter was ended". Both are true; only the first is useful.
        if self.dead_reason is None:
            self.dead_reason = reason
        with contextlib.suppress(Exception):
            self.process.kill()
        with contextlib.suppress(Exception):
            self.pipe.close()

    def close(self):
        self.die("ended")
        shutil.rmtree(self.directory, ignore_errors=True)


def _authorised():
    given = request.headers.get("Authorization", "")
    if not TOKEN:
        return True
    return given.startswith("Bearer ") and hmac.compare_digest(given[len("Bearer ") :], TOKEN)


def _reap():
    """End sessions nobody has used. Cheap, and runs on every request."""
    now = time.monotonic()
    with _sessions_lock:
        gone = [s for s in _sessions.values() if now - s.touched > IDLE_SECONDS or not s.alive]
        for session in gone:
            _sessions.pop(session.id, None)
    for session in gone:
        session.close()


def _session_or_404(session_id):
    with _sessions_lock:
        return _sessions.get(session_id)


@app.before_request
def _gate():
    if request.path == "/ping":
        return None
    if not _authorised():
        return jsonify({"message": "not authorised"}), 401
    _reap()
    return None


@app.route("/ping")
def ping():
    with _sessions_lock:
        live = sum(1 for s in _sessions.values() if s.alive)
    # `spark` says whether cells here can reach a cluster. Whether one is
    # *attached* is deliberately not reported: the session opens on first use
    # inside a child, and asking every child would make a health check do work.
    return jsonify({"ok": True, "sessions": live, "capacity": MAX_SESSIONS, "spark": spark.configured()})


@app.route("/sessions", methods=["POST"])
def create_session():
    _reap()
    with _sessions_lock:
        if len(_sessions) >= MAX_SESSIONS:
            return (
                jsonify(
                    {
                        "message": "This interpreter is running {} sessions, which is all it is "
                        "configured for. Try again shortly, or raise "
                        "EXECUTOR_MAX_SESSIONS.".format(MAX_SESSIONS)
                    }
                ),
                503,
            )
    session = Session()
    answer = session.ask((PING,), 30)
    if not answer.get("ok"):
        session.close()
        return jsonify({"message": "The interpreter did not start: {}".format(answer.get("error"))}), 500
    with _sessions_lock:
        _sessions[session.id] = session
    return jsonify({"id": session.id}), 201


@app.route("/sessions/<session_id>/inputs/<name>", methods=["PUT"])
def put_input(session_id, name):
    """
    An earlier cell's output, as Parquet in the request body.

    Pushed rather than fetched. The executor has no route back to SQLDesk and
    no credential to use on one, which is the decision the whole boundary rests
    on -- so the data comes to it.
    """
    session = _session_or_404(session_id)
    if session is None or not session.alive:
        return jsonify({"message": "No such session."}), 404
    if not _is_a_name(name):
        return jsonify({"message": "{!r} is not a usable cell name.".format(name)}), 400

    body = request.get_data()
    if not body:
        return jsonify({"message": "No data was sent."}), 400
    if len(body) > MAX_INPUT_MB * 1024 * 1024:
        return (
            jsonify(
                {
                    "message": "That cell's result is {:.0f} MB, and this interpreter accepts {} MB. "
                    "Aggregate in the SQL cell above.".format(len(body) / 1048576.0, MAX_INPUT_MB)
                }
            ),
            413,
        )

    path = os.path.join(session.directory, "{}.parquet".format(name))
    with open(path, "wb") as handle:
        handle.write(body)
    with session.lock:
        answer = session.ask((INPUT, name, path), 120)
    if not answer.get("ok"):
        return jsonify({"message": answer.get("error", "The input could not be read.")}), 400
    return jsonify({"name": name, "bytes": len(body)})


@app.route("/sessions/<session_id>/run", methods=["POST"])
def run(session_id):
    session = _session_or_404(session_id)
    if session is None or not session.alive:
        return jsonify({"message": "No such session."}), 404
    code = (request.get_json(silent=True) or {}).get("code") or ""
    if not code.strip():
        return jsonify({"message": "There is no code in this cell."}), 400

    result_id = uuid.uuid4().hex
    out = os.path.join(session.directory, "{}.parquet".format(result_id))
    if not session.lock.acquire(timeout=1):
        return jsonify({"message": "This notebook is already running a cell."}), 409
    session.running = True
    try:
        answer = session.ask((RUN, code, out), RUN_SECONDS)
    finally:
        session.running = False
        session.lock.release()

    if not answer.get("ok"):
        return jsonify(
            {
                "ok": False,
                "error": answer.get("error"),
                "traceback": answer.get("traceback", ""),
                "stdout": answer.get("stdout", ""),
            }
        )
    frame = answer.get("frame")
    return jsonify(
        {
            "ok": True,
            "stdout": answer.get("stdout", ""),
            "value": answer.get("value"),
            # Present only when the cell's last expression was a dataframe --
            # which is what the next cell can read and what a visualization can
            # be put on.
            "result_id": result_id if frame else None,
        }
    )


@app.route("/sessions/<session_id>/results/<result_id>")
def result(session_id, result_id):
    session = _session_or_404(session_id)
    if session is None:
        return jsonify({"message": "No such session."}), 404
    if not _is_an_id(result_id):
        return jsonify({"message": "No such result."}), 404
    path = os.path.join(session.directory, "{}.parquet".format(result_id))
    if not os.path.exists(path):
        return jsonify({"message": "No such result."}), 404
    with open(path, "rb") as handle:
        body = handle.read()
    return Response(body, mimetype="application/vnd.apache.parquet")


@app.route("/sessions/<session_id>/stop", methods=["POST"])
def stop(session_id):
    session = _session_or_404(session_id)
    if session is None:
        return jsonify({"message": "No such session."}), 404
    stopped = session.interrupt()
    return jsonify({"stopped": stopped, "alive": session.alive})


@app.route("/sessions/<session_id>", methods=["DELETE"])
def end_session(session_id):
    with _sessions_lock:
        session = _sessions.pop(session_id, None)
    if session is None:
        return jsonify({"message": "No such session."}), 404
    session.close()
    return jsonify({"ended": session_id})


def _is_a_name(name):
    """The same rule SQLDesk applies to a cell name, restated at the boundary."""
    return (
        bool(name) and len(name) <= 63 and (name[0].isalpha() or name[0] == "_") and name.replace("_", "a").isalnum()
    )


def _is_an_id(value):
    """A result id is one of ours, so a path cannot be named through it."""
    return len(value) == 32 and all(character in "0123456789abcdef" for character in value)
