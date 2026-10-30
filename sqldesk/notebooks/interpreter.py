"""
SQLDesk's side of the boundary: talking to the interpreter.

Everything about this is one-directional on purpose. SQLDesk opens a session,
pushes the data a cell needs, asks for the cell to run, and pulls the result
back. The interpreter never calls here -- it has no address for us, no
credential to use and, because a code cell reads only an earlier cell's output
(design §4.1), nothing it would need us for.

**A session belongs to a notebook, and lives in Redis.** Not in a process:
the web server and the workers are separate processes and there may be several
of each, so "which interpreter session is this notebook using" has to be
answerable from any of them. Redis already holds exactly this kind of fact,
and a TTL is the idle timeout -- the same one the interpreter applies at its
end, so neither side keeps a session the other has given up on.

**Opening a notebook attaches nothing** (design §4.4). A session is created by
the first run, and the page says the interpreter is not attached until then.
A Spark session takes 30-60 seconds to come up; if opening a notebook paid
that, nothing about the product would feel like a BI tool.
"""

import logging
import os
import re
import tempfile

import requests

from sqldesk import redis_connection, settings

logger = logging.getLogger(__name__)

#: How a Python cell refers to an earlier cell: as a bare name, because that is
#: what the dataframe is called in its namespace. Word boundaries, so `orders`
#: does not match `orders_total` -- and intersected with the notebook's real
#: cell names afterwards, so an ordinary variable is not mistaken for a
#: reference to a cell that happens to share its name.
WORD = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\b")

#: Where a notebook's session id is kept, and for how long. A little longer
#: than the interpreter's own idle timeout, so the interpreter is always the
#: one that decides a session is finished -- if this expired first, SQLDesk
#: would open a second session while the first was still holding memory.
SESSION_KEY = "notebook:{}:session"
SESSION_TTL = 1200

#: How long to wait on the interpreter. Starting a session is quick; a cell is
#: as slow as somebody's code, and the interpreter has its own deadline for
#: that, so this one only has to be longer than it.
CONNECT_TIMEOUT = 5
START_TIMEOUT = 60
RUN_TIMEOUT = 600


class NoInterpreter(Exception):
    """There is nowhere to run Python. Carries the sentence for the cell."""


class Gone(Exception):
    """The session we had is not there any more. Recoverable: open another."""


def configured():
    return bool(settings.NOTEBOOK_EXECUTOR_URL)


def references(code, names):
    """
    Which earlier cells this code mentions, in the order they first appear.

    Used to decide what to ship, which is the whole reason it matters: a
    notebook whose first cell fetched four million rows should not send them to
    the interpreter for a cell that does not look at them.
    """
    canonical = {name: True for name in names}
    found = []
    for word in WORD.findall(code or ""):
        if word in canonical and word not in found:
            found.append(word)
    return found


class Interpreter:
    """
    One install's interpreter, as seen from here.

    Stateless except for what Redis holds, so a worker that picks up the next
    cell of a notebook finds the same session the last one used.
    """

    def __init__(self, url=None, token=None):
        self.url = (url or settings.NOTEBOOK_EXECUTOR_URL or "").rstrip("/")
        self.token = token if token is not None else settings.NOTEBOOK_EXECUTOR_TOKEN
        if not self.url:
            raise NoInterpreter(
                "Python cells need an interpreter, and this install has none configured. "
                "An administrator can turn on the executor, or a SQL cell can do this work."
            )

    # --- plumbing -----------------------------------------------------------

    @property
    def headers(self):
        return {"Authorization": "Bearer {}".format(self.token)} if self.token else {}

    def _call(self, method, path, timeout, **kwargs):
        try:
            answer = requests.request(
                method, "{}{}".format(self.url, path), headers=self.headers, timeout=timeout, **kwargs
            )
        except requests.RequestException as e:
            logger.warning("the interpreter at %s did not answer: %s", self.url, e)
            raise NoInterpreter("The interpreter did not answer. An administrator can check that it is running.")
        if answer.status_code == 404:
            raise Gone("that session is finished")
        if answer.status_code == 401:
            raise NoInterpreter(
                "The interpreter refused this SQLDesk. Its token and " "SQLDESK_NOTEBOOK_EXECUTOR_TOKEN have to match."
            )
        return answer

    # --- sessions -----------------------------------------------------------

    def session_for(self, notebook, create=True):
        """
        This notebook's session, opening one if it has none.

        `create=False` is how the page asks whether an interpreter is attached
        without attaching one.
        """
        key = SESSION_KEY.format(notebook.id)
        existing = redis_connection.get(key)
        if existing:
            session_id = existing.decode() if isinstance(existing, bytes) else existing
            # Touched on every use, at both ends: the TTL here and the idle
            # timer there both start again.
            redis_connection.expire(key, SESSION_TTL)
            return session_id
        if not create:
            return None

        answer = self._call("POST", "/sessions", START_TIMEOUT)
        if answer.status_code == 503:
            raise NoInterpreter(_said(answer, "The interpreter is busy. Try again shortly."))
        if answer.status_code != 201:
            raise NoInterpreter(_said(answer, "The interpreter could not start a session."))
        session_id = answer.json()["id"]
        redis_connection.setex(key, SESSION_TTL, session_id)
        return session_id

    def attached(self, notebook):
        """Whether a session exists, without making one."""
        return self.session_for(notebook, create=False) is not None

    def detach(self, notebook):
        """End the session and forget it. Its variables go with it."""
        key = SESSION_KEY.format(notebook.id)
        session_id = self.session_for(notebook, create=False)
        redis_connection.delete(key)
        if session_id:
            try:
                self._call("DELETE", "/sessions/{}".format(session_id), CONNECT_TIMEOUT)
            except (NoInterpreter, Gone):
                # Already gone, or unreachable. Either way this notebook has no
                # session now, which is what was asked for.
                pass
        return session_id

    def stop(self, notebook):
        """
        Cancel the cell that is running. The session and its variables stay
        (design §4.6).
        """
        session_id = self.session_for(notebook, create=False)
        if not session_id:
            return False
        try:
            answer = self._call("POST", "/sessions/{}/stop".format(session_id), CONNECT_TIMEOUT)
        except Gone:
            return False
        return bool(answer.json().get("stopped"))

    # --- the work -----------------------------------------------------------

    def ship(self, notebook, session_id, store, names):
        """
        Push each named cell's handoff to the interpreter as Parquet.

        Exported to a temporary file inside the notebook's own directory, which
        is the only place the store is allowed to write, and removed afterwards
        -- a cell sealed into that directory can read what is left there.
        """
        for name in names:
            handle = tempfile.NamedTemporaryFile(dir=store.directory, prefix="ship-", suffix=".parquet", delete=False)
            handle.close()
            try:
                store.export(name, handle.name)
                with open(handle.name, "rb") as reading:
                    answer = self._call(
                        "PUT",
                        "/sessions/{}/inputs/{}".format(session_id, name),
                        RUN_TIMEOUT,
                        data=reading.read(),
                    )
            finally:
                try:
                    os.remove(handle.name)
                except OSError:
                    pass
            if answer.status_code != 200:
                raise RuntimeError(_said(answer, "{} could not be sent to the interpreter.".format(name)))

    def run(self, session_id, code):
        """Run one cell. Returns the interpreter's answer as it came."""
        answer = self._call("POST", "/sessions/{}/run".format(session_id), RUN_TIMEOUT, json={"code": code})
        if answer.status_code != 200:
            raise RuntimeError(_said(answer, "The interpreter refused to run this cell."))
        return answer.json()

    def fetch(self, session_id, result_id, into):
        """Pull a cell's dataframe back as Parquet, to `into`."""
        answer = self._call("GET", "/sessions/{}/results/{}".format(session_id, result_id), RUN_TIMEOUT)
        if answer.status_code != 200:
            raise RuntimeError(_said(answer, "The interpreter's result could not be read back."))
        with open(into, "wb") as handle:
            handle.write(answer.content)
        return into


def _said(answer, otherwise):
    """The interpreter's own sentence, if it sent one."""
    try:
        message = (answer.json() or {}).get("message")
    except ValueError:
        message = None
    return message or otherwise
