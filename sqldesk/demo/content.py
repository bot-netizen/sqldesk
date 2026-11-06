"""
What the demo contains: a query per shape, and a visualization of every type.

**Every registered type appears exactly once**, and a test holds that to the
viz-lib catalog -- so a visualization added without a demo fails the suite
rather than quietly going undemonstrated. That is the whole point of this
file: "do the visualizations work" is a question nobody can answer by reading
code, and the answer rots silently.

Options are deliberately thin. Every visualization's `getOptions` fills its
column choices from the result it is given, so what is written here is only
what the demo means to *say* -- which columns matter, how to format them --
and the rest is the same defaulting a person would get by adding the chart by
hand. Writing out full option blobs would be writing down viz-lib's defaults
in a second place, where they would drift.
"""

#: `(name, description, sql)`. Shared by several visualizations where the
#: shape suits, because that is also how a real dashboard is built -- one
#: query, several readings.
QUERIES = [
    (
        "Revenue by day",
        "Every order, rolled up to the day it was placed.",
        """select ordered_at::date as day,
       sum(total) as revenue,
       count(*) as orders,
       sum(units) as units
from orders
group by 1
order by 1""",
    ),
    (
        "Every region, measured four ways",
        "Four measures per region, for finding the one that behaves unlike the rest.",
        """select p.country as region,
       sum(o.total) as revenue,
       count(*) as orders,
       sum(o.units) as units,
       round(avg(o.total), 2) as avg_order
from orders o
join customers c on c.customer_id = o.customer_id
join places p on p.country_code = c.country_code
group by 1
order by 2 desc""",
    ),
    (
        "Who sells to whom",
        "Region to region trade, as a plain relationship rather than a flow.",
        """select p.country as region,
       o.channel as partner,
       sum(o.total) as revenue
from orders o
join customers c on c.customer_id = o.customer_id
join places p on p.country_code = c.country_code
group by 1, 2
order by 3 desc""",
    ),
    (
        "Order sizes, day by day",
        "The spread of a day's orders, not just its total: what a candlestick needs.",
        """select ordered_at::date as day,
       arg_min(total, ordered_at) as open,
       arg_max(total, ordered_at) as close,
       min(total) as low,
       max(total) as high
from orders
group by 1
order by 1""",
    ),
    (
        "Revenue by day and channel",
        "The mix over time rather than the total: what the streamgraph is for.",
        """select ordered_at::date as day,
       channel,
       sum(total) as revenue
from orders
group by 1, 2
order by 1, 2""",
    ),
    (
        "Revenue by region and channel",
        "The same money, cut two ways. Feeds the pivot and the heatmap.",
        """select p.country as region,
       o.channel,
       sum(o.total) as revenue,
       count(*) as orders
from orders o
join customers c on c.customer_id = o.customer_id
join places p on p.country_code = c.country_code
group by 1, 2
order by 3 desc""",
    ),
    (
        "Revenue by category",
        "One number per category: the shape treemaps and word clouds want.",
        """select category, sum(total) as revenue, count(*) as orders
from orders group by 1 order by 2 desc""",
    ),
    (
        "This quarter at a glance",
        "A single row. Counters and gauges read one number off it.",
        """select sum(total) as revenue,
       count(*) as orders,
       count(distinct customer_id) as customers,
       round(avg(total), 2) as average_order,
       round(100.0 * count(*) / 4000, 1) as share_of_target
from orders""",
    ),
    (
        "Recent orders",
        "Rows as rows. The table, and the details card for one of them.",
        """select o.order_id, o.ordered_at, c.name as customer,
       o.channel, o.category, o.units, o.total
from orders o join customers c on c.customer_id = o.customer_id
order by o.ordered_at desc
limit 200""",
    ),
    (
        "Order totals",
        "One row per order, for distributions.",
        """select p.country as region, o.category, o.total
from orders o
join customers c on c.customer_id = o.customer_id
join places p on p.country_code = c.country_code""",
    ),
    (
        "Signup funnel",
        "Steps and the share of people reaching each.",
        """select step, round(reaching * 10000) as people
from funnel_steps order by position""",
    ),
    (
        "Cohort retention",
        "Signup week against ordering week: the shape a cohort table needs.",
        """with cohorts as (
    select customer_id, date_trunc('week', signed_up_on)::date as cohort_date
    from customers
),
sizes as (
    select cohort_date, count(*) as total from cohorts group by 1
)
select ch.cohort_date,
       date_diff('week', ch.cohort_date, o.ordered_at::date) as week_number,
       count(distinct o.customer_id) as value,
       s.total
from cohorts ch
join orders o on o.customer_id = ch.customer_id
join sizes s on s.cohort_date = ch.cohort_date
where o.ordered_at::date >= ch.cohort_date
group by 1, 2, 4
order by 1, 2""",
    ),
    (
        "Channel to category to region",
        "Three hops, for the flow diagrams.",
        """select o.channel as stage1, o.category as stage2, p.country as stage3,
       count(*) as value
from orders o
join customers c on c.customer_id = o.customer_id
join places p on p.country_code = c.country_code
group by 1, 2, 3
having count(*) > 4""",
    ),
    (
        "Revenue bridge",
        "Opening, the moves, and where it lands.",
        """select 'Opening' as step, 180000 as change, true as is_total
union all select 'Organic', 42000, false
union all select 'Paid search', 28000, false
union all select 'Churn', -31000, false
union all select 'Refunds', -8000, false
union all select 'Closing', 211000, true""",
    ),
    (
        "Revenue by country",
        "ISO-3 codes, which is what a choropleth joins on.",
        """select p.country_code, p.country, sum(o.total) as revenue
from orders o
join customers c on c.customer_id = o.customer_id
join places p on p.country_code = c.country_code
group by 1, 2 order by 3 desc""",
    ),
    (
        "Cities",
        "Points on a map: latitude, longitude and something to size by.",
        """select p.city, p.country, p.latitude, p.longitude, sum(o.total) as revenue
from orders o
join customers c on c.customer_id = o.customer_id
join places p on p.country_code = c.country_code
group by 1, 2, 3, 4 order by 5 desc""",
    ),
    (
        "Service health today",
        "One row per service, with a status word to colour by.",
        """select service, status, uptime
from service_days where day = current_date - 1 order by service""",
    ),
    (
        "Service health over a month",
        "The same services, a row per day, for a timeline.",
        """select service, day, status from service_days order by service, day""",
    ),
    (
        "Region scorecard",
        "Several measures per region, for a radar.",
        """select p.country as region,
       round(sum(o.total) / 1000, 1) as revenue_k,
       count(*) as orders,
       round(avg(o.total), 1) as average_order,
       count(distinct o.customer_id) as customers
from orders o
join customers c on c.customer_id = o.customer_id
join places p on p.country_code = c.country_code
group by 1 order by 2 desc limit 8""",
    ),
]


#: `(query name, visualization type, visualization name, options)`.
#:
#: The CHART entries are several readings of one query on purpose: that is
#: what a dashboard widget's tabs are for, and the demo should show it.
VISUALIZATIONS = [
    (
        "Revenue by day",
        "CHART",
        "Revenue, daily",
        {"globalSeriesType": "line", "columnMapping": {"day": "x", "revenue": "y"}},
    ),
    (
        "Revenue by day",
        "CHART",
        "Orders, daily",
        {"globalSeriesType": "column", "columnMapping": {"day": "x", "orders": "y"}},
    ),
    (
        "Revenue by day",
        "CHART",
        "Units, daily",
        {"globalSeriesType": "area", "columnMapping": {"day": "x", "units": "y"}},
    ),
    (
        "Revenue by category",
        "CHART",
        "Share by category",
        {"globalSeriesType": "pie", "columnMapping": {"category": "x", "revenue": "y"}},
    ),
    ("Revenue by day", "CALENDAR_HEATMAP", "Orders per day", {"dateColumn": "day", "valueColumn": "orders"}),
    ("Revenue by region and channel", "PIVOT", "Region against channel", {}),
    ("Revenue by category", "TREEMAP", "Where the money is", {}),
    (
        "Revenue by category",
        "WORD_CLOUD",
        "Categories by weight",
        {"column": "category", "frequenciesColumn": "revenue"},
    ),
    (
        "This quarter at a glance",
        "COUNTER",
        "Revenue this quarter",
        {"counterColName": "revenue", "stringDecimal": 0, "stringDecChar": ".", "stringThouSep": ","},
    ),
    ("This quarter at a glance", "GAUGE", "Against target", {"valueColumn": "share_of_target", "min": 0, "max": 120}),
    ("This quarter at a glance", "PROGRESS", "Target attainment", {"valueColumn": "share_of_target", "target": 100}),
    ("Recent orders", "TABLE", "Recent orders", {}),
    (
        "Recent orders",
        "CHART",
        "Those orders, plotted",
        {"globalSeriesType": "scatter", "columnMapping": {"ordered_at": "x", "total": "y"}},
    ),
    ("Recent orders", "DETAILS", "One order, in full", {}),
    ("Order totals", "BOXPLOT", "Order totals by region", {}),
    ("Order totals", "HISTOGRAM", "How big is an order?", {"valueColumn": "total", "binCount": 30}),
    ("Signup funnel", "FUNNEL", "Signup funnel", {"stepCol": {"colName": "step"}, "valueCol": {"colName": "people"}}),
    ("Cohort retention", "COHORT", "Retention by signup week", {"timeInterval": "weekly"}),
    ("Channel to category to region", "SANKEY", "Channel to category to region", {}),
    (
        "Every region, measured four ways",
        "PARALLEL",
        "Which region is unlike the others",
        {
            "dimensionColumns": ["revenue", "orders", "units", "avg_order"],
            "seriesColumn": "region",
        },
    ),
    (
        "Who sells to whom",
        "NETWORK",
        "Regions and channels, connected",
        {"sourceColumn": "region", "targetColumn": "partner", "valueColumn": "revenue"},
    ),
    (
        "Order sizes, day by day",
        "CANDLESTICK",
        "How order sizes moved",
        {
            "xColumn": "day",
            "openColumn": "open",
            "closeColumn": "close",
            "lowColumn": "low",
            "highColumn": "high",
        },
    ),
    (
        "Revenue by day and channel",
        "STREAMGRAPH",
        "How the channel mix moves",
        {"xColumn": "day", "seriesColumn": "channel", "valueColumn": "revenue"},
    ),
    ("Channel to category to region", "SUNBURST_SEQUENCE", "The same flow, as rings", {}),
    (
        "Revenue bridge",
        "WATERFALL",
        "Revenue bridge",
        {"labelColumn": "step", "valueColumn": "change", "totalColumn": "is_total"},
    ),
    (
        "Revenue by country",
        "CHOROPLETH",
        "Revenue by country",
        # `keyColumn` and `targetField`, not `countryCodeColumn`: that
        # spelling is not one the choropleth reads, so it joined nothing,
        # had no bounds to fit, and took the page down with "Invalid LatLng
        # object: (NaN, NaN)".
        {"mapType": "countries", "keyColumn": "country_code", "targetField": "iso_a3", "valueColumn": "revenue"},
    ),
    (
        "Cities",
        "MAP",
        "Where the customers are",
        {"latColName": "latitude", "lonColName": "longitude", "classify": "country"},
    ),
    (
        "Service health today",
        "STATUS_GRID",
        "Services right now",
        {"nameColumn": "service", "statusColumn": "status", "valueColumn": "uptime"},
    ),
    (
        "Service health over a month",
        "STATE_TIMELINE",
        "A month of service health",
        {"laneColumn": "service", "startColumn": "day", "stateColumn": "status"},
    ),
    (
        "Region scorecard",
        "RADAR",
        "Regions compared",
        {"labelColumn": "region", "valueColumns": ["revenue_k", "orders", "average_order", "customers"]},
    ),
]


#: How tall each kind of visualization wants to be, in grid rows.
#:
#: Taken from what each one registers for itself in viz-lib -- a counter is
#: six rows and a table is twenty-eight, and a demo that gave them both the
#: same height would be a demo of a squashed table. Kept here rather than
#: read across because Python cannot see a TypeScript registration; the
#: numbers are checked against viz-lib by a test.
HEIGHTS = {
    "BOXPLOT": 16,
    "CALENDAR_HEATMAP": 12,
    "CANDLESTICK": 16,
    "CHART": 16,
    "CHOROPLETH": 16,
    "COHORT": 16,
    "COUNTER": 6,
    "DETAILS": 4,
    "FUNNEL": 20,
    "GAUGE": 12,
    "HISTOGRAM": 16,
    "MAP": 16,
    "NETWORK": 18,
    "PARALLEL": 16,
    "PIVOT": 20,
    "PROGRESS": 12,
    "RADAR": 16,
    "SANKEY": 14,
    "STATE_TIMELINE": 12,
    "STREAMGRAPH": 16,
    "STATUS_GRID": 10,
    "SUNBURST_SEQUENCE": 14,
    "TABLE": 28,
    "TREEMAP": 16,
    "WATERFALL": 16,
    "WORD_CLOUD": 16,
}

#: The dashboard, as `(visualization name, width)` in reading order. Width is
#: in half-widths: 1 is half the board, 2 is the full width.
#:
#: The board is **24 columns** (`client/app/config/dashboard-grid-options.js`),
#: so a half is 12 and a full is 24. Getting that wrong is not subtle: the
#: first version of this used 3 and 6, and every widget came out an eighth of
#: the page wide with its chart squashed into the corner.
DASHBOARD = "Demo: everything, drawn"
DASHBOARD_WIDGETS = [
    ("Revenue this quarter", 1),
    ("Against target", 1),
    # Three readings of one query behind one widget -- the tabs feature, and
    # the reason a dashboard with it fetches that query once instead of
    # three times.
    ("Revenue, daily", 2, ["Orders, daily", "Units, daily"]),
    ("Share by category", 1),
    ("Where the money is", 1),
    ("Region against channel", 2),
    ("Orders per day", 2),
    ("Signup funnel", 1),
    ("Retention by signup week", 1),
    ("Channel to category to region", 1),
    ("The same flow, as rings", 1),
    ("Revenue bridge", 2),
    ("Revenue by country", 1),
    ("Where the customers are", 1),
    ("Services right now", 2),
    ("A month of service health", 2),
    ("Order totals by region", 1),
    ("How big is an order?", 1),
    ("Regions compared", 1),
    ("Target attainment", 1),
    ("Categories by weight", 1),
    ("One order, in full", 1),
    # A table with a chart beside it: the case tables-with-tabs exists for.
    # The chart is of the table's *own* query, which is the rule -- a tab of
    # some other query would have to fetch, and fetching once is the whole
    # point of a tab.
    ("Recent orders", 2, ["Those orders, plotted"]),
]


NOTEBOOK = "Demo: a notebook, end to end"
NOTEBOOK_DESCRIPTION = (
    "What a saved query cannot hold: two sources joined, reshaped in Python, charted, " "and read back as SQL."
)

#: `(name, title, kind, uses the data source, source)`.
NOTEBOOK_CELLS = [
    (
        "orders",
        "Pull the orders",
        "sql",
        True,
        """select p.country as region, o.channel, o.category,
       o.ordered_at::date as day, o.units, o.total
from orders o
join customers c on c.customer_id = o.customer_id
join places p on p.country_code = c.country_code""",
    ),
    (
        "by_region",
        "Reshape it in Python",
        "python",
        False,
        """import pandas as pd

# `orders` is the cell above, already a dataframe. Nothing was fetched twice.
by_region = (
    orders.groupby("region")
    .agg(revenue=("total", "sum"), orders=("total", "size"), units=("units", "sum"))
    .reset_index()
    .sort_values("revenue", ascending=False)
)
by_region["share"] = (100 * by_region.revenue / by_region.revenue.sum()).round(1)
print("regions:", len(by_region), "| revenue:", round(by_region.revenue.sum()))
by_region""",
    ),
    (
        "top_regions",
        "Read it back as SQL",
        "sql",
        False,
        """-- No data source on this cell: it reads the cells above.
select region, revenue, share
from by_region
where share > 5
order by revenue desc""",
    ),
    (
        "drawn",
        "Draw it",
        "python",
        False,
        """import plotly.express as px

px.bar(
    by_region,
    x="region",
    y="revenue",
    title="Revenue by region",
    labels={"revenue": "Revenue", "region": "Region"},
)""",
    ),
]
