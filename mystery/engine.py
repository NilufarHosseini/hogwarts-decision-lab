import json, time, uuid
from dataclasses import asdict
from pathlib import Path
from .world import State, SCENARIOS, options, act, conclude, evaluate, ORACLE_COST, finish_readiness
from .routers import HeuristicRouter

class Session:
    def __init__(self, seed=0, budget=16, router=None):
        if seed not in SCENARIOS: raise ValueError('Unknown scenario')
        self.state=State(seed=seed,budget=budget)
        self.router=router or HeuristicRouter()
        self.decisions=[]
        self.id=uuid.uuid4().hex[:10]
        self.started=time.perf_counter()

    def step(self):
        if not options(self.state): return None
        decision=self.router.choose(self.state)
        self.decisions.append(asdict(decision))
        if decision.selected == 'FINISH_INVESTIGATION':
            if not finish_readiness(self.state)['eligible']:
                raise ValueError('FINISH_INVESTIGATION is not eligible: required evidence or restoration missing')
            if not hasattr(self.router, 'conclude_case'):
                raise RuntimeError('FINISH_INVESTIGATION requires a conclusion-capable router')
            answer = self.ai_finish()
            return {'decision': asdict(decision),
                    'observation': {'text': 'Die KI hat die Ermittlung beendet und einen Abschlussbericht erstellt.',
                                    'action': 'FINISH_INVESTIGATION', 'cost': 0},
                    'conclusion': answer}
        observation=act(self.state,decision.selected)
        return {'decision':asdict(decision),'observation':observation}

    def manual(self,action_id): return act(self.state,action_id)

    def finish(self,responsible,cause,restoration):
        conclude(self.state,responsible,cause,restoration)
        return evaluate(self.state)

    def ai_finish(self):
        if not hasattr(self.router,'conclude_case'):
            raise RuntimeError('AI conclusion requires Azure backend')
        answer, usage=self.router.conclude_case(self.state)
        self.decisions.append(usage)
        self.finish(str(answer.get('responsible','Unbekannt')),
                    str(answer.get('cause','Unbekannt')),
                    str(answer.get('restoration','Unbekannt')))
        return answer

    def report(self):
        total_tokens=sum(x['total_tokens'] for x in self.decisions)
        return {'run_id':self.id,'scenario_id':self.state.seed,'backend':self.router.name,
                'model':getattr(self.router,'model',None),
                'api_mode':getattr(self.router,'api_mode',None),
                'state':asdict(self.state),'decisions':self.decisions,'evaluation':evaluate(self.state),
                'oracle_minimum_cost':ORACLE_COST,
                'regret_vs_omniscient_lower_bound':self.state.spent-ORACLE_COST if evaluate(self.state)['solved'] else None,
                'input_tokens':sum(x['input_tokens'] for x in self.decisions),
                'output_tokens':sum(x['output_tokens'] for x in self.decisions),
                'total_tokens':total_tokens,
                'route_latency_ms':sum(x['latency_ms'] for x in self.decisions),
                'estimated_routing_cost_usd':sum(x['estimated_cost_usd'] for x in self.decisions),
                'fallback_count':sum(x['fallback'] for x in self.decisions),
                'stop_reason': ('agent_chose_finish' if any(x.get('selected') == 'FINISH_INVESTIGATION' for x in self.decisions) else
                                'manual_or_external_finish' if self.state.finished else 'still_investigating'),
                'elapsed_ms':(time.perf_counter()-self.started)*1000}

def run_baseline(seed=0,budget=16):
    s=Session(seed,budget)
    while options(s.state): s.step()
    # Offline policy has no supernatural inference; only deduce from evidence if sufficient
    ids={e['id'] for e in s.state.evidence}
    if {'OBS_RUNE','OBS_CHAMBER','OBS_STABLE'} <= ids:
        s.finish('Professor Vale','defekter Zeitanker','Kristall stabilisieren')
    else: s.finish('Unbekannt','Unbekannt','Unbekannt')
    return s.report()

def save_report(report, directory='results'):
    dest=Path(directory);dest.mkdir(parents=True,exist_ok=True)
    output=dest / f"{report['run_id']}_{report['backend']}.json"
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return str(output)
