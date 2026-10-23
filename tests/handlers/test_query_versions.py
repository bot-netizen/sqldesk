"""
A query's history: what it said before, and putting it back.

Two things are being tested here, and the first one is a repair. `changes` has
recorded queries being created and archived since long before this fork and has
never recorded one being **edited** -- the handler set a `changed_by` that
nothing read -- so the table looked well kept and held almost nothing. Half of
what follows is about that: an edit leaves a version, a save that changed
nothing does not.

The second is the reader, and its rule is that a restore is **a new version**.
Restoring version 2 writes version 7 that happens to say what 2 said; nothing
is rewritten and nothing is deleted. A history that could be edited by using it
would not be a history.
"""

from sqldesk import history, models
from sqldesk.models import db
from tests import BaseTestCase


class VersionTestCase(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.query = self.factory.create_query(name="Orders", query_text="select 1", description="first")
        db.session.commit()

    def save(self, user=None, **fields):
        return self.make_request("post", "/api/queries/{}".format(self.query.id), data=fields, user=user)

    def versions(self, user=None, query=None):
        rv = self.make_request("get", "/api/queries/{}/versions".format((query or self.query).id), user=user)
        return rv

    def restore(self, change_id, user=None):
        return self.make_request(
            "post",
            "/api/queries/{}/versions/{}/restore".format(self.query.id, change_id),
            user=user,
        )


class TestAnEditLeavesAVersion(VersionTestCase):
    def test_a_query_starts_with_the_one_it_was_created_with(self):
        self.assertEqual(["Created"], self.versions().json["versions"][0]["changed"])

    def test_editing_it_records_what_moved(self):
        # The repair: this recorded nothing at all until now.
        self.save(query="select 2")

        newest = self.versions().json["versions"][0]

        self.assertEqual(["SQL"], newest["changed"])
        self.assertEqual("select 2", newest["values"]["query"])

    def test_two_fields_in_one_save_are_both_recorded(self):
        # And this is why the mixin had to be fixed first: it re-read every
        # column on every assignment, so the second field set in one save
        # overwrote the first field's "previous" with its new value.
        self.save(name="Orders by day", query="select 2")

        self.assertEqual(["Name", "SQL"], self.versions().json["versions"][0]["changed"])

    def test_a_save_that_changed_nothing_leaves_no_version(self):
        # The editor sends the whole query whether or not anything in it moved,
        # and a version that says nothing happened is one somebody has to read
        # to find that out.
        before = len(self.versions().json["versions"])

        self.save(name="Orders")

        self.assertEqual(before, len(self.versions().json["versions"]))

    def test_the_newest_version_is_first_and_they_are_numbered_from_the_oldest(self):
        self.save(query="select 2")
        self.save(query="select 3")

        versions = self.versions().json["versions"]

        self.assertEqual([3, 2, 1], [version["number"] for version in versions])
        self.assertEqual("select 3", versions[0]["values"]["query"])

    def test_each_one_says_who_and_when(self):
        # An admin, because a plain user cannot edit somebody else's query --
        # and "who changed it" is only interesting when it is not the owner.
        other = self.factory.create_admin()
        rv = self.save(query="select 2", user=other)

        self.assertEqual(200, rv.status_code)
        newest = self.versions().json["versions"][0]

        self.assertEqual(other.email, newest["by"]["email"])
        self.assertIsNotNone(newest["at"])

    def test_a_version_never_carries_the_api_key(self):
        # It is a credential, and a change record is a copy of it that nothing
        # expires. The page would otherwise have to remember not to show it.
        self.save(query="select 2")

        for version in self.versions().json["versions"]:
            self.assertNotIn("api_key", version["values"])

    def test_the_list_is_capped(self):
        # A long-lived query has hundreds of versions and nobody reads past the
        # first screen. The cap is also what makes the extra row fetched for
        # the comparison worth doing rather than fetching everything.
        for index in range(history.LIMIT + 3):
            self.save(query="select {}".format(index + 10))

        versions = self.versions().json["versions"]

        self.assertEqual(history.LIMIT, len(versions))
        # Numbered from the oldest ever recorded, not from the top of the page.
        self.assertEqual(history.LIMIT + 4, versions[0]["number"])
        # And the oldest one *shown* is not the creation of the query, so it
        # must not be labelled as one. It is compared against the row below the
        # page, which is why one more than the page is fetched.
        self.assertNotEqual(["Created"], versions[-1]["changed"])
        self.assertEqual(["SQL"], versions[-1]["changed"])


class TestItIsThisQuerysHistory(VersionTestCase):
    def test_another_querys_versions_are_not_in_it(self):
        # The leak this guards is not a permission one -- both queries are in
        # the same organisation and readable -- it is a history that shows SQL
        # from a query nobody opened.
        other = self.factory.create_query(name="Refunds", query_text="select refunds")
        db.session.commit()
        self.make_request("post", "/api/queries/{}".format(other.id), data={"query": "select refunds again"})

        versions = self.versions().json["versions"]

        for version in versions:
            self.assertNotIn("refunds", version["values"]["query"])

    def test_and_the_numbering_counts_only_its_own(self):
        other = self.factory.create_query(name="Refunds")
        db.session.commit()
        self.make_request("post", "/api/queries/{}".format(other.id), data={"query": "select refunds"})

        self.save(query="select 2")

        self.assertEqual([2, 1], [version["number"] for version in self.versions().json["versions"]])


class TestWhoMayReadIt(VersionTestCase):
    def test_somebody_who_may_read_the_query_may_read_its_history(self):
        # The SQL is the whole of what a version holds, and they can already
        # read the SQL.
        viewer = self.factory.create_user()

        self.assertEqual(200, self.versions(user=viewer).status_code)

    def test_but_not_a_query_in_another_organisation(self):
        elsewhere = self.factory.create_org()
        theirs = self.factory.create_query(org=elsewhere)
        db.session.commit()

        rv = self.make_request("get", "/api/queries/{}/versions".format(theirs.id))

        self.assertEqual(404, rv.status_code)

    def test_nor_one_whose_data_source_they_cannot_see(self):
        private = self.factory.create_data_source(group=self.factory.create_group())
        hidden = self.factory.create_query(data_source=private)
        db.session.commit()
        outsider = self.factory.create_user()

        rv = self.make_request("get", "/api/queries/{}/versions".format(hidden.id), user=outsider)

        self.assertEqual(403, rv.status_code)


class TestRestoring(VersionTestCase):
    def first(self):
        """The id of the version this query was created with."""
        return self.versions().json["versions"][-1]["id"]

    def test_it_puts_the_sql_back(self):
        self.save(query="select 2")

        rv = self.restore(self.first())

        self.assertEqual(200, rv.status_code)
        self.assertEqual("select 1", models.Query.query.get(self.query.id).query_text)

    def test_as_a_new_version_rather_than_a_rewrite(self):
        self.save(query="select 2")
        before = self.versions().json["versions"]

        self.restore(self.first())
        after = self.versions().json["versions"]

        self.assertEqual(len(before) + 1, len(after))
        # The version that was restored is still where it was, saying what it
        # said. A history that could be edited by using it is not a history.
        self.assertEqual([version["id"] for version in before], [version["id"] for version in after[1:]])

    def test_restoring_what_is_already_there_writes_nothing(self):
        before = self.versions().json["versions"]

        self.restore(self.first())

        self.assertEqual(len(before), len(self.versions().json["versions"]))

    def test_it_does_not_move_the_query_to_another_data_source(self):
        # Where a query runs is a decision with its own access check, and a
        # surprising thing for a button called Restore to do.
        elsewhere = self.factory.create_data_source(group=self.factory.default_group)
        first = self.first()
        self.save(data_source_id=elsewhere.id)

        self.restore(first)

        self.assertEqual(elsewhere.id, models.Query.query.get(self.query.id).data_source_id)

    def test_nor_unpublish_it(self):
        first = self.first()
        self.save(is_draft=False)

        self.restore(first)

        self.assertFalse(models.Query.query.get(self.query.id).is_draft)

    def test_a_version_of_another_query_is_not_this_querys_to_restore(self):
        other = self.factory.create_query()
        db.session.commit()
        theirs = models.Change.query.filter(
            models.Change.object_id == other.id, models.Change.object_type == "queries"
        ).first()

        self.assertEqual(404, self.restore(theirs.id).status_code)

    def test_somebody_who_may_not_edit_the_query_may_not_restore_it(self):
        # A restore writes the SQL. Anyone who could not have typed it cannot
        # arrive at the same text by pressing a button in the history.
        other = self.factory.create_user()
        first = self.first()
        self.save(query="select 2")

        self.assertEqual(403, self.restore(first, user=other).status_code)
        self.assertEqual("select 2", models.Query.query.get(self.query.id).query_text)

    def test_nor_a_query_in_another_organisation(self):
        elsewhere = self.factory.create_org()
        theirs = self.factory.create_query(org=elsewhere)
        db.session.commit()
        version = models.Change.query.filter(
            models.Change.object_id == theirs.id, models.Change.object_type == "queries"
        ).first()

        rv = self.make_request("post", "/api/queries/{}/versions/{}/restore".format(theirs.id, version.id))

        self.assertEqual(404, rv.status_code)

    def without_scheduling(self):
        """
        Take `schedule_query` away from the only group this user is in.

        Done before any request is made as them: `User.permissions` caches
        against the group ids it was built from, and in production that cache
        cannot go stale because the instance does not outlive one request. In a
        test it does, so a request made first would have cached the permission
        this is trying to remove -- and the test would pass against a handler
        that checked nothing.
        """
        group = self.factory.default_group
        group.permissions = [name for name in group.permissions if name != "schedule_query"]
        db.session.add(group)
        db.session.commit()

    def oldest_change(self):
        """The creation version's id, read without making a request."""
        return (
            models.Change.query.filter(
                models.Change.object_id == self.query.id,
                models.Change.object_type == "queries",
            )
            .order_by(models.Change.id.asc())
            .first()
            .id
        )

    def test_putting_a_different_schedule_back_asks_for_permission_to_schedule(self):
        # Restoring a schedule is setting one, and setting one is a permission
        # of its own: it decides what runs on the data source unattended.
        first = self.oldest_change()
        self.query.schedule = {"interval": 3600}
        db.session.commit()
        self.without_scheduling()

        self.assertEqual(403, self.restore(first).status_code)
        self.assertEqual({"interval": 3600}, models.Query.query.get(self.query.id).schedule)

    def test_but_a_restore_that_leaves_the_schedule_alone_does_not(self):
        # Otherwise every restore would need the schedule permission, which
        # would put the history out of reach of most people who edit queries.
        first = self.oldest_change()
        self.query.query_text = "select 2"
        db.session.commit()
        self.without_scheduling()

        self.assertEqual(200, self.restore(first).status_code)
        self.assertEqual("select 1", models.Query.query.get(self.query.id).query_text)

    def test_a_version_naming_a_dropdown_query_they_cannot_read_is_not_restored(self):
        """
        Saving such a dropdown by hand is refused. Restoring a version that
        once named one was not, and the dropdown endpoint then served that
        query's values.
        """
        secret_group = self.factory.create_group(name="Finance")
        secret_source = self.factory.create_data_source(name="Finance", group=secret_group)
        secret = self.factory.create_query(data_source=secret_source, name="Salaries")
        parameters = [{"name": "who", "title": "who", "type": "query", "queryId": secret.id}]
        query = self.factory.create_query(name="Uses it", options={"parameters": parameters})
        db.session.commit()
        first = models.Change.query.filter(
            models.Change.object_id == query.id, models.Change.object_type == "queries"
        ).first()
        self.make_request("post", "/api/queries/{}".format(query.id), data={"options": {"parameters": []}})

        rv = self.make_request("post", "/api/queries/{}/versions/{}/restore".format(query.id, first.id))

        self.assertEqual(403, rv.status_code)
        self.assertEqual([], models.Query.query.get(query.id).options.get("parameters"))

    def test_view_only_access_to_the_source_is_not_enough(self):
        # A restore writes the SQL, which is deciding what runs on the data
        # source -- the same decision as typing it, and it asks for the same
        # access.
        group = self.factory.create_group()
        source = self.factory.create_data_source(group=group, view_only=True)
        query = self.factory.create_query(data_source=source, user=self.factory.user)
        db.session.commit()
        version = models.Change.query.filter(
            models.Change.object_id == query.id, models.Change.object_type == "queries"
        ).first()

        rv = self.make_request("post", "/api/queries/{}/versions/{}/restore".format(query.id, version.id))

        self.assertEqual(403, rv.status_code)
