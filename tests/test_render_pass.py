from unittest import mock

from sqldesk import models, redis_connection, render_pass
from sqldesk.models import db
from sqldesk.permissions import has_access, not_view_only, view_only
from sqldesk.utils import json_dumps
from tests import BaseTestCase


class TestWhatAPassOpens(BaseTestCase):
    """
    A pass exists so that a picture of a dashboard does not require making the
    dashboard public. What it must never become is a credential somebody can
    point somewhere else.
    """

    def setUp(self):
        super().setUp()
        self.dashboard = self.factory.create_dashboard()
        self.other = self.factory.create_dashboard(name="Not this one")
        db.session.commit()

    def test_it_opens_the_object_it_was_issued_for(self):
        token = render_pass.issue(self.factory.user, self.dashboard)

        user = render_pass.load(token, self.factory.org)

        self.assertIsNotNone(user)
        self.assertEqual(self.dashboard.id, user.object.id)

    def test_it_cannot_be_pointed_at_another_object(self):
        # The object is inside the signature, so changing it is forgery.
        token = render_pass.issue(self.factory.user, self.dashboard)

        user = render_pass.load(token, self.factory.org)

        self.assertNotEqual(self.other.id, user.object.id)

    def test_a_forged_one_is_refused(self):
        token = render_pass.issue(self.factory.user, self.dashboard)

        self.assertIsNone(render_pass.load(token[:-4] + "aaaa", self.factory.org))

    def test_one_signed_with_another_key_is_refused(self):
        with mock.patch.object(render_pass.settings, "SECRET_KEY", "somebody-elses-key"):
            token = render_pass.issue(self.factory.user, self.dashboard)

        self.assertIsNone(render_pass.load(token, self.factory.org))

    def test_an_expired_one_is_refused(self):
        token = render_pass.issue(self.factory.user, self.dashboard)

        with mock.patch.object(render_pass, "TTL_SECONDS", -1):
            self.assertIsNone(render_pass.load(token, self.factory.org))

    def test_a_spent_one_is_refused(self):
        # What makes it single use: the signature is still good for the rest
        # of its five minutes, and this is not.
        token = render_pass.issue(self.factory.user, self.dashboard)
        self.assertIsNotNone(render_pass.load(token, self.factory.org))

        render_pass.withdraw(token)

        self.assertIsNone(render_pass.load(token, self.factory.org))

    def test_one_from_another_organization_is_refused(self):
        token = render_pass.issue(self.factory.user, self.dashboard)
        elsewhere = self.factory.create_org()

        self.assertIsNone(render_pass.load(token, elsewhere))

    def test_it_can_only_read(self):
        token = render_pass.issue(self.factory.user, self.dashboard)

        user = render_pass.load(token, self.factory.org)

        self.assertEqual(["view_query"], user.permissions)
        self.assertTrue(user.is_api_user())

    def test_a_dashboard_deleted_since_is_refused(self):
        token = render_pass.issue(self.factory.user, self.dashboard)
        db.session.delete(self.dashboard)
        db.session.commit()

        self.assertIsNone(render_pass.load(token, self.factory.org))

    def test_an_ordinary_api_key_is_not_mistaken_for_one(self):
        self.assertFalse(render_pass.looks_like_one(self.factory.user.api_key))
        self.assertIsNone(render_pass.load(self.factory.user.api_key, self.factory.org))

    def test_no_pass_is_issued_when_it_could_not_be_withdrawn(self):
        # Redis is how a pass is spent. One that cannot be spent is one that
        # stays good for five minutes wherever it ends up, so it is not worth
        # issuing at all.
        with mock.patch.object(redis_connection, "set", side_effect=Exception("Redis is down")):
            self.assertIsNone(render_pass.issue(self.factory.user, self.dashboard))

    def test_and_none_is_accepted_when_that_cannot_be_checked(self):
        token = render_pass.issue(self.factory.user, self.dashboard)

        with mock.patch.object(redis_connection, "exists", side_effect=Exception("Redis is down")):
            self.assertIsNone(render_pass.load(token, self.factory.org))


class TestThePagesAPassOpens(BaseTestCase):
    """
    The pass has to work through the routes the renderer actually opens, which
    are the ones a public link uses -- and it has to keep working where a
    public link would not.
    """

    def setUp(self):
        super().setUp()
        self.dashboard = self.factory.create_dashboard()
        db.session.commit()

    def _get(self, token):
        # user=False so the request carries the pass and nothing else --
        # exactly what the renderer sends.
        return self.make_request("get", "/api/dashboards/public/{}".format(token), user=False)

    def test_a_pass_fetches_its_dashboard(self):
        token = render_pass.issue(self.factory.user, self.dashboard)

        rv = self._get(token)

        self.assertEqual(200, rv.status_code)
        # The public serializer deliberately leaves the id out; the name is
        # what identifies it here.
        self.assertEqual(self.dashboard.name, rv.json["name"])

    def test_and_still_does_when_public_urls_are_switched_off(self):
        # A pass is not a public link. Before this an organization that turned
        # public URLs off could not have its own alerts drawn.
        self.factory.org.set_setting("disable_public_urls", True)
        db.session.commit()
        token = render_pass.issue(self.factory.user, self.dashboard)

        self.assertEqual(200, self._get(token).status_code)

    def test_but_a_real_public_link_still_does_not(self):
        # 404 rather than 400: with the setting on, a public token stops
        # resolving to a user at all, so the request never reaches the
        # handler. That is the 0.6 fix for tokens that kept working after the
        # setting was switched on, and the exception above must not undo it.
        key = models.ApiKey.create_for_object(self.dashboard, self.factory.user)
        self.factory.org.set_setting("disable_public_urls", True)
        db.session.commit()

        self.assertEqual(404, self._get(key.api_key).status_code)

    def test_a_spent_pass_opens_nothing(self):
        token = render_pass.issue(self.factory.user, self.dashboard)
        render_pass.withdraw(token)

        self.assertEqual(404, self._get(token).status_code)


class TestWhatAPassMaySee(BaseTestCase):
    """
    A dashboard's page fetches a result for every widget on it. Without access
    to those queries the picture is a grid of permission errors, which is what
    the first version of this produced and what rendering one on a real
    cluster showed -- the unit tests at the time were all green.
    """

    def setUp(self):
        super().setUp()
        self.dashboard = self.factory.create_dashboard()
        self.query = self.factory.create_query()
        visualization = self.factory.create_visualization(query_rel=self.query)
        self.factory.create_widget(dashboard=self.dashboard, visualization=visualization)

        self.elsewhere = self.factory.create_query()
        db.session.commit()

        self.pass_user = render_pass.load(render_pass.issue(self.factory.user, self.dashboard), self.factory.org)

    def _results(self, query, token):
        """The request a dashboard's page makes for each of its widgets."""
        # The org slug matters: only the org-scoped rules are registered in
        # the tests, so an unprefixed path falls through to the SPA catch-all
        # and answers 405 -- which is not 403, and quietly passes a test that
        # only checks for 403.
        return self.client.post(
            "/{}/api/queries/{}/results".format(self.factory.org.slug, query.id),
            data=json_dumps({"max_age": -1}),
            content_type="application/json",
            headers={"Authorization": "Key {}".format(token)},
        )

    def test_it_may_see_the_dashboard_it_names(self):
        self.assertTrue(has_access(self.dashboard, self.pass_user, view_only))

    def test_and_a_query_drawn_on_it(self):
        self.assertTrue(has_access(self.query, self.pass_user, view_only))

    def test_but_not_a_query_that_is_not(self):
        self.assertFalse(has_access(self.elsewhere, self.pass_user, view_only))

    def test_and_not_another_dashboard(self):
        other = self.factory.create_dashboard(name="Someone else's")
        db.session.commit()

        self.assertFalse(has_access(other, self.pass_user, view_only))

    def test_and_never_for_writing(self):
        # A pass exists to take a photograph.
        self.assertFalse(has_access(self.dashboard, self.pass_user, not_view_only))
        self.assertFalse(has_access(self.query, self.pass_user, not_view_only))

    def test_the_widget_results_endpoint_answers_a_pass(self):
        # The request the page actually makes, which was returning 403 for
        # every widget while every unit test passed.
        token = render_pass.issue(self.factory.user, self.dashboard)

        rv = self._results(self.query, token)

        # 200 rather than "not 403": a 405 from the SPA catch-all is also not
        # 403, and that is how this test passed while every widget in a real
        # render showed a permission error.
        self.assertEqual(200, rv.status_code)

    def test_but_not_for_a_query_on_another_dashboard(self):
        token = render_pass.issue(self.factory.user, self.dashboard)

        rv = self._results(self.elsewhere, token)

        self.assertEqual(403, rv.status_code)


class TestWhatAPassMayRead(BaseTestCase):
    """
    A pass has to be able to read the thing it was issued for.

    It was built with no groups at all, which is nearly right: it names one
    object and should open nothing else. But the embed page a query renders in
    fetches that query's *stored result*, and
    `/api/queries/<id>/results/<id>.json` checks access to the data source --
    which a user in no group never has. So the page fetched the query, was
    refused its result, and sat at "Loading..." until the renderer gave up.

    The alert still went out, because a failed render is meant to cost the
    picture and not the alert, so nothing anywhere said a word. Dashboards were
    unaffected: the public dashboard handler serves its widgets' data itself
    and never asks that endpoint.

    The fix is in `allows`, not in the pass's groups: `has_access` sends a
    render pass straight there and never reaches the group logic at all, so a
    pass carrying every group in the organisation would still have been
    refused.
    """

    def setUp(self):
        super().setUp()
        self.query = self.factory.create_query()
        db.session.commit()

    def test_a_pass_may_read_the_data_source_behind_its_object(self):
        token = render_pass.issue(self.factory.user, self.query)

        user = render_pass.load(token, self.factory.org)

        self.assertTrue(has_access(self.query.data_source, user, view_only))

    def test_and_still_may_not_write(self):
        token = render_pass.issue(self.factory.user, self.query)

        user = render_pass.load(token, self.factory.org)

        self.assertFalse(has_access(self.query.data_source, user, not_view_only))

    def test_and_reaches_no_further_than_its_own_object(self):
        # A second data source nobody granted it. The pass carries the groups
        # of the object it names and no others.
        elsewhere = self.factory.create_data_source(name="Somewhere else", group=self.factory.create_group())
        token = render_pass.issue(self.factory.user, self.query)

        user = render_pass.load(token, self.factory.org)

        self.assertFalse(has_access(elsewhere, user, view_only))

    def test_a_dashboard_pass_carries_what_a_dashboard_carries(self):
        # A dashboard has no data source of its own, so it has no groups; the
        # pass must still load rather than fail on the lookup.
        dashboard = self.factory.create_dashboard()
        db.session.commit()

        user = render_pass.load(render_pass.issue(self.factory.user, dashboard), self.factory.org)

        self.assertIsNotNone(user)
        self.assertEqual(dashboard.id, user.object.id)
