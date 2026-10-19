import json
from types import SimpleNamespace
from mystery.routers import AzureLLMRouter


def fake_router(mode, client):
    r = AzureLLMRouter.__new__(AzureLLMRouter)
    r.api_mode = mode
    r.client = client
    r.model = 'gpt-5.2-chat'
    r.input_rate = 0.0
    r.output_rate = 0.0
    r.name = 'azure:test'
    return r


def test_responses_api_parses_json_and_tokens():
    def create(**kwargs):
        assert 'temperature' not in kwargs
        assert kwargs['model'] == 'gpt-5.2-chat'
        return SimpleNamespace(output_text='{"action":"inspect_tower","reason":"time clue"}',
                               usage=SimpleNamespace(input_tokens=40, output_tokens=12))
    client = SimpleNamespace(responses=SimpleNamespace(create=create))
    payload, in_tokens, out_tokens = fake_router('responses', client)._request('system', {'hello': 'world'})
    assert payload['action'] == 'inspect_tower'
    assert (in_tokens, out_tokens) == (40, 12)


def test_chat_api_omits_temperature():
    def create(**kwargs):
        assert 'temperature' not in kwargs
        msg = SimpleNamespace(content='```json\n{"action":"inspect_tower"}\n```')
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)],
                               usage=SimpleNamespace(prompt_tokens=30, completion_tokens=10))
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    payload, in_tokens, out_tokens = fake_router('chat', client)._request('system', {})
    assert payload['action'] == 'inspect_tower'
    assert (in_tokens, out_tokens) == (30, 10)
