from unittest.mock import MagicMock, patch

from tealdash import rq_redis_connection
from tealdash.monitor import rq_job_ids


def test_rq_job_ids_uses_rq_redis_connection():
    mock_queue = MagicMock()
    mock_queue.job_ids = []

    mock_registry = MagicMock()
    mock_registry.get_job_ids.return_value = []

    with patch("tealdash.monitor.Queue") as mock_Queue, patch(
        "tealdash.monitor.StartedJobRegistry"
    ) as mock_StartedJobRegistry:
        mock_Queue.all.return_value = [mock_queue]
        mock_StartedJobRegistry.return_value = mock_registry

        rq_job_ids()

        mock_Queue.all.assert_called_once_with(connection=rq_redis_connection)
        mock_StartedJobRegistry.assert_called_once_with(queue=mock_queue)
