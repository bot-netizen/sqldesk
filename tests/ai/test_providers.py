from unittest import mock

import pytest
import requests

from sqldesk import ai


def _response(status=200, payload=None, text=""):
    response = mock.Mock()
    response.status_code = status
    response.text = text
    response.json.return_value = payload if payload is not None else {}
    return response


class TestTheTwoShapes:
    """
    Anthropic has its own request shape; everything else speaks OpenAI's. That
    is the whole of why there are three providers and two implementations.
    """

    def test_anthropic_sends_its_own_shape_and_reads_the_blocks_back(self):
        with mock.patch(
            "requests.post", return_value=_response(payload={"content": [{"type": "text", "text": "hi"}]})
        ) as post:
            answer = ai.get_provider("anthropic", model="claude-sonnet-5", api_key="k").complete("q", system="s")

        (url,) = post.call_args[0]
        assert url == "https://api.anthropic.com/v1/messages"
        assert post.call_args[1]["headers"]["x-api-key"] == "k"
        # The system prompt is its own field here, not a message.
        assert post.call_args[1]["json"]["system"] == "s"
        assert answer == "hi"

    def test_openai_sends_the_system_prompt_as_a_message(self):
        payload = {"choices": [{"message": {"content": " out "}}]}
        with mock.patch("requests.post", return_value=_response(payload=payload)) as post:
            answer = ai.get_provider("openai", model="gpt-4.1", api_key="k").complete("q", system="s")

        (url,) = post.call_args[0]
        assert url == "https://api.openai.com/v1/chat/completions"
        assert post.call_args[1]["json"]["messages"][0] == {"role": "system", "content": "s"}
        assert answer == "out"

    def test_a_local_model_is_openai_somewhere_else(self):
        payload = {"choices": [{"message": {"content": "local"}}]}
        with mock.patch("requests.post", return_value=_response(payload=payload)) as post:
            answer = ai.get_provider("local", model="llama3.1", base_url="http://ollama:11434/v1").complete("q")

        (url,) = post.call_args[0]
        # Not doubled: the base URL already ends in /v1, which is how most
        # people write it and the commonest way this fails.
        assert url == "http://ollama:11434/v1/chat/completions"
        assert "authorization" not in post.call_args[1]["headers"]
        assert answer == "local"

    def test_a_local_model_without_v1_gets_one(self):
        payload = {"choices": [{"message": {"content": "ok"}}]}
        with mock.patch("requests.post", return_value=_response(payload=payload)) as post:
            ai.get_provider("local", model="m", base_url="http://vllm:8000").complete("q")
        assert post.call_args[0][0] == "http://vllm:8000/v1/chat/completions"

    def test_a_local_model_needs_somewhere_to_be(self):
        with pytest.raises(ai.ModelError) as error:
            ai.get_provider("local", model="llama3.1")
        assert "base-url" in str(error.value)


class TestFailingReadably:
    """
    An operator reads these. A bare status code sends them to the wrong place,
    and a stack trace sends them nowhere.
    """

    def test_an_http_error_carries_the_reason_the_service_gave(self):
        bad_key = _response(status=401, text='{"error":{"message":"invalid x-api-key"}}')
        with mock.patch("requests.post", return_value=bad_key):
            with pytest.raises(ai.ModelError) as error:
                ai.get_provider("anthropic", api_key="wrong").complete("q")
        assert "401" in str(error.value)
        assert "invalid x-api-key" in str(error.value)

    def test_a_timeout_says_how_long_it_waited(self):
        with mock.patch("requests.post", side_effect=requests.exceptions.Timeout):
            with pytest.raises(ai.ModelError) as error:
                ai.get_provider("openai", api_key="k", timeout=5).complete("q")
        assert "5s" in str(error.value)

    def test_an_unreachable_endpoint_names_it(self):
        with mock.patch("requests.post", side_effect=requests.exceptions.ConnectionError("refused")):
            with pytest.raises(ai.ModelError) as error:
                ai.get_provider("local", model="m", base_url="http://nope:1234/v1").complete("q")
        assert "http://nope:1234/v1" in str(error.value)

    def test_html_instead_of_json_does_not_raise_a_parser_error(self):
        page = _response(payload=None, text="<html>gateway</html>")
        page.json.side_effect = ValueError
        with mock.patch("requests.post", return_value=page):
            with pytest.raises(ai.ModelError) as error:
                ai.get_provider("openai", api_key="k").complete("q")
        assert "not JSON" in str(error.value)

    def test_an_unknown_provider_lists_the_known_ones(self):
        with pytest.raises(ai.ModelError) as error:
            ai.get_provider("gemini")
        assert "anthropic" in str(error.value) and "local" in str(error.value)
