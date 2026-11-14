import logging

from sqldesk.query_runner import (
    TYPE_BOOLEAN,
    TYPE_DATE,
    TYPE_DATETIME,
    TYPE_FLOAT,
    TYPE_INTEGER,
    TYPE_STRING,
    BaseSQLQueryRunner,
    InterruptException,
    JobTimeoutException,
    fetch_within_budget,
    mark_truncated,
    register,
)

logger = logging.getLogger(__name__)

types_map = {
    5: TYPE_BOOLEAN,
    6: TYPE_INTEGER,
    7: TYPE_FLOAT,
    8: TYPE_STRING,
    9: TYPE_STRING,
    10: TYPE_DATE,
    11: TYPE_DATETIME,
    12: TYPE_DATETIME,
    13: TYPE_DATETIME,
    # 14 INTERVAL and 114 INTERVALYM are durations, not points in time. Typed as
    # datetimes they rendered as dates somewhere near 1970.
    14: TYPE_STRING,
    15: TYPE_DATETIME,
    16: TYPE_FLOAT,
    17: TYPE_STRING,
    114: TYPE_STRING,
    115: TYPE_STRING,
    116: TYPE_STRING,
    117: TYPE_STRING,
}


class Vertica(BaseSQLQueryRunner):
    noop_query = "SELECT 1"

    @classmethod
    def configuration_schema(cls):
        return {
            "type": "object",
            "properties": {
                "host": {"type": "string"},
                "user": {"type": "string"},
                "password": {"type": "string", "title": "Password"},
                "database": {"type": "string", "title": "Database name"},
                "port": {"type": "number"},
                "tlsmode": {
                    "type": "string",
                    "title": "TLS Mode",
                    "default": "prefer",
                    "extendedEnum": [
                        {"value": "disable", "name": "Disable"},
                        {"value": "prefer", "name": "Prefer"},
                        {"value": "require", "name": "Require"},
                        {"value": "verify-ca", "name": "Verify CA"},
                        {"value": "verify-full", "name": "Verify Full"},
                    ],
                },
                "connection_timeout": {"type": "number", "title": "Connection Timeout"},
                "binary_transfer": {
                    "type": "boolean",
                    "title": "Binary result transfer (faster; turn off only for a server that refuses it)",
                    "default": True,
                },
            },
            "required": ["database"],
            "order": [
                "host",
                "port",
                "user",
                "password",
                "database",
                "tlsmode",
                "connection_timeout",
                "binary_transfer",
            ],
            "secret": ["password"],
            "extra_options": ["tlsmode", "connection_timeout", "binary_transfer"],
        }

    @classmethod
    def enabled(cls):
        try:
            import vertica_python  # noqa: F401
        except ImportError:
            return False

        return True

    def _get_tables(self, schema):
        query = """
        Select table_schema, table_name, column_name from columns where is_system_table=false
        union all
        select table_schema, table_name, column_name from view_columns;
        """

        results, error = self.run_query(query, None)

        if error is not None:
            self._handle_run_query_error(error)

        for row in results["rows"]:
            table_name = "{}.{}".format(row["table_schema"], row["table_name"])

            if table_name not in schema:
                schema[table_name] = {"name": table_name, "columns": []}

            schema[table_name]["columns"].append(row["column_name"])

        return list(schema.values())

    def run_query(self, query, user):
        import vertica_python

        if query == "":
            data = None
            error = "Query is empty"
            return data, error

        connection = None
        try:
            conn_info = {
                "host": self.configuration.get("host", ""),
                "port": self.configuration.get("port", 5433),
                "user": self.configuration.get("user", ""),
                "password": self.configuration.get("password", ""),
                "database": self.configuration.get("database", ""),
                # `read_timeout` used to be here. vertica-python dropped the option, and
                # an argument the driver ignores is worse than no argument at all: the
                # form promises a limit that nothing enforces.
                "tlsmode": self.configuration.get("tlsmode", "prefer"),
            }

            if self.configuration.get("connection_timeout"):
                conn_info["connection_timeout"] = self.configuration.get("connection_timeout")
            # Values sent in Vertica's binary format rather than as text to be
            # parsed: a million rows came back in 6.9s rather than 10.7s, the
            # same values either way. On unless a data source turns it off --
            # saved data sources have no such key, and get it too.
            if self.configuration.get("binary_transfer", True):
                conn_info["binary_transfer"] = True

            connection = vertica_python.connect(**conn_info)
            cursor = connection.cursor()
            logger.debug("Vertica running query: %s", query)
            cursor.execute(query)

            if cursor.description is not None:
                columns_data = [(i[0], types_map.get(i[1], None)) for i in cursor.description]

                columns = self.fetch_columns(columns_data)
                names = [c["name"] for c in columns]
                rows, truncated = fetch_within_budget(cursor.fetchmany, lambda r: dict(zip(names, r)))
                if truncated:
                    _cancel(connection)

                data = {"columns": columns, "rows": rows}
                if truncated:
                    mark_truncated(data)
                error = None
            else:
                data = None
                error = "No data was returned."

            cursor.close()
        except (KeyboardInterrupt, InterruptException, JobTimeoutException):
            # Cancel and the time limit stopped the worker and nothing else:
            # closing a Vertica connection does not stop the statement it was
            # running, so a cancelled query went on using the cluster.
            if connection:
                _cancel(connection)
            raise
        finally:
            if connection:
                try:
                    connection.close()
                except Exception:
                    logger.warning("Vertica connection did not close cleanly", exc_info=True)

        return data, error


def _cancel(connection):
    """Stop the statement this connection is running, on the server."""
    try:
        connection.cancel()
    except Exception:
        logger.warning("Could not cancel a Vertica statement", exc_info=True)


register(Vertica)
