from dataclasses import dataclass, field, asdict
from typing import Optional

@dataclass(frozen=True)
class Action:
    id: str
    title: str
    cost: int
    requires: tuple[str, ...] = ()
    description: str = ""

ACTIONS = (
    Action('inspect_scene', 'Tatort untersuchen', 1, (), 'Sichere die ersten Spuren im Uhrensaal.'),
    Action('interview_draco', 'Draco befragen', 2, (), 'Pruefe Dracos Alibi und moegliches Motiv.'),
    Action('interview_hermione', 'Hermine befragen', 2, (), 'Pruefe ihre Bibliotheksaktivitaeten.'),
    Action('interview_neville', 'Neville befragen', 2, (), 'Pruefe die unbekannte Substanz.'),
    Action('interview_luna', 'Luna befragen', 1, (), 'Frage nach ihrer Beobachtung der Uhr.'),
    Action('inspect_tower', 'Astronomieturm untersuchen', 2, (), 'Untersuche die rueckwaerts laufende Uhr.'),
    Action('search_library', 'Zeitmagie-Archive durchsuchen', 3, (), 'Suche historische Zeitzauber.'),
    Action('inspect_greenhouse', 'Gewächshaus untersuchen', 2, (), 'Pruefe Nevilles Substanz.'),
    Action('analyze_clock', 'Uhrensignatur analysieren', 2, ('inspect_tower',), 'Analysiere die magische Resonanz.'),
    Action('audit_library_log', 'Bibliothekszugriffe pruefen', 2, ('search_library',), 'Analysiere die Ausleihprotokolle.'),
    Action('decode_rune', 'Zeit-Runen entziffern', 2, ('analyze_clock',), 'Entschluessle das Runenmuster.'),
    Action('inspect_chamber', 'Chronos-Kammer oeffnen', 2, ('decode_rune',), 'Pruefe verborgenen Mechanismus.'),
    Action('stabilize_crystal', 'Kristall stabilisieren', 1, ('inspect_chamber',), 'Stabilisiere den Kristall.'),
)
ACTION_MAP = {a.id: a for a in ACTIONS}

@dataclass
class State:
    seed: int = 0
    budget: int = 16
    done: list[str] = field(default_factory=list)
    evidence: list[dict] = field(default_factory=list)
    spent: int = 0
    finished: bool = False
    conclusion: Optional[dict] = None

    @property
    def remaining(self): return self.budget - self.spent

    def public(self):
        return {'scenario_id': self.seed, 'budget_remaining': self.remaining,
                'actions_taken': self.done, 'observations': self.evidence}

STORY = '''Um Mitternacht fehlt Hogwarts eine ganze Stunde. Der Chronos-Kristall ist verschwunden. Draco hatte Streit mit dem Waechter, Hermine recherchierte Zeitmagie, Neville trug eine unbekannte Substanz und Luna sah die Turmuhr rueckwaerts laufen. Ermittele Ursache, verantwortliche Person und wie die Stunde wiederhergestellt werden kann. Es gibt echte Spuren, Irrwege und begrenzte Ermittlungszeit.'''

# Three preauthored variants within ONE mystery. All hidden facts remain on the tool/evaluator side.
SCENARIOS = {
  0: {'responsible':'Professor Vale', 'cause':'defekter Zeitanker', 'restoration':'Kristall stabilisieren', 'shift':'blau', 'archive':'alte Uhrwerksskizze'},
  1: {'responsible':'Professor Vale', 'cause':'defekter Zeitanker', 'restoration':'Kristall stabilisieren', 'shift':'silbern', 'archive':'unvollstaendiger Laborbericht'},
  2: {'responsible':'Professor Vale', 'cause':'defekter Zeitanker', 'restoration':'Kristall stabilisieren', 'shift':'violett', 'archive':'veraltete Runenliste'},
}

EVENTS = {
 'inspect_scene': ('OBS_SCENE', 'Die Vitrine ist unversehrt. Eine mechanische, nicht-personengebundene Resonanz fuehrt zum Astronomieturm.'),
 'interview_draco': ('OBS_DRACO', 'Draco hatte Streit, aber der belegte Zeitpunkt seines Weggangs liegt vor dem Vorfall. Kein direkter Nachweis.'),
 'interview_hermione': ('OBS_HERMIONE', 'Hermine hat Zeitmagie-Buecher genutzt, um Pruefungsfragen vorzubereiten. Die Aussage ist nicht unabhaengig bestaetigt.'),
 'interview_neville': ('OBS_NEVILLE', 'Die Substanz auf Nevilles Kleidung stammt wahrscheinlich aus dem Gewaechshaus.'),
 'interview_luna': ('OBS_LUNA', 'Luna beobachtete die Turmuhr rueckwaerts. Das deutet auf eine technische Zeitstoerung hin.'),
 'inspect_tower': ('OBS_TOWER', 'Die Uhr hat einen defekten Zeitanker; die Signatur ist nicht eindeutig einer Person zuzuordnen.'),
 'search_library': ('OBS_LIBRARY', 'Zahlreiche alte Buecher zeigen, dass Zeitanker-Stoerungen Erinnerungen verschieben koennen. Kein Schuldnachweis.'),
 'inspect_greenhouse': ('OBS_GREENHOUSE', 'Nevilles Substanz ist ein harmloses Pflanzenschutzmittel. Diese Spur ist entkraeftet.'),
 'analyze_clock': ('OBS_CLOCK', 'Messung: Das Signal stammt aus dem Uhrwerk und verweist auf einen verborgenen Runencode, nicht auf einen Schuelerzauber.'),
 'audit_library_log': ('OBS_LOG', 'Das Log zeigt mehrere Bibliotheksbesuche, aber keine Verbindung zum Diebstahl.'),
 'decode_rune': ('OBS_RUNE', 'Die Runen nennen die Chronos-Kammer unter dem Turm. Ein Wartungssiegel von Professor Vale ist erkennbar.'),
 'inspect_chamber': ('OBS_CHAMBER', 'In der Kammer liegt der Kristall im Zeitanker. Professor Vale versuchte eine Wartung; ein defekter Mechanismus loeste die Stunde aus. Kein Diebstahl.'),
 'stabilize_crystal': ('OBS_STABLE', 'Der Kristall ist stabilisiert, die fehlende Stunde kann wiederhergestellt werden.'),
}

def finish_readiness(state: State) -> dict:
    """Public-evidence-only completion gate; does not inspect SCENARIOS or hidden truth.

    Requires an attributable incident, an examined cause and an executed restoration.
    This is a *workflow eligibility* check, not a claim that the final report is true.
    """
    evidence_ids = {item['id'] for item in state.evidence}
    checks = {
        'responsibility_evidence': 'OBS_RUNE' in evidence_ids and 'OBS_CHAMBER' in evidence_ids,
        'cause_evidence': 'OBS_TOWER' in evidence_ids and 'OBS_CLOCK' in evidence_ids and 'OBS_CHAMBER' in evidence_ids,
        'restoration_executed': 'stabilize_crystal' in state.done and 'OBS_STABLE' in evidence_ids,
    }
    return {'eligible': all(checks.values()), 'checks': checks,
            'missing': [name for name, satisfied in checks.items() if not satisfied]}

def options(state: State) -> list[Action]:
    return [a for a in ACTIONS if a.id not in state.done and
            all(req in state.done for req in a.requires) and a.cost <= state.remaining] if not state.finished else []

def act(state: State, action_id: str) -> dict:
    permitted = {a.id:a for a in options(state)}
    if action_id not in permitted:
        raise ValueError(f'Unzulaessige Aktion: {action_id}')
    a = permitted[action_id]
    clue_id, text = EVENTS[action_id]
    state.done.append(action_id)
    state.spent += a.cost
    obs = {'id':clue_id,'action':action_id,'text':text,'cost':a.cost}
    state.evidence.append(obs)
    return obs

def conclude(state: State, responsible: str, cause: str, restoration: str) -> dict:
    state.finished=True
    state.conclusion={'responsible':responsible,'cause':cause,'restoration':restoration}
    return state.conclusion

def evaluate(state: State) -> dict:
    truth = SCENARIOS[state.seed]
    c = state.conclusion or {}
    correctly_identified = c.get('responsible','').strip().lower() == truth['responsible'].lower()
    correct_cause = c.get('cause','').strip().lower() == truth['cause'].lower()
    restored = 'stabilize_crystal' in state.done and c.get('restoration','').strip().lower() == truth['restoration'].lower()
    supported = {'OBS_RUNE','OBS_CHAMBER'}.issubset({e['id'] for e in state.evidence})
    solved = correctly_identified and correct_cause and restored and supported
    return {'solved':solved,'responsible_correct':correctly_identified,'cause_correct':correct_cause,
            'restored':restored,'evidence_supported':supported, 'actions':len(state.done),
            'budget_spent':state.spent,'remaining':state.remaining}

# Shortest possible completion measured over an omniscient full-state graph; a lower bound,
# NOT a competing fair policy. Needed action chain totals 1? Starting from tower = 2+2+2+2+1 = 9.
ORACLE_CHAIN = ('inspect_tower','analyze_clock','decode_rune','inspect_chamber','stabilize_crystal')
ORACLE_COST = sum(ACTION_MAP[a].cost for a in ORACLE_CHAIN)
