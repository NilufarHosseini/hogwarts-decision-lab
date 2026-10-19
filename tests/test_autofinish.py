from mystery.engine import Session
from mystery.routers import Decision, AzureLLMRouter
from mystery.world import ORACLE_CHAIN, finish_readiness

class FinishRouter:
    name='fake'
    model='test'
    api_mode='responses'
    def choose(self, state):
        return Decision('FINISH_INVESTIGATION','fake',1.0,model='test')
    def conclude_case(self,state):
        return ({'responsible':'Professor Vale','cause':'defekter Zeitanker',
                 'restoration':'Kristall stabilisieren'},
                {'selected':'FINAL','backend':'fake','latency_ms':2,'input_tokens':20,
                 'output_tokens':10,'total_tokens':30,'estimated_cost_usd':0,
                 'fallback':False,'reason':'test'})

def test_agent_can_finish_without_spending_budget():
    session=Session(router=FinishRouter())
    for action in ORACLE_CHAIN:
        session.manual(action)
    result=session.step()
    assert session.state.finished
    assert result['decision']['selected']=='FINISH_INVESTIGATION'
    assert session.report()['evaluation']['solved']
    assert session.report()['stop_reason']=='agent_chose_finish'
    assert session.report()['total_tokens']==30
    assert session.state.spent==9

def test_premature_finish_is_not_graded_as_success():
    session=Session(router=FinishRouter())
    import pytest
    with pytest.raises(ValueError, match='not eligible'):
        session.step()
    assert not session.state.finished
    assert session.state.spent==0

def test_llm_router_offers_finish_option():
    router=AzureLLMRouter.__new__(AzureLLMRouter)
    router.name='azure:test';router.model='test';router.api_mode='responses';router.input_rate=0;router.output_rate=0
    def mock_request(system,payload):
        assert any(a['id']=='FINISH_INVESTIGATION' for a in payload['allowed_actions'])
        assert 'FINISH_INVESTIGATION' in system
        return {'action':'FINISH_INVESTIGATION','reason':'sufficient evidence'},10,5
    router._request=mock_request
    session=Session(router=router)
    for action in ORACLE_CHAIN:
        session.manual(action)
    d=router.choose(session.state)
    assert d.selected=='FINISH_INVESTIGATION'
    assert not d.fallback

def test_finish_gate_requires_public_evidence_and_restoration():
    session=Session()
    assert not finish_readiness(session.state)['eligible']
    for action in ORACLE_CHAIN[:-1]:
        session.manual(action)
    assert not finish_readiness(session.state)['eligible']
    session.manual(ORACLE_CHAIN[-1])
    assert finish_readiness(session.state)['eligible']
