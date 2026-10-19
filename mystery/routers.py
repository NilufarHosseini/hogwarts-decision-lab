import json, os, re, time
from dataclasses import dataclass, asdict
from .world import State, options, finish_readiness

@dataclass
class Decision:
    selected: str
    backend: str
    latency_ms: float
    model: str = ''
    api_mode: str = ''
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    fallback: bool = False
    reason: str = ''
    error: str = ''

class HeuristicRouter:
    name = 'heuristic'
    # Deliberately uncomplicated but not omniscient: investigation of testimony first,
    # followed by physical evidence. No hidden-world knowledge used.
    PRIORITY = ['interview_draco','interview_hermione','interview_neville','inspect_scene',
                'interview_luna','inspect_greenhouse','search_library','audit_library_log',
                'inspect_tower','analyze_clock','decode_rune','inspect_chamber','stabilize_crystal']
    def choose(self, state: State) -> Decision:
        start=time.perf_counter()
        allowed={a.id for a in options(state)}
        selected=next((x for x in self.PRIORITY if x in allowed), None)
        if selected is None: raise ValueError('No available actions')
        return Decision(selected, self.name, (time.perf_counter()-start)*1000, reason='Static public-action priority')

class AzureLLMRouter:
    """Foundry router using Entra ID and either Responses or Chat Completions API."""
    name = 'azure'

    def __init__(self):
        from openai import OpenAI
        from azure.identity import DefaultAzureCredential, get_bearer_token_provider
        endpoint = os.getenv('AZURE_OPENAI_ENDPOINT', '').strip()
        self.model = os.getenv('AZURE_OPENAI_DEPLOYMENT', 'gpt-4.1').strip()
        self.api_mode = os.getenv('AZURE_OPENAI_API_MODE', 'responses').strip().lower()
        if self.api_mode not in ('responses', 'chat'):
            raise ValueError('AZURE_OPENAI_API_MODE must be responses or chat')
        if not endpoint:
            raise ValueError('AZURE_OPENAI_ENDPOINT must be set in .env')
        provider = get_bearer_token_provider(
            DefaultAzureCredential(),
            os.getenv('AZURE_OPENAI_TOKEN_SCOPE', 'https://ai.azure.com/.default')
        )
        self.client = OpenAI(base_url=endpoint.rstrip('/') + '/', api_key=provider,
                             timeout=60, max_retries=1)
        self.input_rate = float(os.getenv('AZURE_INPUT_USD_PER_1M', '0'))
        self.output_rate = float(os.getenv('AZURE_OUTPUT_USD_PER_1M', '0'))
        self.name = f'azure:{self.model}:{self.api_mode}'

    @staticmethod
    def parse_json(raw):
        raw = (raw or '').strip()
        raw = re.sub(r'^```(?:json)?\s*|\s*```$', '', raw, flags=re.I).strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            start, end = raw.find('{'), raw.rfind('}')
            if start < 0 or end <= start:
                raise ValueError(f'No JSON object in model answer: {raw[:300]!r}')
            return json.loads(raw[start:end + 1])

    def _request(self, system, payload):
        message = json.dumps(payload, ensure_ascii=False)
        if self.api_mode == 'responses':
            reply = self.client.responses.create(
                model=self.model,
                instructions=system,
                input=message,
            )
            raw = reply.output_text or ''
            usage = getattr(reply, 'usage', None)
            it = int(getattr(usage, 'input_tokens', 0) or 0)
            ot = int(getattr(usage, 'output_tokens', 0) or 0)
        else:
            # Do not set temperature: GPT-5 deployments may reject it.
            reply = self.client.chat.completions.create(
                model=self.model,
                messages=[{'role': 'system', 'content': system},
                          {'role': 'user', 'content': message}],
            )
            raw = reply.choices[0].message.content or ''
            usage = getattr(reply, 'usage', None)
            it = int(getattr(usage, 'prompt_tokens', 0) or 0)
            ot = int(getattr(usage, 'completion_tokens', 0) or 0)
        return self.parse_json(raw), it, ot

    def _metrics(self, it, ot):
        return {'input_tokens': it, 'output_tokens': ot, 'total_tokens': it + ot,
                'estimated_cost_usd': (it * self.input_rate + ot * self.output_rate) / 1_000_000}

    def choose(self, state: State) -> Decision:
        allowed = options(state)
        if not allowed:
            raise ValueError('No available actions')
        readiness = finish_readiness(state)
        context = {'budget': state.remaining, 'observations': state.evidence,
                   'completion_readiness': readiness,
                   'allowed_actions': [{'id': a.id, 'title': a.title, 'cost': a.cost,
                                        'description': a.description} for a in allowed] +
                                      ([{'id': 'FINISH_INVESTIGATION', 'title': 'Ermittlung abschliessen', 'cost': 0,
                                        'description': 'Beweise gesichert und Wiederherstellung ausgefuehrt.'}] if readiness['eligible'] else [])}
        start = time.perf_counter()
        try:
            parsed, it, ot = self._request(
                'You are a Hogwarts detective planning one investigation step. '
                'You do NOT know hidden truth. Goal: identify responsibility and cause, '
                'AND restore the crystal. Optimize evidence gained per cost. '
                'Choose exactly one ID from allowed_actions, INCLUDING FINISH_INVESTIGATION. '
                'If collected evidence sufficiently establishes the responsible person, cause, and the restoration has been performed, prefer FINISH_INVESTIGATION rather than gathering redundant evidence. '
                'If evidence is insufficient, investigate further. Never assume unknown facts. '
                'Respond with a JSON object: {"action":"allowed_id","reason":"brief reason"}.',
                context,
            )
            choice = parsed.get('action')
            if choice not in ({a['id'] for a in context['allowed_actions']}):
                raise ValueError(f'LLM returned invalid action: {choice!r}')
            m = self._metrics(it, ot)
            return Decision(choice, self.name, (time.perf_counter() - start) * 1000,
                            model=self.model, api_mode=self.api_mode, **m, reason=str(parsed.get('reason', '')))
        except Exception as exc:
            selected = HeuristicRouter().choose(state).selected
            return Decision(selected, self.name, (time.perf_counter() - start) * 1000,
                            model=self.model, api_mode=self.api_mode, fallback=True, reason='Heuristic fallback after Azure error',
                            error=f'{type(exc).__name__}: {exc}')

    def conclude_case(self, state: State):
        start = time.perf_counter()
        payload = {'observations': state.evidence,
                   'actions_taken': state.done,
                   'instructions': 'Conclude from observed evidence only; abstain when not proven.'}
        try:
            result, it, ot = self._request(
                'You are preparing a final structured Hogwarts investigation report. '
                'Return ONLY a JSON object with four keys: responsible, cause, restoration, reason. '
                'Choose responsible exactly from ["Professor Vale", "Draco", "Hermine", "Neville", "Luna", "Unbekannt"]. '
                'Choose cause exactly from ["defekter Zeitanker", "Diebstahl", "Sabotage", "Unbekannt"]. '
                'Choose restoration exactly from ["Kristall stabilisieren", "Zeitzauber wiederholen", "Uhr reparieren", "Unbekannt"]. '
                'Use Professor Vale only if observations connect his maintenance attempt to the failure. '
                'Use "Kristall stabilisieren" only if OBS_STABLE has been observed / stabilize_crystal was executed. '
                'If evidence is insufficient choose Unbekannt. The restoration describes the action performed, '
                'not a separate proof that all memories returned. Do not invent evidence.',
                payload,
            )
            usage = {'backend': self.name, 'model': self.model, 'api_mode': self.api_mode, 'latency_ms': (time.perf_counter() - start) * 1000,
                     **self._metrics(it, ot), 'fallback': False, 'error': '',
                     'reason': 'Final LLM conclusion', 'selected': 'FINAL'}
            return result, usage
        except Exception as exc:
            return {'responsible': 'Unbekannt', 'cause': 'Unbekannt',
                    'restoration': 'Unbekannt'}, {
                'backend': self.name, 'model': self.model, 'api_mode': self.api_mode, 'latency_ms': (time.perf_counter() - start) * 1000,
                **self._metrics(0, 0), 'fallback': True,
                'error': f'{type(exc).__name__}: {exc}',
                'reason': 'Failed final conclusion', 'selected': 'FINAL'}

class JEVNotConfigured:
    name='jev'
    def choose(self,state):
        raise RuntimeError('JEV remote MCP integration is NOT configured or verified. No simulated JEV decisions are used.')


class KevDecisionRouter:
    """Real Kev System One HTTP router. Never silently substitute heuristic choices."""
    name = 'kev'
    model = 'kev-0.8b'
    api_mode = 'systemone'

    def __init__(self, conclusion_router=None, http_client=None):
        import httpx
        self.url = os.getenv('KEV_BASE_URL', 'http://127.0.0.1:8009').rstrip('/') + '/v1/systemone'
        self.model = os.getenv('KEV_MODEL', 'kev-latest')
        self.name = f'kev:{self.model}:systemone'
        self.client = http_client or httpx.Client(timeout=float(os.getenv('KEV_TIMEOUT_SECONDS', '120')))
        self._conclusion_router = conclusion_router

    def choose(self, state: State) -> Decision:
        allowed = options(state)
        if not allowed:
            raise ValueError('No available actions')
        candidates = {a.id: f'{a.title}. {a.description} Cost: {a.cost} budget points.' for a in allowed}
        readiness = finish_readiness(state)
        if readiness['eligible']:
            candidates['FINISH_INVESTIGATION'] = (
                'Submit the final report now. Evidence of responsibility and cause is already collected; '
                'the restoration action was executed. Choose this if no more investigations are needed.'
            )
        # Keep exactly the same public facts as Azure routing; never leak Ground Truth.
        state_text = json.dumps({
            'goal': 'Identify who is responsible, the time-disturbance cause, and perform the restoration.',
            'remaining_budget': state.remaining,
            'observations': state.evidence,
            'completed_actions': state.done,
            'completion_readiness': readiness,
        }, ensure_ascii=False)
        payload = {
            'state': state_text,
            'model': self.model,
            'questions': {
                'next_action': {
                    'type': 'choice',
                    'instructions': ('Select the best NEXT action based only on observed evidence. '
                                     'Prioritize information gained per cost. Select only a listed option. '
                                     'When FINISH_INVESTIGATION is offered, the workflow prerequisites are met; '
                                     'prefer finishing over redundant investigation.'),
                    'criteria': candidates,
                }
            }
        }
        start = time.perf_counter()
        try:
            response = self.client.post(self.url, json=payload)
            response.raise_for_status()
            body = response.json()
            result = body['answers']['next_action']
            selected = result['choice']
            if selected not in candidates:
                raise ValueError(f'Kev returned invalid choice {selected!r}')
            usage = body.get('usage') or {}
            it = int(usage.get('input_tokens', 0) or 0)
            ot = int(usage.get('output_tokens', 0) or 0)
            confidence = result.get('confidence')
            probabilities = result.get('probabilities')
            reason = json.dumps({'confidence': confidence, 'probabilities': probabilities}, ensure_ascii=False)
            return Decision(
                selected=selected, backend=self.name, latency_ms=(time.perf_counter()-start)*1000,
                model=self.model, api_mode=self.api_mode, input_tokens=it, output_tokens=ot,
                total_tokens=it+ot, reason=reason,
            )
        except Exception as exc:
            raise RuntimeError(f'Kev routing failed ({self.url}): {type(exc).__name__}: {exc}') from exc

    def conclude_case(self, state: State):
        if self._conclusion_router is None:
            self._conclusion_router = AzureLLMRouter()
        return self._conclusion_router.conclude_case(state)
