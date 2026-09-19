import datetime
import time
from unittest import mock

from sqldesk import live, models, settings
from sqldesk.models import db
from sqldesk.utils import gen_query_hash, utcnow
from tests import BaseTestCase


def _live_dashboard(factory, interval=30, paused=False, **kwargs):
    dashboard = factory.create_dashboard(**kwargs)
    dashboard.live = {"interval": interval, "paused": paused}
    db.session.add(dashboard)
    db.session.commit()
    return dashboard


def _grant_live(factory, user):
    group = factory.create_group(name="Live", permissions=[live.MANAGE_LIVE_PERMISSION])
    db.session.add(group)
    db.session.commit()
    user.group_ids = list(user.group_ids) + [group.id]
    db.session.add(user)
    db.session.commit()
    return group


class TestTurningLive(BaseTestCase):
    def test_needs_the_permission(self):
        dashboard = self.factory.create_dashboard()
        rv = self.make_request("post", "/api/dashboards/{}/live".format(dashboard.id), data={"interval": 30})
        self.assertEqual(rv.status_code, 403)
        self.assertIsNone(models.Dashboard.query.get(dashboard.id).live)

    def test_admins_have_it(self):
        admin = self.factory.create_admin()
        dashboard = self.factory.create_dashboard(user=admin)
        rv = self.make_request(
            "post", "/api/dashboards/{}/live".format(dashboard.id), data={"interval": 60}, user=admin
        )
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv.json["live"]["interval"], 60)
        self.assertFalse(rv.json["live"]["paused"])

    def test_a_group_can_be_granted_it(self):
        user = self.factory.user
        _grant_live(self.factory, user)
        dashboard = self.factory.create_dashboard(user=user)
        rv = self.make_request("post", "/api/dashboards/{}/live".format(dashboard.id), data={"interval": 30})
        self.assertEqual(rv.status_code, 200)

    def test_the_permission_alone_does_not_let_you_change_someone_elses_dashboard(self):
        _grant_live(self.factory, self.factory.user)
        dashboard = self.factory.create_dashboard(user=self.factory.create_user())
        rv = self.make_request("post", "/api/dashboards/{}/live".format(dashboard.id), data={"interval": 30})
        self.assertEqual(rv.status_code, 403)

    def test_only_the_offered_intervals(self):
        admin = self.factory.create_admin()
        dashboard = self.factory.create_dashboard(user=admin)
        path = "/api/dashboards/{}/live".format(dashboard.id)
        rv = self.make_request("post", path, data={"interval": 5}, user=admin)
        self.assertEqual(rv.status_code, 400)

    def test_an_empty_request_is_refused(self):
        admin = self.factory.create_admin()
        dashboard = self.factory.create_dashboard(user=admin)
        rv = self.make_request("post", "/api/dashboards/{}/live".format(dashboard.id), data={}, user=admin)
        self.assertEqual(rv.status_code, 400)

    def test_pause_resume_and_off(self):
        admin = self.factory.create_admin(name="Iqbal")
        dashboard = _live_dashboard(self.factory, user=admin)
        path = "/api/dashboards/{}/live".format(dashboard.id)

        rv = self.make_request("post", path, data={"paused": True}, user=admin)
        self.assertTrue(rv.json["live"]["paused"])
        self.assertEqual(rv.json["live"]["paused_by"]["name"], "Iqbal")
        self.assertIsNotNone(rv.json["live"]["paused_at"])

        rv = self.make_request("post", path, data={"paused": False}, user=admin)
        self.assertFalse(rv.json["live"]["paused"])
        self.assertIsNone(rv.json["live"]["paused_by"])

        rv = self.make_request("post", path, data={"interval": None}, user=admin)
        self.assertIsNone(rv.json["live"])
        self.assertIsNone(models.Dashboard.query.get(dashboard.id).live)

    def test_only_a_live_dashboard_can_be_paused(self):
        admin = self.factory.create_admin()
        dashboard = self.factory.create_dashboard(user=admin)
        path = "/api/dashboards/{}/live".format(dashboard.id)
        rv = self.make_request("post", path, data={"paused": True}, user=admin)
        self.assertEqual(rv.status_code, 400)

    def test_does_not_bump_the_version_an_editor_saves_against(self):
        # Pausing while someone edits the layout must not make their save a
        # conflict with a change they cannot see.
        admin = self.factory.create_admin()
        dashboard = self.factory.create_dashboard(user=admin)
        version = dashboard.version
        self.make_request("post", "/api/dashboards/{}/live".format(dashboard.id), data={"interval": 30}, user=admin)
        self.assertEqual(models.Dashboard.query.get(dashboard.id).version, version)

    def test_the_dashboard_says_it_is_live(self):
        dashboard = _live_dashboard(self.factory, interval=120)
        rv = self.make_request("get", "/api/dashboards/{}".format(dashboard.id))
        self.assertEqual(rv.json["live"]["interval"], 120)
        self.assertEqual(rv.json["live"]["check_in_seconds"], live.CHECK_IN_SECONDS)

    def test_an_ordinary_dashboard_is_not(self):
        dashboard = self.factory.create_dashboard()
        rv = self.make_request("get", "/api/dashboards/{}".format(dashboard.id))
        self.assertIsNone(rv.json["live"])

    def test_a_leftover_schedule_does_not_make_a_dashboard_live(self):
        # 0.2.0 stored cron schedules on dashboards; they are not live settings.
        dashboard = self.factory.create_dashboard()
        dashboard.schedule = {"cron": "*/5 * * * *"}
        db.session.add(dashboard)
        db.session.commit()
        rv = self.make_request("get", "/api/dashboards/{}".format(dashboard.id))
        self.assertIsNone(rv.json["live"])


class TestWatching(BaseTestCase):
    def _widget(self, dashboard, text="SELECT 1"):
        query = self.factory.create_query(query_text=text)
        visualization = self.factory.create_visualization(query_rel=query)
        widget = self.factory.create_widget(dashboard=dashboard, visualization=visualization)
        db.session.commit()
        return widget

    def test_checking_in_makes_it_watched_and_leaving_does_not(self):
        dashboard = _live_dashboard(self.factory)
        path = "/api/dashboards/{}/live/watch".format(dashboard.id)
        self.assertFalse(live.is_watched(dashboard.id))

        rv = self.make_request("post", path, data={"viewer": "tab-1"})
        self.assertEqual(rv.status_code, 200)
        self.assertTrue(live.is_watched(dashboard.id))

        self.make_request("post", path, data={"viewer": "tab-1", "leaving": True})
        self.assertFalse(live.is_watched(dashboard.id))

    def test_one_viewer_leaving_does_not_stop_another(self):
        dashboard = _live_dashboard(self.factory)
        path = "/api/dashboards/{}/live/watch".format(dashboard.id)
        self.make_request("post", path, data={"viewer": "tab-1"})
        self.make_request("post", path, data={"viewer": "tab-2"})
        self.make_request("post", path, data={"viewer": "tab-1", "leaving": True})
        self.assertTrue(live.is_watched(dashboard.id))

    def test_a_viewer_who_stops_checking_in_stops_counting(self):
        dashboard = _live_dashboard(self.factory)
        live.check_in(dashboard.id, "tab", now=time.time() - live.WATCH_WINDOW - 1)
        self.assertFalse(live.is_watched(dashboard.id))

    def test_a_dashboard_that_is_not_live_is_not_watched(self):
        dashboard = self.factory.create_dashboard()
        rv = self.make_request("post", "/api/dashboards/{}/live/watch".format(dashboard.id), data={"viewer": "t"})
        self.assertIsNone(rv.json["live"])
        self.assertFalse(live.is_watched(dashboard.id))

    def test_needs_a_viewer_id(self):
        dashboard = _live_dashboard(self.factory)
        rv = self.make_request("post", "/api/dashboards/{}/live/watch".format(dashboard.id), data={})
        self.assertEqual(rv.status_code, 400)

    def test_reports_the_newest_result_for_each_widget(self):
        dashboard = _live_dashboard(self.factory)
        widget = self._widget(dashboard)
        result = self.factory.create_query_result(query_text="SELECT 1", query_hash=gen_query_hash("SELECT 1"))
        db.session.commit()

        rv = self.make_request("post", "/api/dashboards/{}/live/watch".format(dashboard.id), data={"viewer": "t"})
        self.assertEqual(rv.json["results"], {str(widget.id): result.id})

    def test_leaves_out_widgets_the_viewer_cannot_see(self):
        dashboard = _live_dashboard(self.factory)
        hidden_source = self.factory.create_data_source(group=self.factory.create_group())
        hidden_query = self.factory.create_query(data_source=hidden_source)
        hidden = self.factory.create_widget(
            dashboard=dashboard, visualization=self.factory.create_visualization(query_rel=hidden_query)
        )
        visible = self._widget(dashboard)
        db.session.commit()

        rv = self.make_request("post", "/api/dashboards/{}/live/watch".format(dashboard.id), data={"viewer": "t"})
        self.assertIn(str(visible.id), rv.json["results"])
        self.assertNotIn(str(hidden.id), rv.json["results"])

    def test_through_the_public_link(self):
        dashboard = _live_dashboard(self.factory)
        api_key = self.factory.create_api_key(object=dashboard)
        db.session.commit()
        rv = self.make_request(
            "post",
            "/api/dashboards/public/{}/live/watch".format(api_key.api_key),
            data={"viewer": "wall"},
            user=False,
        )
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv.json["live"]["interval"], 30)
        self.assertTrue(live.is_watched(dashboard.id))

    def test_the_public_dashboard_says_it_is_live(self):
        dashboard = _live_dashboard(self.factory)
        api_key = self.factory.create_api_key(object=dashboard)
        db.session.commit()
        rv = self.make_request("get", "/api/dashboards/public/{}".format(api_key.api_key), user=False)
        self.assertEqual(rv.json["live"]["interval"], 30)


@mock.patch("sqldesk.tasks.queries.execution.enqueue_query")
class TestRefreshingLiveDashboards(BaseTestCase):
    def _widget(self, dashboard, query=None, **widget_kwargs):
        query = query or self.factory.create_query(query_text="SELECT 1")
        widget = self.factory.create_widget(
            dashboard=dashboard, visualization=self.factory.create_visualization(query_rel=query), **widget_kwargs
        )
        db.session.commit()
        return widget

    def test_runs_a_watched_dashboards_queries(self, enqueue):
        dashboard = _live_dashboard(self.factory)
        widget = self._widget(dashboard)
        live.check_in(dashboard.id, "tab")

        live.refresh_live_dashboards()

        enqueue.assert_called_once()
        text, data_source, user_id = enqueue.call_args[0]
        self.assertEqual(text, "SELECT 1")
        self.assertEqual(data_source.id, widget.visualization.query_rel.data_source.id)
        self.assertEqual(enqueue.call_args[1]["metadata"]["dashboard_id"], dashboard.id)

    def test_not_while_nobody_watches(self, enqueue):
        dashboard = _live_dashboard(self.factory)
        self._widget(dashboard)
        live.refresh_live_dashboards()
        enqueue.assert_not_called()

    def test_not_while_paused(self, enqueue):
        dashboard = _live_dashboard(self.factory, paused=True)
        self._widget(dashboard)
        live.check_in(dashboard.id, "tab")
        live.refresh_live_dashboards()
        enqueue.assert_not_called()

    def test_not_when_archived(self, enqueue):
        dashboard = _live_dashboard(self.factory, is_archived=True)
        self._widget(dashboard)
        live.check_in(dashboard.id, "tab")
        live.refresh_live_dashboards()
        enqueue.assert_not_called()

    def test_not_while_the_result_is_fresh(self, enqueue):
        dashboard = _live_dashboard(self.factory, interval=60)
        self._widget(dashboard)
        self.factory.create_query_result(query_text="SELECT 1", query_hash=gen_query_hash("SELECT 1"))
        db.session.commit()
        live.check_in(dashboard.id, "tab")
        live.refresh_live_dashboards()
        enqueue.assert_not_called()

    def test_again_once_it_is_older_than_the_interval(self, enqueue):
        dashboard = _live_dashboard(self.factory, interval=30)
        self._widget(dashboard)
        old = utcnow().replace(microsecond=0)
        self.factory.create_query_result(
            query_text="SELECT 1",
            query_hash=gen_query_hash("SELECT 1"),
            retrieved_at=old - datetime.timedelta(seconds=40),
        )
        db.session.commit()
        live.check_in(dashboard.id, "tab")
        live.refresh_live_dashboards()
        enqueue.assert_called_once()

    def test_parameters_are_the_saved_values_or_the_widgets_fixed_one(self, enqueue):
        dashboard = _live_dashboard(self.factory)
        query = self.factory.create_query(
            query_text="SELECT {{n}}",
            options={"parameters": [{"name": "n", "title": "n", "type": "number", "value": 1}]},
        )
        self._widget(dashboard, query=query)
        fixed = self.factory.create_query(
            query_text="SELECT {{n}} + 0",
            options={"parameters": [{"name": "n", "title": "n", "type": "number", "value": 1}]},
        )
        mappings = {"n": {"type": "static-value", "value": 7}}
        self._widget(dashboard, query=fixed, options={"parameterMappings": mappings})
        live.check_in(dashboard.id, "tab")

        live.refresh_live_dashboards()

        texts = sorted(call[0][0] for call in enqueue.call_args_list)
        self.assertEqual(texts, ["SELECT 1", "SELECT 7 + 0"])

    def test_text_boxes_are_ignored(self, enqueue):
        dashboard = _live_dashboard(self.factory)
        self.factory.create_widget(dashboard=dashboard, visualization=None, text="hello")
        db.session.commit()
        live.check_in(dashboard.id, "tab")
        live.refresh_live_dashboards()
        enqueue.assert_not_called()

    def test_a_paused_data_source_is_skipped(self, enqueue):
        dashboard = _live_dashboard(self.factory)
        widget = self._widget(dashboard)
        widget.visualization.query_rel.data_source.pause("maintenance")
        live.check_in(dashboard.id, "tab")
        live.refresh_live_dashboards()
        enqueue.assert_not_called()

    def test_the_first_viewer_back_starts_it_at_once(self, enqueue):
        # Nobody was watching, so nothing was refreshed; the scheduler's next
        # tick is up to 10 seconds away, and the viewer is looking now.
        dashboard = _live_dashboard(self.factory)
        self._widget(dashboard)
        path = "/api/dashboards/{}/live/watch".format(dashboard.id)

        rv = self.make_request("post", path, data={"viewer": "tab"})
        self.assertEqual(rv.status_code, 200)
        enqueue.assert_called_once()

        # Somebody is watching now: the scheduler keeps it going, not check-ins.
        self.make_request("post", path, data={"viewer": "tab"})
        self.make_request("post", path, data={"viewer": "another tab"})
        enqueue.assert_called_once()

    def test_coming_back_to_a_hidden_tab_starts_it_at_once(self, enqueue):
        dashboard = _live_dashboard(self.factory)
        self._widget(dashboard)
        path = "/api/dashboards/{}/live/watch".format(dashboard.id)

        self.make_request("post", path, data={"viewer": "tab"})
        self.make_request("post", path, data={"viewer": "tab", "leaving": True})
        self.make_request("post", path, data={"viewer": "tab"})

        self.assertEqual(enqueue.call_count, 2)

    def test_a_check_in_says_what_time_the_server_makes_it(self, enqueue):
        dashboard = _live_dashboard(self.factory)
        rv = self.make_request("post", "/api/dashboards/{}/live/watch".format(dashboard.id), data={"viewer": "tab"})
        server_time = datetime.datetime.fromisoformat(rv.json["server_time"])
        self.assertLess(abs((utcnow() - server_time).total_seconds()), 5)

    def test_resume_starts_it_at_once_and_pause_does_not(self, enqueue):
        admin = self.factory.create_admin()
        dashboard = _live_dashboard(self.factory, user=admin)
        self._widget(dashboard)
        path = "/api/dashboards/{}/live".format(dashboard.id)

        self.make_request("post", path, data={"paused": True}, user=admin)
        enqueue.assert_not_called()

        self.make_request("post", path, data={"paused": False}, user=admin)
        enqueue.assert_called_once()


class TestGrantingLive(BaseTestCase):
    def test_an_admin_grants_and_takes_away(self):
        admin = self.factory.create_admin()
        group = self.factory.create_group(name="Ops")
        db.session.add(group)
        db.session.commit()
        path = "/api/groups/{}/permissions".format(group.id)

        rv = self.make_request("post", path, data={live.MANAGE_LIVE_PERMISSION: True}, user=admin)
        self.assertEqual(rv.status_code, 200)
        self.assertIn(live.MANAGE_LIVE_PERMISSION, rv.json["permissions"])

        rv = self.make_request("post", path, data={live.MANAGE_LIVE_PERMISSION: False}, user=admin)
        self.assertNotIn(live.MANAGE_LIVE_PERMISSION, rv.json["permissions"])

    def test_the_default_group_can_be_granted_it(self):
        admin = self.factory.create_admin()
        path = "/api/groups/{}/permissions".format(self.factory.default_group.id)
        rv = self.make_request("post", path, data={live.MANAGE_LIVE_PERMISSION: True}, user=admin)
        self.assertEqual(rv.status_code, 200)

    def test_nothing_else_can_be_granted_this_way(self):
        admin = self.factory.create_admin()
        path = "/api/groups/{}/permissions".format(self.factory.default_group.id)
        rv = self.make_request("post", path, data={"admin": True}, user=admin)
        self.assertEqual(rv.status_code, 400)
        self.assertNotIn("admin", models.Group.query.get(self.factory.default_group.id).permissions)

    def test_only_admins(self):
        path = "/api/groups/{}/permissions".format(self.factory.default_group.id)
        rv = self.make_request("post", path, data={live.MANAGE_LIVE_PERMISSION: True})
        self.assertEqual(rv.status_code, 403)


class TestRegularRefresh(BaseTestCase):
    def test_ordinary_dashboards_refresh_no_faster_than_every_ten_minutes(self):
        self.assertTrue(settings.DASHBOARD_REFRESH_INTERVALS)
        self.assertGreaterEqual(min(settings.DASHBOARD_REFRESH_INTERVALS), 600)
        self.assertEqual(settings.DASHBOARD_REFRESH_MINIMUM, 600)
