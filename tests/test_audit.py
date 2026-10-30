"""
The audit: where the month went, read from the rows that were always there.

Every execution has been written to `events` since the fork and nothing read
it as a history. What makes this worth testing rather than obvious is the
shape of the answer: "expensive" has three different answers and only one of
them is a person, so a page that only ranked people would send somebody
looking in the wrong place.
"""

from datetime import datetime, timedelta, timezone

from sqldesk import models
from sqldesk.models import db
from sqldesk.monitor import get_audit
from tests import BaseTestCase


def ran(org, user, data_source=None, query=None, when=None, cached=False):
    """One execution, as the query path records it."""
    event = models.Event(
        org=org,
        user=user,
        action="execute_query",
        object_type="data_source",
        object_id=str(data_source.id) if data_source else None,
        additional_properties={
            "cache": "hit" if cached else "miss",
            "query_id": query.id if query else None,
        },
        created_at=when or datetime.now(timezone.utc),
    )
    db.session.add(event)
    return event


class AuditTestCase(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.org = self.factory.org
        self.source = self.factory.data_source


class TestWhatItCounts(AuditTestCase):
    def test_an_empty_month_is_zero_rather_than_an_error(self):
        audit = get_audit(self.org.id)

        self.assertEqual(0, audit["executions"])
        self.assertEqual([], audit["top_users"])
        # Not 0: a ratio of no executions is not a cache missing everything.
        self.assertIsNone(audit["cache_hit_ratio"])

    def test_it_counts_the_executions_in_the_window(self):
        for _ in range(3):
            ran(self.org, self.factory.user, self.source)
        db.session.commit()

        self.assertEqual(3, get_audit(self.org.id)["executions"])

    def test_it_leaves_out_what_happened_before_the_window(self):
        ran(self.org, self.factory.user, self.source, when=datetime.now(timezone.utc) - timedelta(days=45))
        ran(self.org, self.factory.user, self.source)
        db.session.commit()

        self.assertEqual(1, get_audit(self.org.id, days=30)["executions"])
        self.assertEqual(2, get_audit(self.org.id, days=90)["executions"])

    def test_it_leaves_out_another_organisation(self):
        other = self.factory.create_org()
        ran(other, self.factory.create_user(org=other), None)
        ran(self.org, self.factory.user, self.source)
        db.session.commit()

        self.assertEqual(1, get_audit(self.org.id)["executions"])

    def test_it_counts_only_executions_and_not_every_event(self):
        """
        `events` records views, edits and archives too. An audit of "how busy
        was this" that counted somebody opening a page would be meaningless.
        """
        ran(self.org, self.factory.user, self.source)
        db.session.add(
            models.Event(org=self.org, user=self.factory.user, action="view", object_type="query", object_id="1")
        )
        db.session.commit()

        self.assertEqual(1, get_audit(self.org.id)["executions"])

    def test_the_cache_ratio_is_of_the_executions_counted(self):
        ran(self.org, self.factory.user, self.source, cached=True)
        ran(self.org, self.factory.user, self.source, cached=True)
        ran(self.org, self.factory.user, self.source, cached=False)
        db.session.commit()

        audit = get_audit(self.org.id)

        self.assertEqual(2, audit["from_cache"])
        self.assertAlmostEqual(2 / 3, audit["cache_hit_ratio"])


class TestTheThreeAnswers(AuditTestCase):
    """
    "Expensive" has three answers and only one of them is a person.
    """

    def test_by_person(self):
        busy = self.factory.create_user(name="Busy")
        quiet = self.factory.create_user(name="Quiet")
        for _ in range(3):
            ran(self.org, busy, self.source)
        ran(self.org, quiet, self.source)
        db.session.commit()

        top = get_audit(self.org.id)["top_users"]

        self.assertEqual(["Busy", "Quiet"], [one["name"] for one in top])
        self.assertEqual([3, 1], [one["executions"] for one in top])

    def test_by_data_source_because_that_is_where_the_money_went(self):
        warehouse = self.factory.create_data_source(name="Warehouse")
        for _ in range(4):
            ran(self.org, self.factory.user, warehouse)
        ran(self.org, self.factory.user, self.source)
        db.session.commit()

        top = get_audit(self.org.id)["top_data_sources"]

        self.assertEqual("Warehouse", top[0]["name"])
        self.assertEqual(4, top[0]["executions"])

    def test_by_query_so_a_refreshing_dashboard_is_visible_as_itself(self):
        expensive = self.factory.create_query(name="Hourly rollup")
        for _ in range(5):
            ran(self.org, self.factory.user, self.source, query=expensive)
        db.session.commit()

        top = get_audit(self.org.id)["top_queries"]

        self.assertEqual("Hourly rollup", top[0]["name"])
        self.assertEqual(5, top[0]["executions"])

    def test_a_run_with_no_saved_query_is_named_ad_hoc_and_not_deleted(self):
        """
        Three cases, and the first version collapsed two of them. The query
        path records the string "adhoc" for a run from the editor; `int()`
        cannot read it, so it became None, and None is in no lookup -- five
        ad-hoc runs were reported on the page as a deleted query.
        """
        event = ran(self.org, self.factory.user, self.source)
        event.additional_properties = {"cache": "miss", "query_id": "adhoc"}
        db.session.commit()

        top = get_audit(self.org.id)["top_queries"]

        self.assertEqual([{"id": None, "name": "ad-hoc", "executions": 1}], top)

    def test_a_deleted_thing_is_named_as_deleted_rather_than_dropped(self):
        """
        Dropping the row would quietly reduce the month's total as seen in the
        breakdown, and somebody comparing it against the headline would find
        the two disagreeing with no explanation.
        """
        source = self.factory.create_data_source(name="Gone")
        for _ in range(2):
            ran(self.org, self.factory.user, source)
        db.session.commit()
        source_id = source.id
        db.session.delete(source)
        db.session.commit()

        top = get_audit(self.org.id)["top_data_sources"]

        self.assertEqual([{"id": source_id, "name": "deleted", "executions": 2}], top)


class TestTheShapeOfTheAnswer(AuditTestCase):
    def test_a_day_with_nothing_is_absent_rather_than_zero(self):
        """
        The series is what was recorded, not a calendar. The page draws bars
        from it and a gap is a gap.
        """
        ran(self.org, self.factory.user, self.source, when=datetime.now(timezone.utc) - timedelta(days=2))
        ran(self.org, self.factory.user, self.source)
        db.session.commit()

        per_day = get_audit(self.org.id)["per_day"]

        self.assertEqual(2, len(per_day))
        self.assertLess(per_day[0][0], per_day[1][0], "the days are not in order")

    def test_the_window_is_reported_with_the_answer(self):
        self.assertEqual(7, get_audit(self.org.id, days=7)["window_days"])

    def test_the_lists_are_capped(self):
        for n in range(12):
            ran(self.org, self.factory.create_user(name="Person {}".format(n)), self.source)
        db.session.commit()

        self.assertEqual(10, len(get_audit(self.org.id, limit=10)["top_users"]))


class TestWhoMayRead(AuditTestCase):
    def ask(self, user, query=""):
        # `org=False`: the admin routes are not org-scoped, so a slug prefix
        # misses them and falls through to the SPA shell -- a 200 of HTML that
        # looks like success and is not. The same trap is noted in
        # tests/handlers/test_admin.py, and it caught this file too.
        return self.make_request("get", "/api/admin/audit" + query, user=user, org=False)

    def test_an_administrator_may(self):
        admin = self.factory.create_admin()
        db.session.commit()

        answer = self.ask(admin)

        self.assertEqual(200, answer.status_code)
        self.assertIn("top_users", answer.json)

    def test_an_ordinary_user_may_not(self):
        self.assertEqual(403, self.ask(self.factory.user).status_code)

    def test_the_window_is_capped_rather_than_whatever_was_typed(self):
        """
        `events` gets a row per execution and is never trimmed, so an
        unbounded window is a table scan somebody asked for by editing a URL.
        """
        admin = self.factory.create_admin()
        db.session.commit()

        self.assertEqual(365, self.ask(admin, "?days=100000").json["window_days"])

    def test_a_nonsense_window_does_not_become_zero_days(self):
        admin = self.factory.create_admin()
        db.session.commit()

        self.assertEqual(1, self.ask(admin, "?days=-5").json["window_days"])


class TestNotebookCells(AuditTestCase):
    """
    A notebook SQL cell is somebody asking a warehouse a question, so the
    audit counts it as one.

    Notebooks and the audit are both new, and were built without reference to
    each other -- so an install whose people worked in notebooks saw an empty
    audit while the page promised "where the month went". Found by running a
    notebook on the deployed cluster and looking at the audit afterwards.
    """

    def a_cell_run(self, when=None, user=None):
        event = ran(self.org, user or self.factory.user, self.source, when=when)
        event.additional_properties = {"cache": "miss", "query_id": "notebook", "notebook_id": 1, "cell": "orders"}
        return event

    def test_it_is_counted_in_the_month(self):
        self.a_cell_run()
        db.session.commit()

        self.assertEqual(1, get_audit(self.org.id)["executions"])

    def test_it_is_named_rather_than_counted_as_the_editor(self):
        """
        A month spent in notebooks and a month spent in the editor are
        different months. Collapsing them into "ad-hoc" is the same mistake as
        reporting an ad-hoc run as a deleted query, one level along.
        """
        self.a_cell_run()
        db.session.commit()

        top = get_audit(self.org.id)["top_queries"]

        self.assertEqual([{"id": None, "name": "notebook cell", "executions": 1}], top)

    def test_the_editor_and_a_notebook_are_two_rows_not_one(self):
        editor = ran(self.org, self.factory.user, self.source)
        editor.additional_properties = {"cache": "miss", "query_id": "adhoc"}
        self.a_cell_run()
        db.session.commit()

        top = get_audit(self.org.id)["top_queries"]
        named = {one["name"]: one["executions"] for one in top}

        self.assertEqual({"ad-hoc": 1, "notebook cell": 1}, named)

    def test_it_counts_towards_the_person_who_ran_it(self):
        self.a_cell_run()
        db.session.commit()

        top = get_audit(self.org.id)["top_users"]

        self.assertEqual(1, top[0]["executions"])

    def test_it_counts_towards_its_data_source(self):
        self.a_cell_run()
        db.session.commit()

        top = get_audit(self.org.id)["top_data_sources"]

        self.assertEqual(self.source.name, top[0]["name"])
