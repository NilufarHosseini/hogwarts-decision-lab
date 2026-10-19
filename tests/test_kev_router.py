import json
import pytest
from mystery.routers import KevDecisionRouter
from mystery.world import State, act

class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload=payload
        self.status_code=status
    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError('HTTP failure')
    def json(self):
        return self.payload

class FakeClient:
    def __init__(self, answer='inspect_scene'):
        self.answer=answer
        self.last=None
    def post(self,url,json):
        self.last=json
        return FakeResponse({'answers':{'next_action':{'choice':self.answer,'confidence':0.8,'probabilities':{self.answer:0.8}}},'usage':{'input_tokens':101,'output_tokens':7}})

def test_kev_real_protocol_payload(monkeypatch):
    c=FakeClient()
    r=KevDecisionRouter(http_client=c)
    d=r.choose(State(seed=0,budget=16))
    assert d.selected == 'inspect_scene'
    assert d.total_tokens == 108
    assert d.fallback is False
    assert c.last['questions']['next_action']['type'] == 'choice'
    assert 'FINISH_INVESTIGATION' not in c.last['questions']['next_action']['criteria']
    assert 'ground_truth' not in c.last['state']

def test_finish_choice(monkeypatch):
    c=FakeClient('FINISH_INVESTIGATION')
    r=KevDecisionRouter(http_client=c)
    state=State(seed=0,budget=16)
    for action in ('inspect_tower','analyze_clock','decode_rune','inspect_chamber','stabilize_crystal'):
        act(state, action)
    d=r.choose(state)
    assert d.selected == 'FINISH_INVESTIGATION'
    assert 'FINISH_INVESTIGATION' in c.last['questions']['next_action']['criteria']

def test_bad_choice_fails_loudly():
    r=KevDecisionRouter(http_client=FakeClient('NOT_ALLOWED'))
    with pytest.raises(RuntimeError, match='Kev routing failed'):
        r.choose(State(seed=0,budget=16))

def test_premature_finish_not_offered_to_kev():
    c=FakeClient('inspect_tower')
    r=KevDecisionRouter(http_client=c)
    r.choose(State(seed=0,budget=16))
    assert not json.loads(c.last['state'])['completion_readiness']['eligible']
