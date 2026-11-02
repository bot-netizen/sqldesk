"""
The demo's data: one DuckDB file, built from nothing.

Generated rather than shipped as a fixture. A .csv in the repository would be
a file nobody reads, that goes stale against the queries written over it, and
that has to be kept in sync by hand. This is forty lines of SQL that says what
the shape is, and the shape is the point -- every visualization in the catalog
needs rows of a particular form, and these tables are chosen to supply them
between them rather than one table per chart.

Deterministic, so the dashboard looks the same on every install and a
screenshot taken today matches one taken next week. `setseed` fixes DuckDB's
generator; the dates are relative to the day it is seeded, because a demo
whose "last 90 days" ended in 2026 is a demo of nothing.

**A column picked at random is indexed into a list, not drawn with a
subquery.** `(SELECT x FROM t ORDER BY random() LIMIT 1)` is uncorrelated:
it does not mention the outer row, so it is evaluated *once* for the whole
statement and every row gets the same answer. It looks right, it runs, and
it produces four thousand orders that are all the same category -- charts
with one bar on them. Indexing a list literal puts the `random()` in the
outer row's own expression, where it is drawn per row.
"""

#: Three months. Long enough for a calendar heatmap to have shape and for a
#: cohort table to have something to decay, short enough to build in a second.
DAYS = 90

#: Countries carry ISO-3 codes because that is what the choropleth joins on,
#: and lat/long because the map needs points. Both from one table, so the two
#: maps are demonstrably the same data drawn two ways.
PLACES = [
    ("CAN", "Canada", "Toronto", 43.65, -79.38),
    ("USA", "United States", "New York", 40.71, -74.01),
    ("GBR", "United Kingdom", "London", 51.51, -0.13),
    ("DEU", "Germany", "Berlin", 52.52, 13.40),
    ("FRA", "France", "Paris", 48.86, 2.35),
    ("IND", "India", "Bengaluru", 12.97, 77.59),
    ("AUS", "Australia", "Sydney", -33.87, 151.21),
    ("BRA", "Brazil", "São Paulo", -23.55, -46.63),
    ("JPN", "Japan", "Tokyo", 35.68, 139.69),
    ("ZAF", "South Africa", "Cape Town", -33.92, 18.42),
]

CHANNELS = ["Organic", "Paid search", "Referral", "Email", "Partner"]
CATEGORIES = ["Filters", "Pumps", "Valves", "Sensors", "Fittings", "Gaskets"]
SERVICES = ["api", "worker", "scheduler", "ingest", "search", "billing"]

#: The funnel's steps, with the share of the previous step that reaches each.
#: Written out rather than computed so the drop-off is a decision somebody can
#: read and argue with.
FUNNEL = [
    ("Visited", 1.00),
    ("Signed up", 0.42),
    ("Connected a source", 0.26),
    ("Ran a query", 0.19),
    ("Shared a dashboard", 0.08),
]


def _values(rows):
    """A VALUES list, quoted. Only ever called on the constants above."""
    out = []
    for row in rows:
        cells = []
        for cell in row:
            if isinstance(cell, str):
                cells.append("'{}'".format(cell.replace("'", "''")))
            else:
                cells.append(repr(cell))
        out.append("({})".format(", ".join(cells)))
    return ",\n    ".join(out)


def statements():
    """
    Every statement that builds the demo, in order.

    Returned rather than executed so the caller owns the connection, and so a
    test can read them without a database.
    """
    places = _values(PLACES)
    channels = _values([(one,) for one in CHANNELS])
    categories = _values([(one,) for one in CATEGORIES])
    services = _values([(one,) for one in SERVICES])
    funnel = _values([(name, share, nth) for nth, (name, share) in enumerate(FUNNEL)])

    return [
        "SELECT setseed(0.42)",
        "CREATE OR REPLACE TABLE places (country_code VARCHAR, country VARCHAR, city VARCHAR, "
        "latitude DOUBLE, longitude DOUBLE)",
        "INSERT INTO places VALUES\n    {}".format(places),
        "CREATE OR REPLACE TABLE channels (channel VARCHAR)",
        "INSERT INTO channels VALUES\n    {}".format(channels),
        "CREATE OR REPLACE TABLE categories (category VARCHAR)",
        "INSERT INTO categories VALUES\n    {}".format(categories),
        "CREATE OR REPLACE TABLE services (service VARCHAR)",
        "INSERT INTO services VALUES\n    {}".format(services),
        "CREATE OR REPLACE TABLE funnel_steps (step VARCHAR, reaching DOUBLE, position INTEGER)",
        "INSERT INTO funnel_steps VALUES\n    {}".format(funnel),
        # Customers first: orders point at them, and the cohort table is built
        # from when they signed up against when they ordered.
        """
        CREATE OR REPLACE TABLE customers AS
        SELECT
            n AS customer_id,
            'Customer ' || lpad(n::VARCHAR, 4, '0') AS name,
            (SELECT list(country_code) FROM places)[1 + CAST(floor(random() * 10) AS INTEGER)] AS country_code,
            (current_date - CAST(floor(random() * {days}) AS INTEGER)) AS signed_up_on
        FROM range(1, 601) t(n)
        """.format(
            days=DAYS
        ),
        # One row per order. Everything with a time axis comes off this.
        """
        CREATE OR REPLACE TABLE orders AS
        SELECT
            n AS order_id,
            1 + CAST(floor(random() * 600) AS INTEGER) AS customer_id,
            (SELECT list(channel) FROM channels)[1 + CAST(floor(random() * 5) AS INTEGER)] AS channel,
            (SELECT list(category) FROM categories)[1 + CAST(floor(random() * 6) AS INTEGER)] AS category,
            CAST(current_date - CAST(floor(random() * {days}) AS INTEGER) AS TIMESTAMP)
                + INTERVAL (CAST(floor(random() * 24) AS INTEGER)) HOUR AS ordered_at,
            1 + CAST(floor(random() * 9) AS INTEGER) AS units,
            round((12 + random() * 480)::NUMERIC, 2) AS total
        FROM range(1, 4001) t(n)
        """.format(
            days=DAYS
        ),
        # A day per service, with a status word the status grid and the state
        # timeline both colour by -- mostly fine, occasionally not.
        """
        CREATE OR REPLACE TABLE service_days AS
        SELECT
            s.service,
            (current_date - CAST(d.n AS INTEGER)) AS day,
            CASE
                WHEN random() < 0.04 THEN 'down'
                WHEN random() < 0.16 THEN 'degraded'
                ELSE 'ok'
            END AS status,
            round((88 + random() * 12)::NUMERIC, 2) AS uptime
        FROM services s CROSS JOIN range(0, 30) d(n)
        """,
    ]
