from unittest import mock

from sqldesk import models
from sqldesk.ai import ModelError
from tests import BaseTestCase


class TestAIStatus(BaseTestCase):
    """
    Two flags, and who is allowed to see which.

    `enabled` is the operator's environment variable; `configured` is whether
    anyone has named a model. They fail differently and the remedy differs, so
    the page has to be able to tell them apart.
    """

    def _configure(self, **kwargs):
        args = {"org": self.factory.org, "type": "openai", "model": "gpt-4.1", "enabled": True}
        args.update(kwargs)
        provider = models.AIProvider(**args)
        models.db.session.add(provider)
        models.db.session.commit()
        return provider

    def test_nothing_configured_says_so_without_failing(self):
        response = self.make_request("get", "/api/ai/status", user=self.factory.user)
        self.assertEqual(200, response.status_code)
        self.assertFalse(response.json["configured"])
        self.assertFalse(response.json["available"])

    def test_configured_but_the_flag_is_off_is_not_available(self):
        # The distinction the page exists to draw: a model is named, but the
        # operator has not turned the feature on.
        self._configure()
        with mock.patch("sqldesk.settings.FEATURE_AI", False):
            response = self.make_request("get", "/api/ai/status", user=self.factory.create_admin())
        self.assertTrue(response.json["configured"])
        self.assertFalse(response.json["enabled"])
        self.assertFalse(response.json["available"])

    def test_both_on_is_available(self):
        self._configure()
        with mock.patch("sqldesk.settings.FEATURE_AI", True):
            response = self.make_request("get", "/api/ai/status", user=self.factory.create_admin())
        self.assertTrue(response.json["available"])

    def test_a_disabled_provider_is_not_configured(self):
        self._configure(enabled=False)
        with mock.patch("sqldesk.settings.FEATURE_AI", True):
            response = self.make_request("get", "/api/ai/status", user=self.factory.create_admin())
        self.assertFalse(response.json["available"])

    def test_an_ordinary_user_is_not_told_which_model_or_endpoint(self):
        # It names an internal endpoint and says whether a key exists. That is
        # not everyone's business, and the key itself is nobody's.
        self._configure(base_url="http://internal-ollama:11434/v1", options={"api_key": "sk-secret"})
        response = self.make_request("get", "/api/ai/status", user=self.factory.user)
        self.assertNotIn("provider", response.json)
        self.assertNotIn("sk-secret", str(response.json))
        self.assertNotIn("internal-ollama", str(response.json))

    def test_an_admin_sees_the_provider_but_never_the_key(self):
        self._configure(options={"api_key": "sk-secret"})
        response = self.make_request("get", "/api/ai/status", user=self.factory.create_admin())
        self.assertEqual("gpt-4.1", response.json["provider"]["model"])
        self.assertTrue(response.json["provider"]["has_api_key"])
        self.assertNotIn("sk-secret", str(response.json))

    def test_anonymous_callers_get_nothing(self):
        response = self.make_request("get", "/api/ai/status", user=False)
        self.assertIn(response.status_code, (302, 401, 404))


class TestAITest(BaseTestCase):
    def test_only_an_admin_may_spend_a_request(self):
        response = self.make_request("post", "/api/ai/test", user=self.factory.user)
        self.assertEqual(403, response.status_code)

    def test_with_nothing_configured_it_says_so_rather_than_erroring(self):
        response = self.make_request("post", "/api/ai/test", user=self.factory.create_admin())
        self.assertEqual(200, response.status_code)
        self.assertFalse(response.json["ok"])
        self.assertIn("manage ai configure", response.json["error"])

    def test_a_model_that_refuses_is_reported_not_raised(self):
        models.db.session.add(
            models.AIProvider(
                org=self.factory.org, type="openai", model="gpt-4.1", enabled=True, options={"api_key": "k"}
            )
        )
        models.db.session.commit()
        with mock.patch(
            "sqldesk.ai.OpenAIProvider.complete",
            side_effect=ModelError("401 bad key"),
        ):
            response = self.make_request("post", "/api/ai/test", user=self.factory.create_admin())
        self.assertEqual(200, response.status_code)
        self.assertFalse(response.json["ok"])
        self.assertIn("401 bad key", response.json["error"])


class TestCredentialsThatWillNotDecrypt(BaseTestCase):
    """
    An ordinary thing: somebody rotates SQLDESK_SECRET_KEY, or restores a
    database into an instance configured with a different one. The row is
    intact and useless.

    It used to take out the whole AI page with a 500 -- the column decrypts
    while the row loads, so an unreadable key takes out whatever asked for it,
    and the feature had no way to tell you what was wrong with it.
    """

    def _unreadable_row(self):
        provider = models.AIProvider(
            org=self.factory.org, type="openai", model="gpt-4.1", enabled=True, options={"api_key": "sk-x"}
        )
        models.db.session.add(provider)
        models.db.session.commit()
        # What a rotated secret leaves behind: ciphertext this instance's key
        # cannot open.
        models.db.session.execute(
            "UPDATE ai_providers SET encrypted_options = :junk WHERE id = :id",
            {"junk": b"gAAAAABnot-a-valid-token", "id": provider.id},
        )
        models.db.session.commit()
        models.db.session.expunge_all()

    def test_the_status_endpoint_says_so_instead_of_failing(self):
        self._unreadable_row()
        response = self.make_request("get", "/api/ai/status", user=self.factory.create_admin())
        self.assertEqual(200, response.status_code)
        self.assertIn("SQLDESK_SECRET_KEY", response.json["error"])
        self.assertFalse(response.json["configured"])

    def test_an_ordinary_user_still_gets_a_page(self):
        self._unreadable_row()
        response = self.make_request("get", "/api/ai/status", user=self.factory.user)
        self.assertEqual(200, response.status_code)
        self.assertNotIn("error", response.json, "the remedy is an admin's, and so is the detail")

    def test_the_test_button_reports_it_rather_than_erroring(self):
        self._unreadable_row()
        response = self.make_request("post", "/api/ai/test", user=self.factory.create_admin())
        self.assertEqual(200, response.status_code)
        self.assertFalse(response.json["ok"])
        self.assertIn("configure", response.json["error"])
