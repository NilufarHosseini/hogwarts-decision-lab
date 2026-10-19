import json, os
from html import escape
from pathlib import Path
import streamlit as st
from dotenv import load_dotenv
from mystery.world import STORY, ACTION_MAP, SCENARIOS, options, act, evaluate, ORACLE_COST, finish_readiness
from mystery.engine import Session, save_report, run_baseline
from mystery.routers import AzureLLMRouter, HeuristicRouter, KevDecisionRouter

load_dotenv()
st.set_page_config(page_title='The Vanishing Hour | Decision Lab', page_icon='🕰️', layout='wide', initial_sidebar_state='expanded')

# Visual language inspired by contemporary data-consulting websites: scarlet, charcoal,
# editorial type, spacious white cards. No third-party logos, fonts, images or tracking.
st.markdown("""
<style>
:root { --accent: #e52530; --accent-dark:#bf1926; --ink:#22252a; --muted:#6a727c; --line:#e7e9ed; --canvas:#f7f8fa; }
[data-testid="stAppViewContainer"] { background: var(--canvas); color:var(--ink); }
[data-testid="stHeader"] { background:rgba(247,248,250,.9); }
[data-testid="stSidebar"] { background:#22252a; }
[data-testid="stSidebar"] * { color:#f8f8fa !important; }
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p { color:#dfe1e5 !important; }
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p { color:#dfe1e5; }
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] { opacity:.78; }
[data-testid="stSidebar"] [data-testid="stSelectbox"] div[data-baseweb="select"] > div,
[data-testid="stSidebar"] [data-testid="stRadio"] { color:#25282d; }
.block-container { max-width:1360px; padding-top:2.4rem; padding-bottom:3.7rem; }
html, body, [class*="css"] { font-family: 'Segoe UI', 'Arial', sans-serif; }
h1,h2,h3 { color:var(--ink); letter-spacing:-.035em; font-weight:800 !important; }
h2 { font-size:1.7rem !important; margin-top:.65rem !important; }
h3 { font-size:1.28rem !important; }
[data-testid="stVerticalBlockBorderWrapper"] > div { border-color:var(--line); }
[data-testid="stMetric"] { background:white; border:1px solid var(--line); border-top:3px solid var(--accent); border-radius:10px; padding:17px 20px; box-shadow:0 5px 20px rgba(35,38,45,.035); }
[data-testid="stMetricLabel"] p { color:#65707a !important; font-size:.85rem; }
[data-testid="stMetricValue"] { color:var(--ink); font-weight:800; }
.stButton>button[kind="primary"], .stFormSubmitButton>button[kind="primary"] { background:var(--accent); border-color:var(--accent); color:white; font-weight:700; border-radius:7px; }
.stButton>button[kind="primary"]:hover, .stFormSubmitButton>button[kind="primary"]:hover { background:var(--accent-dark); border-color:var(--accent-dark); }
.stButton>button, .stDownloadButton>button, .stFormSubmitButton>button { border-radius:7px; font-weight:650; }
.stDownloadButton>button { border:1px solid var(--accent); color:var(--accent); }
[data-testid="stExpander"] { border:1px solid var(--line); border-radius:10px; background:#fff; }
[data-testid="stDataFrame"] { border-radius:9px; overflow:hidden; }
hr { border-color:var(--line) !important; }
.hero { background:#22252a; color:#fff; padding:38px 44px 34px; border-radius:13px; position:relative; overflow:hidden; margin-bottom:25px; }
.hero:before { content:""; position:absolute; right:-80px; top:-120px; width:450px; height:450px; border:2px solid rgba(255,255,255,.08); border-radius:50%; box-shadow:0 0 0 46px rgba(229,37,48,.07),0 0 0 96px rgba(255,255,255,.04); }
.hero:after { content:""; position:absolute; width:98px; height:6px; background:#ef2937; top:0; left:44px; }
.hero .eyebrow { font-size:.73rem; font-weight:750; text-transform:uppercase; letter-spacing:.19em; color:#ff6971; margin-bottom:17px; }
.hero h1 { position:relative; color:#fff !important; font-size:clamp(2rem,4vw,3.45rem); margin:0 0 15px; line-height:1.12; letter-spacing:-.045em; max-width:800px; }
.hero .intro { position:relative; color:#d1d4d9; font-size:1.02rem; max-width:760px; line-height:1.7; margin:0; }
.hero .label { margin-top:24px; display:inline-block; border:1px solid rgba(255,255,255,.23); padding:7px 11px; color:#fff; font-size:.72rem; font-weight:700; letter-spacing:.055em; border-radius:5px; }
.section-kicker { margin-top:12px; color:#e52530; text-transform:uppercase; letter-spacing:.14em; font-size:.72rem; font-weight:800; }
.section-head { margin:1px 0 17px; font-size:1.65rem; font-weight:850; letter-spacing:-.035em; color:#22252a; }
.info-strip { background:#fff; border-left:4px solid #e52530; padding:16px 19px; border-radius:0 9px 9px 0; margin:10px 0 20px; color:#424851; line-height:1.65; box-shadow:0 2px 12px rgba(20,20,20,.025); }
.side-head { color:#fff; border-bottom:1px solid rgba(255,255,255,.16); padding:0 0 14px; margin-bottom:13px; font-size:1.25rem; font-weight:800; }
.side-note { border-left:3px solid #e52530; padding-left:12px; margin-top:16px; color:#d0d3d9; font-size:.82rem; line-height:1.55; }
.mini-label { color:#6d7580; font-size:.82rem; }
@media (max-width: 700px) { .hero {padding:28px 25px;} .hero:after {left:25px;} .block-container {padding-top:1rem;} }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="hero">
  <div class="eyebrow">AI DECISION LAB <span style="color:#7f858c;margin:0 9px">/</span> INTERACTIVE MYSTERY</div>
  <h1>THE VANISHING<br><span style="color:#ff4553">HOUR.</span></h1>
  <p class="intro">Ein verschwundener Zeitabschnitt. Verborgene Hinweise. Eine Entscheidung nach der anderen.
  Teste, wie Mensch, generative KI und spezialisierte Decision Models denselben Fall lösen.</p>
  <div class="label">HOGWARTS CASE FILE 01 &nbsp; / &nbsp; EXPERIMENTAL WORKSPACE</div>
</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown('<div class="side-head">EXPERIMENT SETUP</div>', unsafe_allow_html=True)
    seed=st.selectbox('Mystery-Variante (gleiche Story)',list(SCENARIOS.keys()),format_func=lambda x:f'Variante {x+1}')
    budget=st.slider('Ermittlungsbudget',10,30,16)
    deployment=os.getenv('AZURE_OPENAI_DEPLOYMENT', 'nicht konfiguriert')
    st.caption(f'Azure Deployment: {deployment} · API: {os.getenv("AZURE_OPENAI_API_MODE", "responses")}')
    mode=st.radio('Ermittlungsmodus',['Mensch spielt','Rule-based Baseline','Azure LLM (Foundry)','Kev Decision Router + Azure Abschluss'],index=0)
    st.markdown('<div class="side-note">Kev nutzt den lokalen System-One-Server. JEV und Harness² sind nicht aktiviert.</div>', unsafe_allow_html=True)
    st.caption(f'Kev Server: {os.getenv("KEV_BASE_URL","http://127.0.0.1:8009")}')
    if st.button('Neues Spiel',use_container_width=True):
        st.session_state.pop('game',None);st.session_state.pop('game_key',None)
        st.rerun()

st.markdown('<div class="section-kicker">01 / DER FALL</div><div class="section-head">Eine Stunde ist verschwunden.</div>', unsafe_allow_html=True)
st.markdown(f'<div class="info-strip">{escape(STORY)}</div>', unsafe_allow_html=True)
with st.expander('Spielregeln und Ziel',expanded=True):
    st.markdown('''Du hast ein begrenztes Budget. Jede Untersuchung verbraucht Punkte. Manche Aktionen werden erst nach neuen Beweisen freigeschaltet.

**Ziel:** Finde heraus, *wer verantwortlich* ist, *warum die Stunde verschwand* und *wie die Stunde wiederhergestellt wird*. Ein Verdacht allein genügt nicht: Die Lösung braucht stützende Beweise und eine tatsächlich ausgeführte Wiederherstellung. Der verdeckte Evaluator kennt die Wahrheit. Der spielende Mensch und das LLM kennen sie nicht.

Du kannst zuerst selbst spielen und danach die KI mit identischem Startzustand antreten lassen. Es gibt mögliche Irrwege, aber auch einen kurzen Ermittlungsweg.''')

key=(seed,budget,mode,os.getenv('AZURE_OPENAI_DEPLOYMENT'),os.getenv('AZURE_OPENAI_API_MODE'),os.getenv('KEV_BASE_URL'),os.getenv('KEV_MODEL'))
if st.session_state.get('game_key') != key:
    # Delay initialization of Azure until first interaction so story/UI opens without auth.
    st.session_state.game=Session(seed,budget, HeuristicRouter())
    st.session_state.game_key=key
    st.session_state.azure_initialized=False
    st.session_state.latest=None

game=st.session_state.game
state=game.state
readiness=finish_readiness(state)
with st.expander('Abschlussvoraussetzungen (aus sichtbaren Beweisen)', expanded=False):
    for name, ok in readiness['checks'].items():
        st.write(('✅ ' if ok else '⬜ ') + name.replace('_',' '))
    st.caption('Diese Prüfungen verwenden ausschließlich beobachtete Beweise und ausgeführte Aktionen, nicht die geheime Lösung.')
st.divider()
st.markdown('<div class="section-kicker">02 / INVESTIGATION</div><div class="section-head">Ermittlung & Beweise</div>', unsafe_allow_html=True)
m1,m2,m3=st.columns(3)
m1.metric('Budget übrig',state.remaining)
m2.metric('Aktionen',len(state.done))
m3.metric('Beweise',len(state.evidence))

if not state.finished:
    allowed=options(state)
    if not allowed: st.warning('Keine Ermittlungsaktion mehr möglich. Du kannst jetzt eine Schlussfolgerung abgeben.')
    if mode=='Mensch spielt':
        if allowed:
            selected=st.selectbox('Welche Aktion möchtest du ausführen?',allowed,
                                  format_func=lambda a:f'{a.title} — {a.cost} Punkte')
            st.caption(selected.description)
            if st.button('Aktion ausführen',type='primary'):
                st.session_state.latest={'observation':game.manual(selected.id),'decision':{'backend':'human','selected':selected.id}}
                st.rerun()
    else:
        c1,c2=st.columns(2)
        with c1:
            if st.button('Nächster KI-Schritt',disabled=not allowed,type='primary'):
                if mode in ('Azure LLM (Foundry)', 'Kev Decision Router + Azure Abschluss') and not st.session_state.azure_initialized:
                    try:
                        game.router = KevDecisionRouter() if mode.startswith('Kev ') else AzureLLMRouter()
                        st.session_state.azure_initialized=True
                    except Exception as exc:
                        st.error(f'Router-Konfiguration fehlgeschlagen: {exc}');st.stop()
                try:
                    st.session_state.latest=game.step()
                except Exception as exc:
                    st.error(str(exc));st.stop()
                st.rerun()
        with c2:
            if st.button('Automatisch bis Abschluss oder Budgetende',disabled=not allowed):
                if mode in ('Azure LLM (Foundry)', 'Kev Decision Router + Azure Abschluss') and not st.session_state.azure_initialized:
                    try:
                        game.router = KevDecisionRouter() if mode.startswith('Kev ') else AzureLLMRouter()
                        st.session_state.azure_initialized=True
                    except Exception as exc:
                        st.error(f'Router-Konfiguration fehlgeschlagen: {exc}');st.stop()
                while options(game.state) and not game.state.finished:
                    try: st.session_state.latest=game.step()
                    except Exception as exc:
                        st.error(str(exc));break
                st.rerun()

if st.session_state.get('latest'):
    x=st.session_state.latest
    st.info(f"Letzter Schritt: {x['observation']['text']}")
    if x['decision'].get('fallback'):
        st.error('Achtung: LLM-Router ist auf Heuristik zurückgefallen.')
        st.code(x['decision'].get('error', 'Kein Fehlertext vorhanden'))

st.markdown('### Ermittlungsakte')
if state.evidence:
    for i,obs in enumerate(state.evidence,1):
        with st.expander(f"{i}. {ACTION_MAP[obs['action']].title} · −{obs['cost']} Budget",expanded=(i==len(state.evidence))):
            st.write(obs['text']);st.code(obs['id'])
else: st.info('Noch keine Beweise erhoben. Starte eine Untersuchung, um deine Ermittlungsakte aufzubauen.')

if not state.finished:
    st.divider()
    st.markdown('<div class="section-kicker">03 / FINAL REPORT</div><div class="section-head">Schlussfolgerung</div>', unsafe_allow_html=True)
    if mode in ('Azure LLM (Foundry)', 'Kev Decision Router + Azure Abschluss'):
        if st.button('Azure LLM soll den Fall abschließen'):
            if not st.session_state.azure_initialized:
                try: game.router=(KevDecisionRouter() if mode.startswith('Kev ') else AzureLLMRouter());st.session_state.azure_initialized=True
                except Exception as exc: st.error(str(exc));st.stop()
            answer=game.ai_finish();st.success('LLM-Schlussfolgerung gespeichert.');st.json(answer);st.rerun()
    else:
        with st.form('conclusion'):
            responsible=st.selectbox('Wer ist verantwortlich?', ['Unbekannt','Draco','Hermine','Neville','Luna','Professor Vale'])
            cause=st.selectbox('Was ist die Ursache?', ['Unbekannt','Diebstahl','Sabotage','defekter Zeitanker'])
            restoration=st.selectbox('Wie wird die Stunde wiederhergestellt?', ['Unbekannt','Kristall stabilisieren','Zeitzauber wiederholen','Uhr reparieren'])
            if st.form_submit_button('Ermittlungsbericht abgeben'):
                game.finish(responsible,cause,restoration);st.rerun()

st.divider();st.markdown('<div class="section-kicker">04 / PERFORMANCE</div><div class="section-head">Decision Analytics</div>', unsafe_allow_html=True)
report=game.report()
a,b,c,d=st.columns(4)
a.metric('Tokens (Routing + Abschluss)',report['total_tokens'])
b.metric('Routing + Abschluss-Zeit',f"{report['route_latency_ms']/1000:.2f} s")
c.metric('Aktionen',len(state.done))
d.metric('Fallbacks',report['fallback_count'])
if state.finished:
    ev=report['evaluation']
    st.success('Fall erfolgreich abgeschlossen!' if ev['solved'] else 'Fall nicht vollständig gelöst.')
    st.caption(f"Abschlussart: {report.get('stop_reason', 'unbekannt')}")
    st.json(ev)
    st.caption(f"Omniscient lower bound: {ORACLE_COST} Budgetpunkte. Nicht gleichzusetzen mit einer fairen Router-Policy.")
else:
    st.caption('Evaluiert wird nach dem Abschluss. Die Ground Truth wird während der Ermittlung nicht angezeigt.')

if report['decisions']:
    st.dataframe([{k:round(v,2) if isinstance(v,float) else v for k,v in x.items()} for x in report['decisions']],use_container_width=True)

st.caption(f'Router im Trace: {report.get("model") or "Offline"} · API: {report.get("api_mode") or "n/a"}. Bei Kev wird der Azure-Abschluss separat in decisions protokolliert.')
st.caption('Kosten in USD sind nur berechenbar, wenn die eigenen Azure-Preise pro 1 Mio Input-/Output-Tokens in .env eingetragen sind. Null bedeutet sonst: Preis unbekannt.')
st.metric('Geschätzte Routing-Kosten USD',f"{report['estimated_routing_cost_usd']:.6f}")
st.download_button('Vollständigen Trace als JSON herunterladen',
                   json.dumps(report,ensure_ascii=False,indent=2),file_name=f"{report['run_id']}_{report['backend']}.json",mime='application/json')
if st.button('Trace zusätzlich lokal speichern'):
    st.success(save_report(report))
with st.expander('Baseline über alle Varianten (offline)'):
    if st.button('Rule-based Baseline ausführen'):
        results=[run_baseline(i,budget=budget) for i in SCENARIOS]
        st.dataframe([{'scenario':r['scenario_id'],'solved':r['evaluation']['solved'],
                        'actions':r['evaluation']['actions'],'budget':r['evaluation']['budget_spent'],
                        'routing_tokens':r['total_tokens']} for r in results])
