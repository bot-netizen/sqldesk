from flask_login import current_user
from funcy import project
from mock import patch

from sqldesk import models, settings
from tests import BaseTestCase, authenticated_user


class AuthenticationTestMixin:
    def test_returns_404_when_not_unauthenticated(self):
        for path in self.paths:
            rv = self.client.get(path)
            self.assertEqual(404, rv.status_code)

    def test_returns_content_when_authenticated(self):
        for path in self.paths:
            rv = self.make_request("get", path, is_json=False)
            self.assertEqual(200, rv.status_code)


class TestAuthentication(BaseTestCase):
    def test_responds_with_success_for_signed_in_user(self):
        with self.client as c:
            with c.session_transaction() as sess:
                sess["_user_id"] = self.factory.user.get_id()
            rv = self.client.get("/default/")

            self.assertEqual(200, rv.status_code)

    def test_redirects_for_nonsigned_in_user(self):
        rv = self.client.get("/default/")
        self.assertEqual(302, rv.status_code)

    def test_redirects_for_invalid_session_identifier(self):
        with self.client as c:
            with c.session_transaction() as sess:
                sess["_user_id"] = 100
            rv = self.client.get("/default/")

            self.assertEqual(302, rv.status_code)


class PingTest(BaseTestCase):
    def test_ping(self):
        rv = self.client.get("/ping")
        self.assertEqual(200, rv.status_code)
        self.assertEqual(b"PONG.", rv.data)


class IndexTest(BaseTestCase):
    def setUp(self):
        self.paths = [
            "/default/",
            "/default/dashboard/example",
            "/default/queries/1",
            "/default/admin/status",
        ]
        super(IndexTest, self).setUp()

    def test_redirect_to_login_when_not_authenticated(self):
        for path in self.paths:
            rv = self.client.get(path)
            self.assertEqual(302, rv.status_code)

    def test_returns_content_when_authenticated(self):
        for path in self.paths:
            rv = self.make_request("get", path, org=False, is_json=False)
            self.assertEqual(200, rv.status_code)


class StatusTest(BaseTestCase):
    def test_returns_data_for_super_admin(self):
        admin = self.factory.create_admin()
        models.db.session.commit()
        rv = self.make_request("get", "/status.json", org=False, user=admin, is_json=False)
        self.assertEqual(rv.status_code, 200)

    def test_returns_403_for_non_admin(self):
        rv = self.make_request("get", "/status.json", org=False, is_json=False)
        self.assertEqual(rv.status_code, 403)

    def test_redirects_non_authenticated_user(self):
        rv = self.client.get("/status.json")
        self.assertEqual(rv.status_code, 302)


class JobAPITest(BaseTestCase, AuthenticationTestMixin):
    def setUp(self):
        self.paths = []
        super(JobAPITest, self).setUp()


class TestLogin(BaseTestCase):
    def setUp(self):
        super(TestLogin, self).setUp()
        self.factory.org.set_setting("auth_password_login_enabled", True)

    def test_get_login_form(self):
        rv = self.client.get("/default/login")
        self.assertEqual(rv.status_code, 200)

    def test_get_login_form_remote_auth(self):
        """Make sure the remote auth link can be rendered correctly on the
        login page when the remote user login feature is enabled"""
        old_remote_user_enabled = settings.REMOTE_USER_LOGIN_ENABLED
        old_ldap_login_enabled = settings.LDAP_LOGIN_ENABLED
        try:
            settings.REMOTE_USER_LOGIN_ENABLED = True
            settings.LDAP_LOGIN_ENABLED = True
            rv = self.client.get("/default/login")
            self.assertEqual(rv.status_code, 200)
            self.assertIn("/{}/remote_user/login".format(self.factory.org.slug), rv.data.decode())
            self.assertIn("/{}/ldap/login".format(self.factory.org.slug), rv.data.decode())
        finally:
            settings.REMOTE_USER_LOGIN_ENABLED = old_remote_user_enabled
            settings.LDAP_LOGIN_ENABLED = old_ldap_login_enabled

    def test_submit_non_existing_user(self):
        with patch("sqldesk.handlers.authentication.login_user") as login_user_mock:
            rv = self.client.post("/default/login", data={"email": "arik", "password": "password"})
            self.assertEqual(rv.status_code, 200)
            self.assertFalse(login_user_mock.called)

    def test_submit_correct_user_and_password(self):
        user = self.factory.user
        user.hash_password("password")

        self.db.session.add(user)
        self.db.session.commit()

        with patch("sqldesk.handlers.authentication.login_user") as login_user_mock:
            rv = self.client.post("/default/login", data={"email": user.email, "password": "password"})
            self.assertEqual(rv.status_code, 302)
            login_user_mock.assert_called_with(user, remember=False)

    def test_submit_case_insensitive_user_and_password(self):
        user = self.factory.user
        user.hash_password("password")

        self.db.session.add(user)
        self.db.session.commit()

        with patch("sqldesk.handlers.authentication.login_user") as login_user_mock:
            rv = self.client.post(
                "/default/login",
                data={"email": user.email.upper(), "password": "password"},
            )
            self.assertEqual(rv.status_code, 302)
            login_user_mock.assert_called_with(user, remember=False)

    def test_submit_correct_user_and_password_and_remember_me(self):
        user = self.factory.user
        user.hash_password("password")

        self.db.session.add(user)
        self.db.session.commit()

        with patch("sqldesk.handlers.authentication.login_user") as login_user_mock:
            rv = self.client.post(
                "/default/login",
                data={"email": user.email, "password": "password", "remember": True},
            )
            self.assertEqual(rv.status_code, 302)
            login_user_mock.assert_called_with(user, remember=True)

    def test_submit_correct_user_and_password_with_next(self):
        user = self.factory.user
        user.hash_password("password")

        self.db.session.add(user)
        self.db.session.commit()

        with patch("sqldesk.handlers.authentication.login_user") as login_user_mock:
            rv = self.client.post(
                "/default/login?next=/test",
                data={"email": user.email, "password": "password"},
            )
            self.assertEqual(rv.status_code, 302)
            self.assertEqual(rv.location, "/test")
            login_user_mock.assert_called_with(user, remember=False)

    def test_submit_incorrect_user(self):
        with patch("sqldesk.handlers.authentication.login_user") as login_user_mock:
            rv = self.client.post("/default/login", data={"email": "non-existing", "password": "password"})
            self.assertEqual(rv.status_code, 200)
            self.assertFalse(login_user_mock.called)

    def test_submit_incorrect_password(self):
        user = self.factory.user
        user.hash_password("password")

        self.db.session.add(user)
        self.db.session.commit()

        with patch("sqldesk.handlers.authentication.login_user") as login_user_mock:
            rv = self.client.post(
                "/default/login",
                data={"email": user.email, "password": "badbadpassword"},
            )
            self.assertEqual(rv.status_code, 200)
            self.assertFalse(login_user_mock.called)

    def test_submit_empty_password(self):
        user = self.factory.user

        with patch("sqldesk.handlers.authentication.login_user") as login_user_mock:
            rv = self.client.post("/default/login", data={"email": user.email, "password": ""})
            self.assertEqual(rv.status_code, 200)
            self.assertFalse(login_user_mock.called)

    def test_user_already_loggedin(self):
        with authenticated_user(self.client), patch("sqldesk.handlers.authentication.login_user") as login_user_mock:
            rv = self.client.get("/default/login")
            self.assertEqual(rv.status_code, 302)
            self.assertFalse(login_user_mock.called)

    def test_correct_user_and_password_when_password_login_disabled(self):
        user = self.factory.user
        user.hash_password("password")

        self.db.session.add(user)
        self.db.session.commit()

        self.factory.org.set_setting("auth_password_login_enabled", False)

        with patch("sqldesk.handlers.authentication.login_user"):
            rv = self.client.post("/default/login", data={"email": user.email, "password": "password"})
            self.assertEqual(rv.status_code, 200)
            self.assertIn("Password login is not enabled for your organization", str(rv.data))


class TestLogout(BaseTestCase):
    def test_logout_when_not_loggedin(self):
        with self.app.test_client() as c:
            rv = c.get("/default/logout")
            self.assertEqual(rv.status_code, 302)
            self.assertFalse(current_user.is_authenticated)

    def test_logout_when_loggedin(self):
        with self.app.test_client() as c, authenticated_user(c, user=self.factory.user):
            rv = c.get("/default/")
            self.assertTrue(current_user.is_authenticated)
            rv = c.get("/default/logout")
            self.assertEqual(rv.status_code, 302)
            self.assertFalse(current_user.is_authenticated)


class TestQuerySnippet(BaseTestCase):
    def test_create(self):
        res = self.make_request(
            "post",
            "/api/query_snippets",
            data={"trigger": "x", "description": "y", "snippet": "z"},
            user=self.factory.user,
        )
        self.assertEqual(
            project(res.json, ["id", "trigger", "description", "snippet"]),
            {"id": 1, "trigger": "x", "description": "y", "snippet": "z"},
        )
        qs = models.QuerySnippet.query.one()
        self.assertEqual(qs.trigger, "x")
        self.assertEqual(qs.description, "y")
        self.assertEqual(qs.snippet, "z")

    def test_edit(self):
        qs = models.QuerySnippet(
            trigger="a",
            description="b",
            snippet="c",
            user=self.factory.user,
            org=self.factory.org,
        )
        models.db.session.add(qs)
        models.db.session.commit()
        res = self.make_request(
            "post",
            "/api/query_snippets/1",
            data={"trigger": "x", "description": "y", "snippet": "z"},
            user=self.factory.user,
        )
        self.assertEqual(
            project(res.json, ["id", "trigger", "description", "snippet"]),
            {"id": 1, "trigger": "x", "description": "y", "snippet": "z"},
        )
        self.assertEqual(qs.trigger, "x")
        self.assertEqual(qs.description, "y")
        self.assertEqual(qs.snippet, "z")

    def test_list(self):
        qs = models.QuerySnippet(
            trigger="x",
            description="y",
            snippet="z",
            user=self.factory.user,
            org=self.factory.org,
        )
        models.db.session.add(qs)
        models.db.session.commit()
        res = self.make_request("get", "/api/query_snippets", user=self.factory.user)
        self.assertEqual(res.status_code, 200)
        data = res.json
        self.assertEqual(len(data), 1)
        self.assertEqual(
            project(data[0], ["id", "trigger", "description", "snippet"]),
            {"id": 1, "trigger": "x", "description": "y", "snippet": "z"},
        )
        self.assertEqual(qs.trigger, "x")
        self.assertEqual(qs.description, "y")
        self.assertEqual(qs.snippet, "z")

    def test_delete(self):
        qs = models.QuerySnippet(
            trigger="a",
            description="b",
            snippet="c",
            user=self.factory.user,
            org=self.factory.org,
        )
        models.db.session.add(qs)
        models.db.session.commit()
        self.make_request("delete", "/api/query_snippets/1", user=self.factory.user)
        self.assertEqual(models.QuerySnippet.query.count(), 0)


class TestConfigBeforeSetup(BaseTestCase):
    """
    `/api/config` on an install that has not been through `/setup`.

    Nobody meets this on the path people take: a brand new install is sent to
    `/setup`, which is server-rendered and answers fine. But a browser holding
    the SPA from a previous install asks for this first, and it used to get a
    500 with a traceback -- which a client can do nothing with.

    Found by the 0.7.7 smoke test against a brand new database, and inherited
    rather than introduced: the line was byte-identical in 0.7.6.
    """

    def no_organization(self):
        # What `Organization.get_by_slug` really returns before setup. Patched
        # rather than deleting the fixture's org, so the rest of the row stays
        # consistent while the proxy resolves to None.
        return patch("sqldesk.authentication.org_resolving.Organization.get_by_slug", return_value=None)

    def test_it_answers_rather_than_raising(self):
        with self.no_organization():
            rv = self.client.get("/api/config")

        self.assertEqual(200, rv.status_code)

    def test_it_says_the_install_still_needs_setting_up(self):
        with self.no_organization():
            rv = self.client.get("/api/config")

        self.assertIsNone(rv.json["org_slug"])
        self.assertTrue(rv.json["setup_required"])

    def test_the_client_config_is_still_usable(self):
        # The browser boots from this, so an empty object would trade a 500 for
        # a blank page. Settings fall back to the install's defaults, which is
        # where an organization that has overridden nothing ends up anyway.
        with self.no_organization():
            config = self.client.get("/api/config").json["client_config"]

        self.assertIn("dateFormat", config)
        self.assertIn("pageSize", config)
        self.assertFalse(config["slackConfigured"])

    def test_an_install_that_is_set_up_is_unaffected(self):
        rv = self.client.get("/api/config")

        self.assertEqual(200, rv.status_code)
        self.assertEqual(self.factory.org.slug, rv.json["org_slug"])
        self.assertNotIn("setup_required", rv.json)
