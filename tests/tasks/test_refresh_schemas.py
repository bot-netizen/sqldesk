from mock import patch

from sqldesk.tasks import refresh_schemas
from tests import BaseTestCase


class TestRefreshSchemas(BaseTestCase):
    def test_calls_refresh_of_all_data_sources(self):
        self.factory.data_source  # trigger creation
        with patch("sqldesk.tasks.queries.maintenance.refresh_schema.delay") as refresh_job:
            refresh_schemas()
            refresh_job.assert_called()

    def test_skips_paused_data_sources(self):
        self.factory.data_source.pause()

        with patch("sqldesk.tasks.queries.maintenance.refresh_schema.delay") as refresh_job:
            refresh_schemas()
            refresh_job.assert_not_called()

        self.factory.data_source.resume()

        with patch("sqldesk.tasks.queries.maintenance.refresh_schema.delay") as refresh_job:
            refresh_schemas()
            refresh_job.assert_called()
