from unittest import mock

from sqldesk import settings
from sqldesk.tasks.catalog import harvest_catalog, harvest_catalogs
from sqldesk.tasks.schedule import periodic_job_definitions
from tests import BaseTestCase


class TestHarvestSchedule(BaseTestCase):
    """
    The catalog used to fill only when somebody remembered to run a command,
    which meant an install that never did had context tools answering with
    nothing at all.
    """

    def _funcs(self):
        return [job["func"].__name__ for job in periodic_job_definitions()]

    def test_it_is_scheduled_when_the_feature_is_on(self):
        with mock.patch.object(settings, "FEATURE_AI", True), mock.patch.object(
            settings, "CATALOG_HARVEST_SCHEDULE", 24
        ):
            self.assertIn("harvest_catalogs", self._funcs())

    def test_it_is_not_scheduled_when_the_feature_is_off(self):
        with mock.patch.object(settings, "FEATURE_AI", False):
            self.assertNotIn("harvest_catalogs", self._funcs())

    def test_zero_turns_it_off_for_people_who_run_it_themselves(self):
        with mock.patch.object(settings, "FEATURE_AI", True), mock.patch.object(
            settings, "CATALOG_HARVEST_SCHEDULE", 0
        ):
            self.assertNotIn("harvest_catalogs", self._funcs())


class TestHarvestFanOut(BaseTestCase):
    def test_one_job_per_data_source(self):
        self.factory.create_data_source()
        with mock.patch.object(settings, "FEATURE_AI", True), mock.patch.object(harvest_catalog, "delay") as delay:
            harvest_catalogs()

        self.assertTrue(delay.called)

    def test_a_paused_source_is_left_alone(self):
        # Both, so that a version of harvest_catalogs which queued nothing at
        # all could not pass this by doing nothing.
        paused = self.factory.create_data_source(name="paused")
        active = self.factory.create_data_source(name="active")
        paused.pause("maintenance")
        with mock.patch.object(settings, "FEATURE_AI", True), mock.patch.object(harvest_catalog, "delay") as delay:
            harvest_catalogs()

        queued = [call.args[0] for call in delay.call_args_list]
        self.assertIn(active.id, queued)
        self.assertNotIn(paused.id, queued)

    def test_one_source_failing_does_not_take_the_worker_down(self):
        # A harvest that raises must not poison the queue for the others.
        source = self.factory.create_data_source()
        with mock.patch("sqldesk.tasks.catalog.harvest_data_source", side_effect=RuntimeError("boom")):
            harvest_catalog(source.id)

    def test_a_source_deleted_since_the_job_was_queued_is_skipped(self):
        with mock.patch("sqldesk.tasks.catalog.harvest_data_source") as harvest:
            harvest_catalog(123456789)

        self.assertFalse(harvest.called)
