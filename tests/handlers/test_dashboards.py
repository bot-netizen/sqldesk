from sqldesk.handlers.dashboards import DashboardArchiveResource, DashboardListResource
from sqldesk.models import AccessPermission, ApiKey, Dashboard, db
from sqldesk.permissions import ACCESS_TYPE_MODIFY
from sqldesk.serializers import serialize_dashboard
from sqldesk.utils import json_loads
from tests import BaseTestCase


class TestDashboardListResource(BaseTestCase):
    def test_create_new_dashboard(self):
        dashboard_name = "Test Dashboard"
        rv = self.make_request("post", "/api/dashboards", data={"name": dashboard_name})
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv.json["name"], "Test Dashboard")
        self.assertEqual(rv.json["user_id"], self.factory.user.id)
        self.assertEqual(rv.json["layout"], [])


class TestDashboardListGetResource(BaseTestCase):
    def test_returns_dashboards(self):
        d1 = self.factory.create_dashboard()
        d2 = self.factory.create_dashboard()
        d3 = self.factory.create_dashboard()

        rv = self.make_request("get", "/api/dashboards")

        assert len(rv.json["results"]) == 3
        assert set([result["id"] for result in rv.json["results"]]) == set([d1.id, d2.id, d3.id])

    def test_filters_with_tags(self):
        d1 = self.factory.create_dashboard(tags=["test"])
        self.factory.create_dashboard()
        self.factory.create_dashboard()

        rv = self.make_request("get", "/api/dashboards?tags=test")
        assert len(rv.json["results"]) == 1
        assert set([result["id"] for result in rv.json["results"]]) == set([d1.id])

    def test_search_term(self):
        d1 = self.factory.create_dashboard(name="Sales")
        d2 = self.factory.create_dashboard(name="Q1 sales")
        self.factory.create_dashboard(name="Ops")

        rv = self.make_request("get", "/api/dashboards?q=sales")
        assert len(rv.json["results"]) == 2
        assert set([result["id"] for result in rv.json["results"]]) == set([d1.id, d2.id])


class TestDashboardResourceGet(BaseTestCase):
    def test_the_public_link_goes_only_to_people_who_may_revoke_it(self):
        # The link is a credential for every query on the dashboard.
        d = self.factory.create_dashboard(user=self.factory.create_user())
        self.factory.create_api_key(object=d)
        db.session.commit()

        as_viewer = self.make_request("get", "/api/dashboards/{}".format(d.id)).json
        as_admin = self.make_request("get", "/api/dashboards/{}".format(d.id), user=self.factory.create_admin()).json

        self.assertNotIn("api_key", as_viewer)
        self.assertNotIn("public_url", as_viewer)
        self.assertIn("api_key", as_admin)

    def test_get_dashboard(self):
        d1 = self.factory.create_dashboard()
        rv = self.make_request("get", "/api/dashboards/{0}".format(d1.id))
        self.assertEqual(rv.status_code, 200)

        expected = serialize_dashboard(d1, with_widgets=True, with_favorite_state=False)
        actual = json_loads(rv.data)

        self.assertResponseEqual(expected, actual)

    def test_get_dashboard_with_slug(self):
        d1 = self.factory.create_dashboard()
        rv = self.make_request("get", "/api/dashboards/{0}?legacy".format(d1.slug))
        self.assertEqual(rv.status_code, 200)

        expected = serialize_dashboard(d1, with_widgets=True, with_favorite_state=False)
        actual = json_loads(rv.data)

        self.assertResponseEqual(expected, actual)

    def test_get_dashboard_filters_unauthorized_widgets(self):
        dashboard = self.factory.create_dashboard()

        restricted_ds = self.factory.create_data_source(group=self.factory.create_group())
        query = self.factory.create_query(data_source=restricted_ds)
        vis = self.factory.create_visualization(query_rel=query)
        restricted_widget = self.factory.create_widget(visualization=vis, dashboard=dashboard)
        widget = self.factory.create_widget(dashboard=dashboard)
        dashboard.layout = [[widget.id, restricted_widget.id]]
        db.session.commit()

        rv = self.make_request("get", "/api/dashboards/{0}".format(dashboard.id))
        self.assertEqual(rv.status_code, 200)
        self.assertTrue(rv.json["widgets"][0]["restricted"])
        self.assertNotIn("restricted", rv.json["widgets"][1])

    def test_get_non_existing_dashboard(self):
        rv = self.make_request("get", "/api/dashboards/-1")
        self.assertEqual(rv.status_code, 404)


class TestDashboardResourcePost(BaseTestCase):
    def test_update_dashboard(self):
        d = self.factory.create_dashboard()
        new_name = "New Name"
        rv = self.make_request(
            "post",
            "/api/dashboards/{0}".format(d.id),
            data={"name": new_name, "layout": []},
        )
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv.json["name"], new_name)

    def test_raises_error_in_case_of_conflict(self):
        d = self.factory.create_dashboard()
        d.name = "Updated"
        db.session.commit()
        new_name = "New Name"
        rv = self.make_request(
            "post",
            "/api/dashboards/{0}".format(d.id),
            data={"name": new_name, "layout": [], "version": d.version - 1},
        )

        self.assertEqual(rv.status_code, 409)

    def test_overrides_existing_if_no_version_specified(self):
        d = self.factory.create_dashboard()
        d.name = "Updated"

        new_name = "New Name"
        rv = self.make_request(
            "post",
            "/api/dashboards/{0}".format(d.id),
            data={"name": new_name, "layout": []},
        )

        self.assertEqual(rv.status_code, 200)

    def test_works_for_non_owner_with_permission(self):
        d = self.factory.create_dashboard()
        user = self.factory.create_user()

        new_name = "New Name"
        rv = self.make_request(
            "post",
            "/api/dashboards/{0}".format(d.id),
            data={"name": new_name, "layout": [], "version": d.version},
            user=user,
        )
        self.assertEqual(rv.status_code, 403)

        AccessPermission.grant(obj=d, access_type=ACCESS_TYPE_MODIFY, grantee=user, grantor=d.user)

        rv = self.make_request(
            "post",
            "/api/dashboards/{0}".format(d.id),
            data={"name": new_name, "layout": [], "version": d.version},
            user=user,
        )

        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv.json["name"], new_name)


class TestDashboardForkResourcePost(BaseTestCase):
    def test_forks_a_dashboard(self):
        dashboard = self.factory.create_dashboard()

        rv = self.make_request("post", "/api/dashboards/{}/fork".format(dashboard.id))

        self.assertEqual(rv.status_code, 200)

    def test_a_copy_of_a_streaming_dashboard_is_a_streaming_dashboard(self):
        # It defaulted to "saved": the copy landed in the saved list with
        # stream widgets on it, and was offered warehouse intervals.
        dashboard = self.factory.create_dashboard(kind="streaming")
        db.session.commit()

        rv = self.make_request("post", "/api/dashboards/{}/fork".format(dashboard.id))

        self.assertEqual("streaming", Dashboard.query.get(rv.json["id"]).kind)

    def test_a_copy_carries_only_the_panels_the_copier_may_read(self):
        # The copy is the copier's to share, and a public link reads every
        # query on the dashboard it is for -- so a locked panel must not
        # come along.
        locked = self.factory.create_data_source(group=self.factory.create_group())
        secret = self.factory.create_query(data_source=locked)
        dashboard = self.factory.create_dashboard(user=self.factory.create_user())
        self.factory.create_widget(
            dashboard=dashboard, visualization=self.factory.create_visualization(query_rel=secret)
        )
        self.factory.create_widget(dashboard=dashboard, visualization=self.factory.create_visualization())
        db.session.commit()

        rv = self.make_request("post", "/api/dashboards/{}/fork".format(dashboard.id))

        self.assertEqual(rv.status_code, 200)
        copied = [w["visualization"]["query"]["id"] for w in rv.json["widgets"] if w.get("visualization")]
        self.assertNotIn(secret.id, copied)
        self.assertEqual(1, len(copied))


class TestDashboardResourceDelete(BaseTestCase):
    def test_delete_dashboard(self):
        d = self.factory.create_dashboard()

        rv = self.make_request("delete", "/api/dashboards/{0}".format(d.id))
        self.assertEqual(rv.status_code, 200)

        d = Dashboard.get_by_id_and_org(d.id, d.org)
        self.assertTrue(d.is_archived)

    def test_only_its_owner_or_an_admin_archives_it(self):
        d = self.factory.create_dashboard(user=self.factory.create_user())
        db.session.commit()

        rv = self.make_request("delete", "/api/dashboards/{0}".format(d.id))

        self.assertEqual(rv.status_code, 403)
        self.assertFalse(Dashboard.get_by_id_and_org(d.id, d.org).is_archived)

    def test_a_missing_dashboard_is_not_found(self):
        self.assertEqual(404, self.make_request("delete", "/api/dashboards/999999").status_code)


class TestDashboardShareResourcePost(BaseTestCase):
    def test_creates_api_key(self):
        dashboard = self.factory.create_dashboard()

        res = self.make_request("post", "/api/dashboards/{}/share".format(dashboard.id))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json["api_key"], ApiKey.get_by_object(dashboard).api_key)

    def test_requires_admin_or_owner(self):
        dashboard = self.factory.create_dashboard()
        user = self.factory.create_user()

        res = self.make_request("post", "/api/dashboards/{}/share".format(dashboard.id), user=user)
        self.assertEqual(res.status_code, 403)

        user.group_ids.append(self.factory.org.admin_group.id)

        res = self.make_request("post", "/api/dashboards/{}/share".format(dashboard.id), user=user)
        self.assertEqual(res.status_code, 200)


class TestDashboardShareResourceDelete(BaseTestCase):
    def test_disables_api_key(self):
        dashboard = self.factory.create_dashboard()
        ApiKey.create_for_object(dashboard, self.factory.user)

        res = self.make_request("delete", "/api/dashboards/{}/share".format(dashboard.id))
        self.assertEqual(res.status_code, 200)
        self.assertIsNone(ApiKey.get_by_object(dashboard))

    def test_ignores_when_no_api_key_exists(self):
        dashboard = self.factory.create_dashboard()

        res = self.make_request("delete", "/api/dashboards/{}/share".format(dashboard.id))
        self.assertEqual(res.status_code, 200)

    def test_requires_admin_or_owner(self):
        dashboard = self.factory.create_dashboard()
        user = self.factory.create_user()

        res = self.make_request("delete", "/api/dashboards/{}/share".format(dashboard.id), user=user)
        self.assertEqual(res.status_code, 403)

        user.group_ids.append(self.factory.org.admin_group.id)

        res = self.make_request("delete", "/api/dashboards/{}/share".format(dashboard.id), user=user)
        self.assertEqual(res.status_code, 200)


class TestTheDashboardArchive(BaseTestCase):
    """
    `/api/dashboards/archive`.

    There has been an is_archived flag and an Archive action since the fork,
    and no way to see what had been archived -- an archived dashboard was
    reachable only by remembering its address, which is a poor place to keep
    the one you might want back.
    """

    def setUp(self):
        super().setUp()
        self.live = self.factory.create_dashboard(name="Still in use", is_draft=False)
        self.gone = self.factory.create_dashboard(name="Archived one", is_draft=False, is_archived=True)
        db.session.commit()

    def names(self, path="/api/dashboards/archive", **params):
        rv = self.make_request("get", path, **params)
        self.assertEqual(200, rv.status_code, rv.data[:300])
        return [one["name"] for one in rv.json["results"]]

    def test_the_archive_lists_what_was_archived(self):
        self.assertEqual(["Archived one"], self.names())

    def test_and_nothing_that_is_still_in_use(self):
        self.assertNotIn("Still in use", self.names())

    def test_the_index_is_unchanged_by_the_archive_existing(self):
        names = self.names("/api/dashboards")

        self.assertIn("Still in use", names)
        self.assertNotIn("Archived one", names)

    def test_the_archive_can_be_searched(self):
        self.factory.create_dashboard(name="Another archived", is_draft=False, is_archived=True)
        db.session.commit()

        self.assertEqual(["Archived one"], self.names(path="/api/dashboards/archive?q=Archived one"))

    def test_searching_the_archive_does_not_reach_the_index(self):
        self.assertEqual([], self.names(path="/api/dashboards/archive?q=Still in use"))

    def test_archiving_moves_a_dashboard_between_the_two(self):
        self.assertIn("Still in use", self.names("/api/dashboards"))

        rv = self.make_request("delete", "/api/dashboards/{}".format(self.live.id))
        self.assertEqual(200, rv.status_code, rv.data[:300])

        self.assertNotIn("Still in use", self.names("/api/dashboards"))
        self.assertIn("Still in use", self.names())

    def test_somebody_elses_dashboard_is_not_in_your_archive(self):
        # The archive is the index's other half, so it answers to the same
        # permission rule rather than a looser one.
        other_org = self.factory.create_org()
        other_user = self.factory.create_user(org=other_org)
        self.factory.create_dashboard(name="Theirs", is_draft=False, is_archived=True, org=other_org, user=other_user)
        db.session.commit()

        self.assertNotIn("Theirs", self.names())

    def test_it_is_the_index_with_the_flag_flipped_rather_than_a_second_listing(self):
        # Shared on purpose: the permission, the tag and folder filters, the
        # kind filter, the ordering and the pagination are written once. A
        # reimplemented archive is how one of those quietly stops matching.
        self.assertTrue(issubclass(DashboardArchiveResource, DashboardListResource))
        self.assertFalse(DashboardListResource.archived)
        self.assertTrue(DashboardArchiveResource.archived)
        self.assertEqual(DashboardListResource.get, DashboardArchiveResource.get)

    def test_a_folder_filter_works_on_the_archive_too(self):
        # It comes free from sharing the handler, and is worth an assertion
        # because that is exactly what would be lost by reimplementing it.
        folder = self.factory.create_dashboard_folder() if hasattr(self.factory, "create_dashboard_folder") else None
        if folder is None:
            self.skipTest("this install has no dashboard folders")
        self.gone.folder_id = folder.id
        db.session.commit()

        self.assertEqual(["Archived one"], self.names(path="/api/dashboards/archive?folder={}".format(folder.id)))
