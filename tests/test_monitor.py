from unittest.mock import MagicMock, patch

from sqldesk import rq_redis_connection
from sqldesk.monitor import rq_job_ids


def test_rq_job_ids_uses_rq_redis_connection():
    mock_queue = MagicMock()
    mock_queue.job_ids = []

    mock_registry = MagicMock()
    mock_registry.get_job_ids.return_value = []

    with patch("sqldesk.monitor.Queue") as mock_Queue, patch(
        "sqldesk.monitor.StartedJobRegistry"
    ) as mock_StartedJobRegistry:
        mock_Queue.all.return_value = [mock_queue]
        mock_StartedJobRegistry.return_value = mock_registry

        rq_job_ids()

        mock_Queue.all.assert_called_once_with(connection=rq_redis_connection)
        mock_StartedJobRegistry.assert_called_once_with(queue=mock_queue)


class _AJob:
    """Only the attributes `fetch_jobs` reads off an RQ job."""

    def __init__(self, job_id):
        self.id = job_id
        self.func_name = "sqldesk.tasks.queries.execution.execute_query"
        self.origin = "queries"
        self.enqueued_at = None
        self.started_at = None
        self.meta = {}


def _fetch_many_like_rq(job_ids, connection=None, serializer=None):
    """
    RQ's own `Job.fetch_many`, in the one respect that matters.

    It walks `job_ids` **twice**: once to queue the pipeline commands, and
    again to pair the answers back up with the ids. A generator is exhausted
    by the first pass, so the second pairs nothing -- and it returns an empty
    list rather than raising, which is what made this invisible.
    """
    for _ in job_ids:
        pass
    return [_AJob(job_id) for job_id in job_ids]


def test_fetch_jobs_survives_a_generator():
    """
    Running Queries was empty on every install.

    `started_job_ids()` is built with `funcy.flatten`, which is lazy, and it
    was handed straight to `fetch_jobs`. Proven on a running cluster against a
    real `pg_sleep`: one started job id, `fetch_jobs(list)` returned it,
    `fetch_jobs(generator)` returned nothing, and the page showed no rows.

    The existing tests all mocked `fetch_jobs` itself, which is precisely
    where the fault lived.
    """
    from sqldesk import monitor

    with patch.object(monitor.Job, "fetch_many", side_effect=_fetch_many_like_rq):
        jobs = monitor.fetch_jobs(one for one in ["a", "b"])

    assert [job["id"] for job in jobs] == ["a", "b"]


def test_started_job_ids_is_a_sequence_that_can_be_read_twice():
    mock_queue = MagicMock()
    mock_registry = MagicMock()
    mock_registry.get_job_ids.return_value = ["x", "y"]

    with patch("sqldesk.monitor.Queue") as mock_Queue, patch(
        "sqldesk.monitor.StartedJobRegistry"
    ) as mock_StartedJobRegistry:
        mock_Queue.all.return_value = [mock_queue]
        mock_StartedJobRegistry.return_value = mock_registry

        from sqldesk.monitor import started_job_ids

        ids = started_job_ids()

    assert list(ids) == ["x", "y"]
    # Again: a generator would be spent by now, and whatever read it second
    # would quietly see nothing.
    assert list(ids) == ["x", "y"]
