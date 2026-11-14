"""Cancel and the time limit stop the Hive operation, and rows come back in large batches."""
from unittest import TestCase
from unittest.mock import MagicMock, patch

from sqldesk.query_runner import FETCH_BATCH, InterruptException
from sqldesk.query_runner.hive_ds import Hive


class TestHive(TestCase):
    def run_with(self, cursor):
        connection = MagicMock()
        connection.cursor.return_value = cursor
        with patch.object(Hive, "_get_connection", return_value=connection):
            return Hive({"host": "h"}).run_query("select 1", None)

    def test_cancel_stops_the_operation_on_hiveserver2(self):
        cursor = MagicMock()
        cursor.execute.side_effect = InterruptException()
        with self.assertRaises(InterruptException):
            self.run_with(cursor)
        cursor.cancel.assert_called()

    def test_rows_come_in_large_batches(self):
        cursor = MagicMock()
        cursor.description = [("n", "INT_TYPE")]
        cursor.fetchmany.side_effect = [[(1,)], []]
        data, error = self.run_with(cursor)
        self.assertEqual(cursor.arraysize, FETCH_BATCH)
        self.assertEqual(data["rows"], [{"n": 1}])
