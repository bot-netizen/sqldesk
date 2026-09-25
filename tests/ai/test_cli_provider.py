import subprocess
from unittest import mock

import pytest

from sqldesk import ai


def _finished(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args=["claude"], returncode=returncode, stdout=stdout, stderr=stderr)


class TestTheClaudeCommand:
    """
    No key anywhere: if somebody has signed Claude Code in with their
    subscription, the session is already on the machine. That is the appeal
    and the caveat both -- it is one person's session.
    """

    def test_it_needs_no_api_key(self):
        assert ai._PROVIDERS["cli"].needs_api_key is False

    def test_it_runs_the_command_and_returns_what_it_printed(self):
        with mock.patch("shutil.which", return_value="/usr/bin/claude"):
            with mock.patch("subprocess.run", return_value=_finished(stdout="  ready\n")) as run:
                answer = ai.get_provider("cli").complete("how many orders?")
        assert answer == "ready"
        argv = run.call_args[0][0]
        assert argv[:2] == ["claude", "-p"]
        assert argv[-1] == "how many orders?"

    def test_the_prompt_is_an_argument_not_a_shell_string(self):
        # A question containing a backtick is a question containing a backtick.
        with mock.patch("shutil.which", return_value="/usr/bin/claude"):
            with mock.patch("subprocess.run", return_value=_finished(stdout="ok")) as run:
                ai.get_provider("cli").complete("what is `rm -rf /` doing here")
        assert run.call_args[1].get("shell") is None
        assert run.call_args[0][0][-1] == "what is `rm -rf /` doing here"

    def test_a_model_is_passed_through_only_when_asked_for(self):
        with mock.patch("shutil.which", return_value="/usr/bin/claude"):
            with mock.patch("subprocess.run", return_value=_finished(stdout="ok")) as run:
                ai.get_provider("cli").complete("q")
            assert "--model" not in run.call_args[0][0], "the CLI's own setting is the right default"

            with mock.patch("subprocess.run", return_value=_finished(stdout="ok")) as run:
                ai.get_provider("cli", model="claude-sonnet-5").complete("q")
            argv = run.call_args[0][0]
            assert argv[argv.index("--model") + 1] == "claude-sonnet-5"

    def test_a_different_executable_can_be_named(self):
        with mock.patch("shutil.which", return_value="/opt/claude"):
            with mock.patch("subprocess.run", return_value=_finished(stdout="ok")) as run:
                ai.get_provider("cli", command="/opt/claude").complete("q")
        assert run.call_args[0][0][0] == "/opt/claude"


class TestWhenItCannotRun:
    def test_a_missing_command_says_where_it_has_to_be(self):
        with mock.patch("shutil.which", return_value=None):
            with pytest.raises(ai.ModelError) as error:
                ai.get_provider("cli").complete("q")
        assert "PATH" in str(error.value)

    def test_a_non_zero_exit_carries_what_the_cli_said(self):
        # Not signed in, unknown model, no network -- all on stderr.
        with mock.patch("shutil.which", return_value="/usr/bin/claude"):
            with mock.patch("subprocess.run", return_value=_finished(returncode=1, stderr="Not logged in")):
                with pytest.raises(ai.ModelError) as error:
                    ai.get_provider("cli").complete("q")
        assert "Not logged in" in str(error.value)

    def test_a_timeout_says_how_long_it_waited(self):
        with mock.patch("shutil.which", return_value="/usr/bin/claude"):
            with mock.patch("subprocess.run", side_effect=subprocess.TimeoutExpired("claude", 180)):
                with pytest.raises(ai.ModelError) as error:
                    ai.get_provider("cli", timeout=180).complete("q")
        assert "180s" in str(error.value)

    def test_silence_suggests_the_thing_to_try(self):
        with mock.patch("shutil.which", return_value="/usr/bin/claude"):
            with mock.patch("subprocess.run", return_value=_finished(stdout="   ")):
                with pytest.raises(ai.ModelError) as error:
                    ai.get_provider("cli").complete("q")
        assert "signed in" in str(error.value)


class TestBuildingOneFromARow:
    def test_a_cli_row_carries_its_command_not_a_key(self):
        row = mock.Mock(type="cli", model=None, base_url=None, api_key=None, options={"command": "/opt/claude"})
        provider = ai.provider_from(row)
        assert provider.command == "/opt/claude"

    def test_an_http_row_still_gets_its_key_and_endpoint(self):
        row = mock.Mock(type="local", model="llama3.1", base_url="http://ollama:11434/v1", api_key=None, options={})
        provider = ai.provider_from(row)
        assert provider.base_url == "http://ollama:11434/v1"
