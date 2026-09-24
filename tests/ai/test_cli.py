from unittest import mock

from click.testing import CliRunner

from sqldesk import ai, models
from sqldesk.cli import ai as ai_cli
from tests import BaseTestCase


class TestConfigureCommand(BaseTestCase):
    """
    Every one of these is a bug that driving the command found and the unit
    tests did not.
    """

    def _run(self, *args, **kwargs):
        with mock.patch.object(ai_cli, "_org", return_value=self.factory.org):
            return CliRunner().invoke(ai_cli.manager, list(args), **kwargs)

    def _provider(self):
        return models.AIProvider.get_for_org(self.factory.org)

    def test_a_local_model_needs_no_key(self):
        result = self._run("configure", "local", "--base-url", "http://ollama:11434/v1", "--model", "llama3.1")
        assert result.exit_code == 0, result.output
        self.assertEqual("local", self._provider().type)
        self.assertIsNone(self._provider().api_key)

    def test_a_hosted_provider_without_a_key_is_refused(self):
        result = self._run("configure", "openai", "--model", "gpt-4.1")
        self.assertEqual(1, result.exit_code)
        self.assertIn("needs a key", result.output)

    def test_a_key_can_come_from_stdin_rather_than_the_command_line(self):
        # On the command line it lands in shell history and in `ps`.
        result = self._run("configure", "openai", "--api-key-stdin", input="sk-from-stdin\n")
        assert result.exit_code == 0, result.output
        self.assertEqual("sk-from-stdin", self._provider().api_key)

    def test_changing_the_model_keeps_the_key(self):
        self._run("configure", "openai", "--api-key-stdin", input="sk-kept\n")
        result = self._run("configure", "openai", "--model", "gpt-4.1-mini")
        assert result.exit_code == 0, result.output
        self.assertEqual("gpt-4.1-mini", self._provider().model)
        self.assertEqual("sk-kept", self._provider().api_key)

    def test_switching_provider_does_not_carry_the_old_key_across(self):
        # A key for OpenAI is not a key for Anthropic; carrying it over turns a
        # missing key into a 401 somewhere else entirely.
        self._run("configure", "openai", "--api-key-stdin", input="sk-openai\n")
        result = self._run("configure", "anthropic", "--model", "claude-sonnet-5")
        self.assertEqual(1, result.exit_code)
        self.assertIn("needs a key", result.output)
        self.assertEqual("openai", self._provider().type, "a refused configure must change nothing")

    def test_the_key_is_never_printed(self):
        self._run("configure", "openai", "--api-key-stdin", input="sk-secret\n")
        for command in (["configure", "openai", "--model", "gpt-4.1"], ["status"]):
            result = self._run(*command)
            self.assertNotIn("sk-secret", result.output)
        self.assertIn("has_api_key: True", self._run("status").output)

    def test_status_says_plainly_when_nothing_is_configured(self):
        result = self._run("status")
        self.assertIn("No provider configured", result.output)

    def test_disable_keeps_the_configuration(self):
        self._run("configure", "local", "--base-url", "http://ollama:11434/v1")
        self._run("disable")
        self.assertFalse(self._provider().enabled)
        self.assertEqual("local", self._provider().type)

    def test_forget_removes_it(self):
        self._run("configure", "local", "--base-url", "http://ollama:11434/v1")
        self._run("forget")
        self.assertIsNone(self._provider())

    def test_test_reports_a_failure_instead_of_a_traceback(self):
        self._run("configure", "local", "--base-url", "http://ollama:11434/v1")
        with mock.patch.object(ai.LocalProvider, "complete", side_effect=ai.ModelError("no route to host")):
            result = self._run("test", "hello")
        self.assertEqual(1, result.exit_code)
        self.assertIn("no route to host", result.output)
        self.assertNotIn("Traceback", result.output)
