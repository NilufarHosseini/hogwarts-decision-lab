import pytest
from mystery.world import State, options, act, evaluate, conclude, ORACLE_COST, ORACLE_CHAIN
from mystery.engine import Session, run_baseline
from mystery.routers import HeuristicRouter, JEVNotConfigured

def test_dependencies_and_ground_truth_isolation():
    state=State()
    assert 'analyze_clock' not in {a.id for a in options(state)}
    assert 'responsible' not in state.public()
    act(state,'inspect_tower')
    assert 'analyze_clock' in {a.id for a in options(state)}

def test_banned_action():
    with pytest.raises(ValueError):act(State(),'inspect_chamber')

def test_oracle_chain_proves_feasible_short_path():
    state=State()
    for action in ORACLE_CHAIN: act(state,action)
    assert state.spent==ORACLE_COST==9
    conclude(state,'Professor Vale','defekter Zeitanker','Kristall stabilisieren')
    assert evaluate(state)['solved']

def test_unsupported_guess_fails():
    s=State()
    conclude(s,'Professor Vale','defekter Zeitanker','Kristall stabilisieren')
    assert not evaluate(s)['solved']

def test_correct_answer_requires_restoration():
    s=State()
    for a in ORACLE_CHAIN[:-1]:act(s,a)
    conclude(s,'Professor Vale','defekter Zeitanker','Kristall stabilisieren')
    assert not evaluate(s)['solved']

def test_baseline_not_oracle():
    report=run_baseline(0,16)
    assert report['backend']=='heuristic'
    assert not report['evaluation']['solved']
    assert report['total_tokens']==0

def test_router_is_not_omniscient():
    router=HeuristicRouter()
    assert router.choose(State()).selected=='interview_draco'

def test_jev_never_faked():
    with pytest.raises(RuntimeError):JEVNotConfigured().choose(State())

@pytest.mark.parametrize('seed',[0,1,2])
def test_all_scenarios(seed):
    s=State(seed=seed)
    for a in ORACLE_CHAIN:act(s,a)
    conclude(s,'Professor Vale','defekter Zeitanker','Kristall stabilisieren')
    assert evaluate(s)['solved']

def test_report_export():
    game=Session(router=HeuristicRouter());game.step();report=game.report()
    assert report['decisions'][0]['backend']=='heuristic'
    assert report['total_tokens']==0
