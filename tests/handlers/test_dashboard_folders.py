"""
Folders for dashboards, and the lock that makes one mean something.

A set called "business KPIs" that anybody can edit is a set of dashboards with
a label on it. One only administrators can change is a statement about what has
been through review -- so the lock is on *changing*, never on seeing, and it
covers every way a dashboard can be changed rather than the obvious one.
"""

from sqldesk import models
from sqldesk.models import db
from tests import BaseTestCase


class FolderTestCase(BaseTestCase):
    def folder(self, name="Business KPIs", locked=True, meaning="Numbers the board reads."):
        folder = models.DashboardFolder(org=self.factory.org, name=name, meaning=meaning, locked=locked)
        db.session.add(folder)
        db.session.commit()
        return folder

    def filed(self, folder):
        dashboard = self.factory.create_dashboard(user=self.factory.user)
        dashboard.folder = folder
        db.session.commit()
        return dashboard


class TestMakingOne(FolderTestCase):
    def test_an_administrator_makes_one_with_its_meaning(self):
        rv = self.make_request(
            "post",
            "/api/dashboard_folders",
            data={"name": "Operational metrics", "meaning": "What the line is doing.", "locked": True},
            user=self.factory.create_admin(),
        )

        self.assertEqual(200, rv.status_code)
        self.assertEqual("What the line is doing.", rv.json["meaning"])
        self.assertTrue(rv.json["locked"])

    def test_anybody_else_may_not(self):
        rv = self.make_request("post", "/api/dashboard_folders", data={"name": "Mine"})

        self.assertEqual(403, rv.status_code)

    def test_two_with_the_same_name_are_refused(self):
        admin = self.factory.create_admin()
        self.folder(name="KPIs")

        rv = self.make_request("post", "/api/dashboard_folders", data={"name": "KPIs"}, user=admin)

        self.assertEqual(400, rv.status_code)

    def test_everybody_can_read_the_list(self):
        # The lock is on changing, never on seeing: the point of a folder is
        # that people find what is in it.
        self.folder()

        rv = self.make_request("get", "/api/dashboard_folders", user=self.factory.create_user())

        self.assertEqual(200, rv.status_code)
        self.assertEqual("Business KPIs", rv.json[0]["name"])

    def test_the_list_says_how_much_is_in_each(self):
        folder = self.folder()
        self.filed(folder)

        rv = self.make_request("get", "/api/dashboard_folders")

        self.assertEqual(1, rv.json[0]["dashboards"])


class TestTheLock(FolderTestCase):
    """
    Four ways to change a dashboard, and the lock has to cover all of them.
    One that covered three would be worse than none, because it would look
    like protection.
    """

    def test_its_owner_cannot_edit_it(self):
        dashboard = self.filed(self.folder())

        rv = self.make_request("post", "/api/dashboards/{}".format(dashboard.id), data={"name": "Renamed"})

        self.assertEqual(403, rv.status_code)

    def test_nor_archive_it(self):
        dashboard = self.filed(self.folder())

        rv = self.make_request("delete", "/api/dashboards/{}".format(dashboard.id))

        self.assertEqual(403, rv.status_code)
        self.assertFalse(models.Dashboard.query.get(dashboard.id).is_archived)

    def test_nor_add_a_widget_to_it(self):
        dashboard = self.filed(self.folder())
        visualization = self.factory.create_visualization()

        rv = self.make_request(
            "post",
            "/api/widgets",
            data={
                "dashboard_id": dashboard.id,
                "visualization_id": visualization.id,
                "options": {"position": {"col": 0, "row": 0, "sizeX": 3, "sizeY": 3}},
                "width": 1,
                "text": "",
            },
        )

        self.assertEqual(403, rv.status_code)

    def test_but_an_administrator_can(self):
        dashboard = self.filed(self.folder())

        rv = self.make_request(
            "post",
            "/api/dashboards/{}".format(dashboard.id),
            data={"name": "Renamed"},
            user=self.factory.create_admin(),
        )

        self.assertEqual(200, rv.status_code)

    def test_and_an_unlocked_folder_changes_nothing(self):
        # Filing a dashboard is not the same as freezing it.
        dashboard = self.filed(self.folder(name="Scratch", locked=False))

        rv = self.make_request("post", "/api/dashboards/{}".format(dashboard.id), data={"name": "Renamed"})

        self.assertEqual(200, rv.status_code)

    def test_the_page_is_told_it_cannot_edit(self):
        # So it shows a read-only dashboard rather than buttons that 403.
        dashboard = self.filed(self.folder())

        rv = self.make_request("get", "/api/dashboards/{}".format(dashboard.id))

        self.assertFalse(rv.json["can_edit"])
        self.assertTrue(rv.json["folder"]["locked"])


class TestMovingOneInAndOut(FolderTestCase):
    def move(self, dashboard, folder_id, user=None):
        return self.make_request(
            "post", "/api/dashboards/{}/folder".format(dashboard.id), data={"folder_id": folder_id}, user=user
        )

    def test_filing_into_a_locked_folder_is_an_administrators_act(self):
        dashboard = self.factory.create_dashboard(user=self.factory.user)
        folder = self.folder()

        self.assertEqual(403, self.move(dashboard, folder.id).status_code)
        self.assertEqual(200, self.move(dashboard, folder.id, user=self.factory.create_admin()).status_code)

    def test_and_so_is_taking_one_out_of_one(self):
        # Otherwise anybody could take a dashboard out of the folder that
        # protects it, change it, and put it back -- and the lock would be a
        # doorway with a sign on it.
        dashboard = self.filed(self.folder())

        self.assertEqual(403, self.move(dashboard, None).status_code)
        self.assertEqual(200, self.move(dashboard, None, user=self.factory.create_admin()).status_code)
        self.assertIsNone(models.Dashboard.query.get(dashboard.id).folder_id)

    def test_an_unlocked_folder_only_needs_the_dashboards_own_permission(self):
        dashboard = self.factory.create_dashboard(user=self.factory.user)
        folder = self.folder(name="Scratch", locked=False)

        self.assertEqual(200, self.move(dashboard, folder.id).status_code)

    def test_somebody_elses_dashboard_is_not_yours_to_file(self):
        folder = self.folder(name="Scratch", locked=False)
        theirs = self.factory.create_dashboard(user=self.factory.create_user())
        db.session.commit()

        self.assertEqual(403, self.move(theirs, folder.id).status_code)


class TestRemovingAFolder(FolderTestCase):
    def test_one_that_still_holds_dashboards_is_refused(self):
        # Rather than quietly unfiling them: deleting a folder somebody curated
        # is a decision about those dashboards, taken with them in front of you.
        folder = self.folder()
        self.filed(folder)

        rv = self.make_request(
            "delete", "/api/dashboard_folders/{}".format(folder.id), user=self.factory.create_admin()
        )

        self.assertEqual(400, rv.status_code)
        self.assertIn("1 dashboard", rv.json["message"])

    def test_an_empty_one_goes(self):
        folder = self.folder()

        rv = self.make_request(
            "delete", "/api/dashboard_folders/{}".format(folder.id), user=self.factory.create_admin()
        )

        self.assertEqual(200, rv.status_code)
        self.assertEqual(0, models.DashboardFolder.query.count())


class TestFilteringTheList(FolderTestCase):
    def test_the_list_can_be_asked_for_one_folder(self):
        folder = self.folder(name="KPIs", locked=False)
        self.filed(folder)
        self.factory.create_dashboard(user=self.factory.user, name="Loose")
        db.session.commit()

        rv = self.make_request("get", "/api/dashboards?folder={}".format(folder.id))

        self.assertEqual(1, rv.json["count"])

    def test_and_for_the_ones_nobody_filed(self):
        folder = self.folder(name="KPIs", locked=False)
        self.filed(folder)
        self.factory.create_dashboard(user=self.factory.user, name="Loose")
        db.session.commit()

        rv = self.make_request("get", "/api/dashboards?folder=none")

        self.assertEqual(1, rv.json["count"])

    def test_and_with_no_folder_asked_for_it_is_all_of_them(self):
        folder = self.folder(name="KPIs", locked=False)
        self.filed(folder)
        self.factory.create_dashboard(user=self.factory.user, name="Loose")
        db.session.commit()

        rv = self.make_request("get", "/api/dashboards")

        self.assertEqual(2, rv.json["count"])


class TestTheFolderModelDidNotStealAnything(BaseTestCase):
    """
    `@gfk_type` registers a class for generic foreign keys -- favourites, API
    keys, change records all find a dashboard through it. Adding the folder
    model in front of `Dashboard` took its decorator, because a decorator sits
    above the class it belongs to and an insertion there is invisible.

    Nothing failed loudly. Favouriting a dashboard just stopped resolving.
    """

    def test_a_dashboard_is_still_registered_for_generic_keys(self):
        from sqldesk.models.base import _gfk_types

        self.assertIn("dashboards", _gfk_types)
        self.assertIs(models.Dashboard, _gfk_types["dashboards"])

    def test_and_a_folder_is_not(self):
        # It is nobody's generic target: nothing favourites a folder.
        from sqldesk.models.base import _gfk_types

        self.assertNotIn("dashboard_folders", _gfk_types)

    def test_favouriting_a_dashboard_still_finds_it(self):
        # The thing that quietly broke.
        dashboard = self.factory.create_dashboard()
        db.session.commit()

        rv = self.make_request("post", "/api/dashboards/{}/favorite".format(dashboard.id))

        self.assertEqual(200, rv.status_code)
        self.assertEqual(1, models.Favorite.query.count())


class TestADashboardIsOneKindOrTheOther(BaseTestCase):
    """
    A dashboard has one refresh interval, and that is the whole argument.

    A stream panel wants two seconds; a warehouse panel wants thirty or more.
    Mixing them means either running every warehouse query behind the board
    every two seconds, or showing a stream half a minute stale -- the one thing
    a stream exists not to be.
    """

    def cluster(self):
        return self.factory.create_data_source(name="Cluster", type="kafka_stream", group=self.factory.default_group)

    def widget_on(self, dashboard, source):
        query = self.factory.create_query(data_source=source)
        visualization = self.factory.create_visualization(query_rel=query)
        db.session.commit()
        return self.make_request(
            "post",
            "/api/widgets",
            data={
                "dashboard_id": dashboard.id,
                "visualization_id": visualization.id,
                "options": {"position": {"col": 0, "row": 0, "sizeX": 3, "sizeY": 3}},
                "width": 1,
                "text": "",
            },
        )

    def test_a_dashboard_with_no_widgets_is_not_streaming(self):
        self.assertFalse(self.factory.create_dashboard().is_streaming)

    def test_an_ordinary_dashboard_takes_an_ordinary_panel(self):
        # Named for the rule as it now is. The first widget used to *decide*
        # the kind, because the kind was worked out from the widgets; it is
        # declared when the dashboard is made, and the widget is merely
        # allowed or refused against it.
        dashboard = self.factory.create_dashboard()

        self.assertEqual(200, self.widget_on(dashboard, self.factory.data_source).status_code)
        self.assertFalse(models.Dashboard.query.get(dashboard.id).is_streaming)

    def test_a_textbox_belongs_on_either(self):
        # It draws on nothing, so it decides nothing.
        dashboard = self.factory.create_dashboard()
        self.widget_on(dashboard, self.factory.data_source)

        rv = self.make_request(
            "post",
            "/api/widgets",
            data={
                "dashboard_id": dashboard.id,
                "options": {"position": {"col": 0, "row": 4, "sizeX": 3, "sizeY": 1}},
                "width": 1,
                "text": "A note",
                "visualization_id": None,
            },
        )

        self.assertEqual(200, rv.status_code)
