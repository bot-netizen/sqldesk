from sqldesk import models
from tests import BaseTestCase


class TestAIProviderStorage(BaseTestCase):
    """
    The key is the whole risk here. It is stored under the same secret and the
    same column type as a data source's credentials, and nothing that leaves
    the server is allowed to carry it.
    """

    def _make(self, **kwargs):
        args = {"org": self.factory.org, "type": "anthropic", "model": "claude-sonnet-5", "enabled": True}
        args.update(kwargs)
        provider = models.AIProvider(**args)
        models.db.session.add(provider)
        models.db.session.commit()
        return provider

    def test_the_key_is_not_readable_in_the_column(self):
        self._make(options={"api_key": "sk-secret-value"})
        stored = models.db.session.execute("SELECT encrypted_options FROM ai_providers").scalar()
        self.assertNotIn("sk-secret-value", stored)

    def test_the_key_comes_back_through_the_model(self):
        provider = self._make(options={"api_key": "sk-secret-value"})
        models.db.session.expire(provider)
        self.assertEqual("sk-secret-value", models.AIProvider.get_for_org(self.factory.org).api_key)

    def test_to_dict_says_whether_there_is_a_key_without_being_one(self):
        provider = self._make(options={"api_key": "sk-secret-value"})
        as_dict = provider.to_dict()
        self.assertTrue(as_dict["has_api_key"])
        self.assertNotIn("api_key", as_dict)
        self.assertNotIn("sk-secret-value", str(as_dict))

    def test_no_key_configured_reads_as_no_key(self):
        provider = self._make(type="local", base_url="http://ollama:11434/v1", options={})
        self.assertIsNone(provider.api_key)
        self.assertFalse(provider.to_dict()["has_api_key"])

    def test_nothing_configured_is_the_default(self):
        # Which is what makes the features off rather than on.
        self.assertIsNone(models.AIProvider.get_for_org(self.factory.org))

    def test_one_per_organization(self):
        self._make()
        second = self.factory.create_org(name="Other", slug="other")
        self._make(org=second, type="openai", model="gpt-4.1")
        self.assertEqual("anthropic", models.AIProvider.get_for_org(self.factory.org).type)
        self.assertEqual("openai", models.AIProvider.get_for_org(second).type)
