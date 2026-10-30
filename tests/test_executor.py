"""
The interpreter sidecar: the session, the ceilings, and the stop.

These run the real child process, not a mock of it. Every claim this service
makes is about what happens when somebody else's code is running -- that it
cannot take the service down, cannot outlive a stop, cannot read the token out
of the environment -- and none of those can be tested against a stand-in for
the thing doing the running.

The service imports `runner` as a top-level module, as it does in its own
container where both files sit in `/app`. So does this.
"""

import os
import sys
import tempfile
import unittest

import duckdb

EXECUTOR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "executor")
if EXECUTOR not in sys.path:
    sys.path.insert(0, EXECUTOR)

try:
    import pandas  # noqa: F401

    HAVE_PANDAS = True
except ImportError:  # pragma: no cover
    HAVE_PANDAS = False


def _quoted(columns):
    """
    Column declarations with the names quoted. `at` is a reserved word in
    DuckDB -- in 1.5.6 and in 2.0.0 alike -- and a timestamp column called
    `at` is exactly what a stream or an event table has.
    """
    declared = []
    for one in columns.split(","):
        name, _, kind = one.strip().partition(" ")
        declared.append('"{}" {}'.format(name, kind))
    return ", ".join(declared)


def parquet_of(rows, columns="id INTEGER, city VARCHAR"):
    """A Parquet file, as a SQL cell's handoff would arrive."""
    handle = tempfile.NamedTemporaryFile(suffix=".parquet", delete=False)
    handle.close()
    connection = duckdb.connect()
    try:
        connection.execute("CREATE TABLE source ({})".format(_quoted(columns)))
        for row in rows:
            connection.execute("INSERT INTO source VALUES ({})".format(", ".join("?" for _ in row)), list(row))
        connection.execute("COPY source TO ? (FORMAT PARQUET)", [handle.name])
    finally:
        connection.close()
    with open(handle.name, "rb") as reading:
        body = reading.read()
    os.unlink(handle.name)
    return body


@unittest.skipUnless(HAVE_PANDAS, "the interpreter needs pandas")
class ExecutorTestCase(unittest.TestCase):
    """
    One session per test, really started and really ended.

    The limits are set small so the tests that prove they bite take a second
    rather than a minute.
    """

    #: Unset, as in the image: the measurement for why is in `runner.limits`.
    MEMORY_MB = 0
    CPU_SECONDS = 10
    RUN_SECONDS = 20

    @classmethod
    def setUpClass(cls):
        import service

        cls.service = service
        service.TOKEN = "a-test-token"
        service.MEMORY_MB = cls.MEMORY_MB
        service.CPU_SECONDS = cls.CPU_SECONDS
        service.RUN_SECONDS = cls.RUN_SECONDS
        service.app.config["TESTING"] = True

    def setUp(self):
        self.client = self.service.app.test_client()
        self.headers = {"Authorization": "Bearer a-test-token"}
        self.session_id = None

    def tearDown(self):
        for session in list(self.service._sessions.values()):
            self.service._sessions.pop(session.id, None)
            session.close()

    # --- helpers ------------------------------------------------------------

    def start(self):
        answer = self.client.post("/sessions", headers=self.headers)
        self.assertEqual(201, answer.status_code, answer.get_data(as_text=True))
        self.session_id = answer.get_json()["id"]
        return self.session_id

    def cell(self, code, session_id=None):
        answer = self.client.post(
            "/sessions/{}/run".format(session_id or self.session_id),
            json={"code": code},
            headers=self.headers,
        )
        return answer.get_json()

    def give(self, name, body, session_id=None):
        return self.client.put(
            "/sessions/{}/inputs/{}".format(session_id or self.session_id, name),
            data=body,
            headers=self.headers,
        )


class TestASession(ExecutorTestCase):
    def test_a_session_starts_and_answers(self):
        self.start()

        answer = self.cell("1 + 1")

        self.assertTrue(answer["ok"], answer)
        self.assertEqual("2", answer["value"])

    def test_variables_survive_between_cells(self):
        """
        What makes it a notebook rather than a form that runs code. `df`
        assigned in one cell is still there five cells later.
        """
        self.start()

        self.cell("total = 0")
        for _ in range(5):
            self.cell("total = total + 1")
        answer = self.cell("total")

        self.assertEqual("5", answer["value"])

    def test_print_comes_back(self):
        self.start()

        answer = self.cell("print('working'); None")

        self.assertIn("working", answer["stdout"])

    def test_the_last_expression_is_the_result_as_in_jupyter(self):
        self.start()

        answer = self.cell("x = 2\nx * 21")

        self.assertEqual("42", answer["value"])

    def test_a_cell_that_raises_leaves_the_session_standing(self):
        """
        The behaviour that makes a notebook usable: an error is an ordinary
        outcome, and every variable is still there afterwards.
        """
        self.start()
        self.cell("kept = 'here'")

        failed = self.cell("1 / 0")
        after = self.cell("kept")

        self.assertFalse(failed["ok"])
        self.assertIn("ZeroDivisionError", failed["error"])
        self.assertEqual("'here'", after["value"])

    def test_a_syntax_error_is_reported_rather_than_raised(self):
        self.start()

        answer = self.cell("def (")

        self.assertFalse(answer["ok"])
        self.assertIn("SyntaxError", answer["error"])

    def test_an_empty_cell_is_refused_before_anything_runs(self):
        self.start()

        answer = self.client.post(
            "/sessions/{}/run".format(self.session_id), json={"code": "   "}, headers=self.headers
        )

        self.assertEqual(400, answer.status_code)

    def test_ending_a_session_ends_the_process(self):
        session_id = self.start()
        session = self.service._sessions[session_id]

        self.client.delete("/sessions/{}".format(session_id), headers=self.headers)

        self.assertFalse(session.alive)
        self.assertFalse(os.path.exists(session.directory))

    def test_a_session_that_does_not_exist_is_a_404(self):
        self.assertEqual(
            404, self.client.post("/sessions/nope/run", json={"code": "1"}, headers=self.headers).status_code
        )


class TestWhatCrossesTheBoundary(ExecutorTestCase):
    def test_an_earlier_cells_output_arrives_as_a_dataframe(self):
        self.start()

        given = self.give("orders", parquet_of([(1, "Toronto"), (2, "Ottawa")]))
        answer = self.cell("len(orders)")

        self.assertEqual(200, given.status_code, given.get_data(as_text=True))
        self.assertEqual("2", answer["value"])

    def test_the_types_survive_the_trip(self):
        """
        Parquet in both directions so a timestamp is a timestamp, with no
        agreed string format and no pyarrow in either container.
        """
        self.start()
        body = parquet_of([(1, "2026-10-30 09:00:00")], columns="id INTEGER, at TIMESTAMP")

        self.give("events", body)
        answer = self.cell("str(events['at'].dtype)")

        self.assertIn("datetime64", answer["value"])

    def test_a_dataframe_result_comes_back_as_parquet(self):
        self.start()
        self.give("orders", parquet_of([(1, "Toronto"), (2, "Ottawa")]))

        answer = self.cell("orders.head(1)")
        fetched = self.client.get(
            "/sessions/{}/results/{}".format(self.session_id, answer["result_id"]), headers=self.headers
        )

        self.assertIsNotNone(answer["result_id"], answer)
        self.assertEqual(200, fetched.status_code)
        handle = tempfile.NamedTemporaryFile(suffix=".parquet", delete=False)
        handle.write(fetched.get_data())
        handle.close()
        try:
            rows = duckdb.connect().execute("SELECT * FROM read_parquet(?)", [handle.name]).fetchall()
        finally:
            os.unlink(handle.name)
        self.assertEqual([(1, "Toronto")], rows)

    def test_a_value_that_is_not_a_dataframe_has_no_result_to_fetch(self):
        self.start()

        answer = self.cell("'just a string'")

        self.assertIsNone(answer["result_id"])
        self.assertEqual("'just a string'", answer["value"])

    def test_a_result_id_cannot_name_another_file_in_the_session(self):
        """
        A result id is one of ours -- 32 hex characters -- and is checked rather
        than just joined onto a path. The file that proves it is an *input*,
        which really exists in the session's directory under a name of the
        caller's choosing: without the check, asking for it as a result hands
        it back.
        """
        self.start()
        self.give("orders", parquet_of([(1, "Toronto")]))

        answer = self.client.get("/sessions/{}/results/orders".format(self.session_id), headers=self.headers)

        self.assertEqual(404, answer.status_code, "an input was served as a result")

    def test_a_result_id_cannot_climb_out_of_the_directory(self):
        self.start()

        answer = self.client.get(
            "/sessions/{}/results/..%2f..%2fetc%2fpasswd".format(self.session_id), headers=self.headers
        )

        self.assertEqual(404, answer.status_code)

    def test_a_cell_name_that_is_not_a_name_is_refused(self):
        self.start()

        answer = self.give("../escape", parquet_of([(1, "x")]))

        self.assertIn(answer.status_code, (400, 404))

    def test_an_input_bigger_than_the_ceiling_says_what_to_do_about_it(self):
        self.start()
        self.service.MAX_INPUT_MB = 0
        self.addCleanup(setattr, self.service, "MAX_INPUT_MB", 512)

        answer = self.give("orders", parquet_of([(1, "Toronto")]))

        self.assertEqual(413, answer.status_code)
        self.assertIn("Aggregate", answer.get_json()["message"])


class TestTheCeilings(ExecutorTestCase):
    def test_a_cell_cannot_read_the_services_token(self):
        """
        The child scrubs its own environment, because the parent cannot: it is
        a threaded web server, and emptying its environment around a spawn
        would empty it for every other request in flight.

        The token goes into the real environment first. Setting `service.TOKEN`
        alone would leave nothing for the child to inherit, and this test would
        pass with the scrubbing deleted -- which is exactly what it did until a
        mutant pointed it out.
        """
        os.environ["EXECUTOR_TOKEN"] = "a-test-token"
        os.environ["AWS_SECRET_ACCESS_KEY"] = "not-a-real-key"
        self.addCleanup(os.environ.pop, "EXECUTOR_TOKEN", None)
        self.addCleanup(os.environ.pop, "AWS_SECRET_ACCESS_KEY", None)
        self.start()

        answer = self.cell("import os; sorted(n for n in os.environ if 'TOKEN' in n or 'SECRET' in n)")

        self.assertEqual("[]", answer["value"], "a cell can read the environment the service was given")

    def test_the_memory_knob_bites_at_a_value_the_libraries_tolerate(self):
        """
        Set to 4 GB -- the smallest value that leaves pandas and DuckDB able to
        load -- and asked for eight. Reserved rather than written, so the test
        costs no actual memory: the address space is what the limit counts.
        """
        self.service.MEMORY_MB = 4096
        self.addCleanup(setattr, self.service, "MEMORY_MB", 0)
        self.start()

        answer = self.cell("import mmap\nmmap.mmap(-1, 8 * 1024 ** 3)")

        self.assertFalse(answer["ok"], "the memory ceiling did not bite")

    def test_a_session_that_died_is_reported_rather_than_hung(self):
        self.start()
        self.cell("import os; os._exit(1)")

        answer = self.cell("1 + 1")

        # Either the run says the interpreter stopped, or the session has
        # already been reaped and the request is a 404. Both are honest; a
        # hang would not be.
        self.assertTrue(answer is None or not answer.get("ok"), answer)

    def test_the_process_cap_refuses_a_subprocess_when_an_operator_sets_it(self):
        """
        Off by default -- a cap low enough to matter stops `import pandas`
        working, which `runner.limits` records the measurement for. This proves
        the knob does what it says for an operator who accepts that trade.
        """
        self.service.MAX_PROCESSES = 1
        self.addCleanup(setattr, self.service, "MAX_PROCESSES", 0)
        self.start()

        answer = self.cell("import subprocess; subprocess.run(['/bin/true'])")

        self.assertFalse(answer["ok"], "a cell started a process under the cap")

    def test_a_cell_can_use_pandas_by_default(self):
        """
        The other half of that trade, and the reason the cap is off: a cell
        whose whole purpose is a dataframe has to be able to make one.
        """
        self.start()

        answer = self.cell("import pandas; len(pandas.DataFrame({'a': [1, 2, 3]}))")

        self.assertTrue(answer["ok"], answer)
        self.assertEqual("3", answer["value"])


class TestStopping(ExecutorTestCase):
    """
    Stop means cancel the current cell and do not start the next (design §4.6)
    -- not throw the notebook away.

    Each cell here announces that it has reached its loop by touching a file in
    the session's own directory, and the stop waits for that. Without it the
    tests race: `running` is set before the code has even reached the child, so
    a stop can land while it is still idle, and then these are measuring
    something else.
    """

    def ready_path(self):
        session = self.service._sessions[self.session_id]
        return os.path.join(session.directory, "ready")

    def wait_until_ready(self, seconds=15):
        import time

        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if os.path.exists(self.ready_path()):
                return
            time.sleep(0.02)
        self.fail("the cell never reached its loop")

    def in_the_background(self, code):
        import threading

        answers = []
        thread = threading.Thread(target=lambda: answers.append(self.cell(code)))
        thread.start()
        return thread, answers

    def stop_now(self):
        """Its own client: the one the busy thread holds is mid-request."""
        return self.service.app.test_client().post("/sessions/{}/stop".format(self.session_id), headers=self.headers)

    def test_stopping_a_busy_cell_ends_the_cell_not_the_notebook(self):
        self.start()
        self.cell("kept = 'here'")
        thread, answers = self.in_the_background(
            "import pathlib, time\n"
            "pathlib.Path({!r}).touch()\n"
            "while True:\n"
            "    time.sleep(0.05)".format(self.ready_path())
        )
        try:
            self.wait_until_ready()
            stopped = self.stop_now()
        finally:
            thread.join(timeout=self.RUN_SECONDS + 5)

        self.assertEqual(200, stopped.status_code)
        self.assertFalse(thread.is_alive(), "the cell did not stop")
        self.assertFalse(answers[0]["ok"])
        self.assertIn("KeyboardInterrupt", answers[0]["error"])
        self.assertEqual("'here'", self.cell("kept")["value"], "stopping threw the notebook away")

    def test_a_cell_that_will_not_stop_is_killed(self):
        """
        Nothing polite interrupts `while True: pass`, so after the grace period
        the session ends. Told, not hidden.
        """
        self.start()
        self.service.STOP_GRACE_SECONDS = 0.5
        self.addCleanup(setattr, self.service, "STOP_GRACE_SECONDS", 3.0)
        session = self.service._sessions[self.session_id]
        thread, _ = self.in_the_background(
            "import pathlib, signal\n"
            "signal.signal(signal.SIGINT, signal.SIG_IGN)\n"
            "pathlib.Path({!r}).touch()\n"
            "while True:\n"
            "    pass".format(self.ready_path())
        )
        try:
            self.wait_until_ready()
            stopped = self.stop_now()
        finally:
            thread.join(timeout=self.RUN_SECONDS + 5)

        self.assertEqual(200, stopped.status_code)
        self.assertFalse(thread.is_alive(), "the cell outlived the stop")
        self.assertFalse(session.alive, "the session is still alive; reason={!r}".format(session.dead_reason))
        self.assertIn("would not stop", session.dead_reason)

    def test_stopping_an_idle_notebook_does_not_throw_it_away(self):
        """
        A SIGINT to an idle child lands in the `recv()` it is waiting on and
        ends it. So stop with nothing running must not signal at all -- or
        pressing it on a notebook that happened to be between cells would cost
        somebody every variable they had.
        """
        self.start()
        self.cell("kept = 'here'")
        session = self.service._sessions[self.session_id]

        stopped = self.stop_now()

        self.assertEqual(200, stopped.status_code)
        self.assertFalse(stopped.get_json()["stopped"], "it claimed to stop a cell that was not running")
        self.assertTrue(session.alive, "stop ended an idle session")
        self.assertEqual("'here'", self.cell("kept")["value"], "stop lost the notebook's variables")


class TestWhoMayAsk(ExecutorTestCase):
    def test_without_the_token_nothing_is_served(self):
        self.assertEqual(401, self.client.post("/sessions").status_code)

    def test_with_the_wrong_token_nothing_is_served(self):
        answer = self.client.post("/sessions", headers={"Authorization": "Bearer not-it"})

        self.assertEqual(401, answer.status_code)

    def test_ping_answers_without_a_token_so_a_probe_can_use_it(self):
        answer = self.client.get("/ping")

        self.assertEqual(200, answer.status_code)
        self.assertTrue(answer.get_json()["ok"])

    def test_more_sessions_than_the_ceiling_are_refused_with_a_reason(self):
        self.service.MAX_SESSIONS = 1
        self.addCleanup(setattr, self.service, "MAX_SESSIONS", 8)
        self.start()

        answer = self.client.post("/sessions", headers=self.headers)

        self.assertEqual(503, answer.status_code)
        self.assertIn("sessions", answer.get_json()["message"])
