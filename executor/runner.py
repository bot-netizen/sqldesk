"""
The child process that holds one notebook session's variables.

A session is a process, not a thread and not a function call. `df` assigned in
one cell is still there five cells later because the process that assigned it
is still alive -- which is what people expect from Jupyter, and the thing a
stateless "run this code" endpoint cannot give them.

It is a child rather than the service itself for three reasons, in order of
how much they matter:

1. **It can be killed.** Stop means stop (design §4.6). You cannot interrupt
   arbitrary Python reliably from inside the same process -- `while True: pass`
   ignores every polite mechanism there is. A signal to a child, and a SIGKILL
   behind it, always works.
2. **It can be limited.** `setrlimit` is per process, so address space, CPU
   seconds and output size are a ceiling on *this session* rather than on the
   service that serves all of them.
3. **It starts clean.** Spawned, not forked: the child does not inherit the
   service's imported modules, its open sockets or its memory -- including the
   token the service checks requests against.

**No credential ever crosses into here, because none exists to cross.** A code
cell reads an earlier cell's output and nothing else (design §4.1), so the
executor has no API to reach, no data source to open and no reason to make a
single outbound connection. That is what makes the sandbox a sandbox rather
than a promise: there is nothing in it worth reaching.

Data arrives and leaves as Parquet, which carries its own types -- a timestamp
becomes a timestamp without either side agreeing on a string format, and a
column that is all null stays the type it was.
"""

import ast
import contextlib
import io
import os
import resource
import sys
import traceback

import spark

#: What the parent sends. Small and positional, because this travels over a
#: pipe and a protocol nobody can see is a protocol nobody can debug.
INPUT = "input"
RUN = "run"
PING = "ping"

#: The name the result of the last expression is reported under, and the name
#: a cell's own dataframe output is looked for in. Jupyter reports the value of
#: the final expression; this does the same, and additionally hands the next
#: cell a relation if that value is a dataframe.
VALUE = "value"

#: How much of `print()` is kept. A cell that prints in a loop is a cell
#: somebody is debugging, and the first few thousand lines of it say the same
#: thing as all of it.
MAX_OUTPUT = int(os.environ.get("EXECUTOR_MAX_OUTPUT", str(256 * 1024)))

#: How long a repr may be. The same argument: nobody reads the 400,000th
#: character of a dict.
MAX_REPR = int(os.environ.get("EXECUTOR_MAX_REPR", "10000"))


def limits(memory_mb, cpu_seconds, file_mb, max_processes=0):
    """
    The ceilings this process will not pass, set before any of somebody's code
    runs.

    `RLIMIT_CPU` is seconds *of CPU*, not wall clock, so a cell that waits does
    not spend it. The wall-clock deadline is the parent's job -- it is the one
    that can still answer a request while this process is busy.

    **`memory_mb` is off by default, and that is measured rather than lazy.**
    `RLIMIT_AS` caps *address space*, not resident memory, and both DuckDB and
    numpy reserve far more of it than they use -- thread stacks included. In
    this image:

        512 MB    the process dies before Python finishes importing
        2048 MB   DuckDB works; `import pandas` raises KeyboardInterrupt
        4096 MB   everything works

    So it cannot express "two gigabytes per session" at all: the smallest value
    the libraries tolerate is larger than the ceiling anybody wanted, and when
    it does bite it reports a stop rather than a limit. The container's own
    memory limit is the right ceiling -- it kills the child, the parent sees the
    pipe close and says the interpreter ran out of memory, which is the true
    sentence. The knob stays for an operator who wants a per-session cap on top
    and knows to keep it above 4 GB.
    """
    if memory_mb:
        allowed = memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (allowed, allowed))
    if cpu_seconds:
        # A soft limit one second below the hard one: the soft limit raises
        # SIGXCPU, which Python turns into something reportable, and the hard
        # limit is the backstop if that is ignored.
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1))
    if file_mb:
        allowed = file_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_FSIZE, (allowed, allowed))
    # `RLIMIT_NPROC` is off unless an operator asks for it, and this is the
    # measured reason rather than an oversight.
    #
    # It counts every process *and thread* the user owns across the whole
    # container, and numpy's BLAS starts a pool of them on import. Measured in
    # this image: a cap of 0 or 64 makes `import pandas` fail, a cap of 128
    # leaves pandas working and refuses a 35th process. Worse, OpenBLAS's
    # thread-init failure surfaces in Python as **`KeyboardInterrupt`** -- so a
    # cap set too low does not report a limit, it reports every cell as though
    # somebody had pressed stop.
    #
    # Since pandas is the entire point of a Python cell, the default is to
    # leave this to the container: the process runs unprivileged and, with
    # egress denied, a process it starts has nowhere to go. An operator who
    # wants the cap can set EXECUTOR_MAX_PROCESSES, and should start well above
    # 128 and test that pandas still imports.
    if max_processes:
        with contextlib.suppress(ValueError, OSError):
            resource.setrlimit(resource.RLIMIT_NPROC, (max_processes, max_processes))


#: What a cell may read out of the environment. A floor of what is needed
#: rather than a list of what to remove, because a list of what to remove is a
#: list somebody forgets to add to.
KEEP = ("PATH", "HOME", "LANG", "LC_ALL", "TZ", "TMPDIR", "PYTHONHASHSEED")


def scrub_environment():
    """
    Throw away everything in this process's environment but the floor.

    Done **here, in the child**, rather than by handing a trimmed environment
    to it. A spawned child inherits `os.environ` and there is no per-process
    override, so the parent would have to empty its own environment around the
    spawn -- and the parent is a threaded web server, where another request
    would see it emptied. This process is the only one that can do it safely,
    and it is the only one that needs to: the service's token lives in the
    environment it was started with.
    """
    for name in list(os.environ):
        if name not in KEEP:
            del os.environ[name]
    return dict(os.environ)


def _split(code):
    """
    The statements, and the final expression if there is one.

    `exec` returns nothing, so running a whole cell with it reports `None` for
    a cell whose last line is `df.describe()` -- which is most cells. Jupyter
    splits the last expression off and evaluates it; so does this, using the
    same mechanism (`ast`), because anything cleverer is a parser we would then
    own.
    """
    tree = ast.parse(code, filename="<cell>", mode="exec")
    if tree.body and isinstance(tree.body[-1], ast.Expr):
        last = ast.Expression(tree.body[-1].value)
        return ast.Module(body=tree.body[:-1], type_ignores=[]), last
    return tree, None


def _frame_out(value, path):
    """
    A dataframe written where the parent can fetch it, or None.

    DuckDB does the writing, reading the dataframe in place: its Parquet writer
    is native, so neither this container nor SQLDesk's needs pyarrow -- which
    is 40 MB and absent from both.
    """
    try:
        import duckdb
        import pandas
    except ImportError:
        return None
    if spark.is_a_spark_frame(value):
        # The one moment the cluster's result has to fit in this container.
        # `collect` refuses rather than truncating: a notebook that quietly
        # showed the first million rows of a billion would be worse than one
        # that said no.
        value = spark.collect(value)
    if not isinstance(value, pandas.DataFrame):
        return None
    connection = duckdb.connect()
    try:
        connection.register("cell_output", value)
        connection.execute("COPY cell_output TO ? (FORMAT PARQUET)", [path])
    finally:
        connection.close()
    return path


def _described(value):
    """What to show on the page for a value that is not a dataframe."""
    if value is None:
        return None
    try:
        shown = repr(value)
    except Exception as e:  # a __repr__ of somebody's own can raise
        return "<a value whose repr() raised {}>".format(type(e).__name__)
    return shown[:MAX_REPR]


def run_cell(namespace, code, parquet_path):
    """
    Run one cell in this session's namespace. Returns what to report.

    Errors come back as a value rather than an exception: a cell that raises is
    an ordinary outcome of a notebook, and the session survives it with every
    variable still in place -- which is the behaviour that makes a notebook
    worth using in the first place.
    """
    printed = io.StringIO()
    try:
        statements, final = _split(code)
    except SyntaxError as e:
        return {"ok": False, "error": "{}: {}".format(type(e).__name__, e), "traceback": "", "stdout": ""}

    value = None
    try:
        with contextlib.redirect_stdout(printed), contextlib.redirect_stderr(printed):
            exec(compile(statements, "<cell>", "exec"), namespace)
            if final is not None:
                value = eval(compile(final, "<cell>", "eval"), namespace)
    except BaseException as e:
        # BaseException, so that a cell stopped with SIGINT (KeyboardInterrupt)
        # and one that hit the CPU limit are reported like any other failure
        # instead of taking the session down with them.
        return {
            "ok": False,
            "error": "{}: {}".format(type(e).__name__, e),
            # The frames inside this module are ours and mean nothing to the
            # person reading the error; theirs start at the cell.
            "traceback": "".join(traceback.format_exception_only(type(e), e)),
            "stdout": printed.getvalue()[:MAX_OUTPUT],
        }

    frame = _frame_out(value, parquet_path) if parquet_path else None
    return {
        "ok": True,
        "stdout": printed.getvalue()[:MAX_OUTPUT],
        VALUE: None if frame else _described(value),
        "frame": frame,
    }


def load_input(namespace, name, path):
    """
    An earlier cell's output, as a dataframe under its own name.

    Read through DuckDB rather than `pandas.read_parquet`, which needs pyarrow.
    The types survive the trip because Parquet carries them.
    """
    import duckdb

    connection = duckdb.connect()
    try:
        namespace[name] = connection.execute("SELECT * FROM read_parquet(?)", [path]).df()
    finally:
        connection.close()
    return name


def serve(pipe, options):
    """
    The child's whole life: set the ceilings, then answer the parent.

    Runs until the pipe closes or the parent kills it. Nothing here loops
    waiting on the network, because there is no network to wait on.
    """
    scrub_environment()
    limits(
        options.get("memory_mb"),
        options.get("cpu_seconds"),
        options.get("file_mb"),
        options.get("max_processes") or 0,
    )
    # The builtins module explicitly: `__builtins__` is the module here and a
    # dict inside `__main__`, and a namespace that got the wrong one of those
    # fails in a way that depends on how this file was started.
    import builtins

    namespace = {"__name__": "__notebook__", "__builtins__": builtins}
    # `spark` only when this executor has a cluster, and even then only as a
    # handle: the session opens the first time a cell reaches through it, so a
    # notebook nobody has run Spark in has opened nothing.
    if spark.configured():
        namespace["spark"] = spark.Handle()

    while True:
        try:
            message = pipe.recv()
        except (EOFError, KeyboardInterrupt):
            return
        kind = message[0]
        try:
            if kind == PING:
                pipe.send({"ok": True})
            elif kind == INPUT:
                _, name, path = message
                load_input(namespace, name, path)
                pipe.send({"ok": True, "name": name})
            elif kind == RUN:
                _, code, parquet_path = message
                pipe.send(run_cell(namespace, code, parquet_path))
            else:
                pipe.send({"ok": False, "error": "unknown request {!r}".format(kind)})
        except BaseException as e:
            # Including a KeyboardInterrupt that arrived between cells: the
            # session stays up, and the parent hears why this one did not work.
            with contextlib.suppress(Exception):
                pipe.send({"ok": False, "error": "{}: {}".format(type(e).__name__, e)})


def main():
    """Entry point when the parent spawns this module directly."""
    from multiprocessing.connection import Connection

    fd = int(sys.argv[1])
    serve(Connection(fd), {})


if __name__ == "__main__":
    main()
