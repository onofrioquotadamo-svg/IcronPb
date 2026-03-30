"""
app_iscritti.py — FIDAL Ricerca Singolo Iscritto Gara
Avvio: streamlit run app_iscritti.py
"""

import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import base64
import urllib.parse
import os
import json

# Configurazione Pagina
st.set_page_config(page_title="PERSONAL BEST Iscritti", page_icon="🏅", layout="wide")

# ── Core helpers ─────────────────────────────────────────────────────────────

from fidal_utils import (
    decode_tessera, encode_tessera, hms_to_seconds, fetch_from_icron, extract_all_pbs,
    get_base64_logo, fetch_upcoming_icron_events
)

def show_pb_from_row(row):
    # Robust key access
    def g(k): return str(row.get(k.upper(), row.get(k.lower(), ''))).strip()
    
    tessera = g('TESSERA')
    athlete_url = f"https://www.fidal.it/atleta/x/{encode_tessera(tessera)}"
    nome = f"{g('COGNOME')} {g('NOME')}".strip()
    if not nome or nome == "-":
        nome = str(row.get('ATLETA_TEXT', 'Atleta Sconosciuto'))
    categoria, societa = g('CATEGORIA') or '-', g('SOCIETA') or '-'

    with st.spinner("Recupero PB da FIDAL..."):
        pbs, recent_bests, _ = extract_all_pbs(athlete_url, nome=nome, tessera=tessera)

    if not pbs:
        st.warning("Nessun primato registrato su FIDAL.")
        return

    df_pb = pd.DataFrame(pbs)
    df_pb['is_road'] = df_pb['Specialità'].apply(lambda x: any(k in str(x).lower() for k in ['strada', 'maratona', 'maratonina', 'km']))
    
    def get_sb(spec):
        match = recent_bests.get(spec) or next((v for k,v in recent_bests.items() if spec.lower() in k.lower()), None)
        return f"<div style='font-size:0.75rem;color:#ffab40;margin-top:3px'>⭐ SB: {match[1]} ({match[4]})</div>" if match else ""

    road_html = "".join([f"<div style='padding:10px 0;border-bottom:1px solid #333'><div style='font-size:0.95rem;color:#a5d6a7;font-weight:600'>{r['Specialità']}</div><div style='font-size:1.6rem;font-weight:900;color:white;line-height:1.1'>{r['Prestazione']}</div><div style='font-size:0.78rem;color:#90caf9'>📍 {r['Luogo']}</div><div style='font-size:0.7rem;color:#78909c'>{r['Data']}</div>{get_sb(r['Specialità'])}</div>" for _,r in df_pb[df_pb['is_road']].head(4).iterrows()])
    other_html = "".join([f"<div style='display:flex;justify-content:space-between;align-items:center;padding:5px 0;border-bottom:1px solid #2a2a2a'><span style='font-size:0.85rem;color:#bbb'>{r['Specialità']}</span><span style='font-size:1rem;font-weight:700;color:#eee'>{r['Prestazione']}</span></div>" for _,r in df_pb[~df_pb['is_road']].head(6).iterrows()])

    altri_label = f"<div style='margin-top:16px;font-size:0.7rem;color:#78909c;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px'>Altri Primati</div>" if other_html else ""

    st.markdown(f"""
<div style="background:linear-gradient(160deg,#1a1a2e 0%,#0f3460 100%);border-radius:12px;padding:16px 18px;border-left:5px solid #4caf50;font-family:sans-serif;">
  <div style="font-size:1.4rem;font-weight:900;color:white;margin-bottom:4px">{nome}</div>
  <div style="font-size:0.85rem;color:#81c784;margin-bottom:15px;background:rgba(0,0,0,0.2);display:inline-block;padding:2px 8px;border-radius:6px">🏅 {categoria} | 🏢 {societa}</div>
  <div style="font-size:0.75rem;color:#81c784;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px">🏃 Strada</div>
  {road_html if road_html else '<div style="color:#888;font-style:italic;font-size:0.85rem">Nessun record strada</div>'}
  {altri_label}{other_html}
</div>
""", unsafe_allow_html=True)

@st.dialog("🥇 Scheda Atleta", width="large")
def popup_atleta(row):
    show_pb_from_row(row)

# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    # Global 'WOW' Premium CSS
    st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;700;900&display=swap');
html, body, [data-testid="stAppViewContainer"] { font-family: 'Outfit', sans-serif !important; background: #0e1117; color: white; }

div[data-baseweb="input"] > div { background-color: white !important; }
div[data-baseweb="input"] input { color: black !important; }
div[data-baseweb="select"] > div { background-color: white !important; }
div[data-baseweb="select"] * { color: black !important; }

/* Control Buttons (Nav) */
div[data-testid="stButton"] > button {
    border-radius: 12px !important; font-weight: 700 !important; font-size: 0.9rem !important;
    background-color: #4caf50 !important; border: none !important;
    color: white !important; transition: all 0.2s ease !important;
}
div[data-testid="stButton"] > button:hover { background-color: #45a049 !important; transform: translateY(-2px); }
div[data-testid="stButton"] > button[kind="primary"] { background: #4caf50 !important; }

/* PREMIUM CARD STYLE */
.row-card {
    background: linear-gradient(90deg, rgba(255,255,255,0.02) 0%, rgba(255,255,255,0.04) 100%);
    border-radius: 16px; border: 1px solid rgba(255,255,255,0.03);
    padding: 16px 20px; position: relative; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    margin-bottom: 8px; z-index: 1;
}
.row-card:hover {
    background: linear-gradient(90deg, rgba(255,255,255,0.06) 0%, rgba(255,255,255,0.09) 100%);
    border-color: rgba(76,175,80,0.5); box-shadow: 0 8px 32px rgba(0,0,0,0.4); transform: translateY(-2px);
}
.bib-pill {
    background: #4caf50; color: #fff; padding: 4px 10px; border-radius: 8px; font-weight: 900;
    font-size: 0.85rem; display: inline-block; vertical-align: middle; box-shadow: 0 4px 8px rgba(76,175,80,0.2);
}
.athlete-name { font-size: 1.15rem; font-weight: 900; color: #fff; margin-left: 12px; display: inline-block; vertical-align: middle; }
.meta-line { font-size: 0.8rem; color: rgba(255,255,255,0.4); margin-top: 6px; font-weight: 500; }
.meta-line .cat-badge { color: #81d4fa; background: rgba(129,212,250,0.1); padding: 1px 6px; border-radius: 4px; margin-right: 6px; font-weight: 700; }
.chevron { position: absolute; right: 20px; top: 50%; transform: translateY(-50%); color: rgba(255,255,255,0.2); font-size: 1.2rem; }

/* Invisibility hack for cards - Level-1 DOM Strategy */
div[data-testid="stElementContainer"]:has(.row-card) {
    margin-bottom: -78px !important; /* Pull next container up */
}
div[data-testid="stElementContainer"]:has(.row-card) + div[data-testid="stElementContainer"]:has(div[data-testid="stButton"]) {
    position: relative;
    z-index: 10;
}
div[data-testid="stElementContainer"]:has(.row-card) + div[data-testid="stElementContainer"]:has(div[data-testid="stButton"]) button {
    height: 70px !important;
    background: transparent !important;
    color: transparent !important;
    border: none !important;
    box-shadow: none !important;
    margin: 0 !important;
    padding: 0 !important;
    width: 100% !important;
    opacity: 0 !important;
}
div[data-testid="stElementContainer"]:has(.row-card) + div[data-testid="stElementContainer"]:has(div[data-testid="stButton"]) button:hover {
    background: rgba(255,255,255,0.05) !important;
    opacity: 1 !important;
}
/* Visual state for the card underneath */
div[data-testid="stElementContainer"]:has(.row-card):hover .row-card {
    background: linear-gradient(90deg, rgba(255,255,255,0.06) 0%, rgba(255,255,255,0.09) 100%);
    border-color: rgba(76,175,80,0.5);
    transform: translateY(-2px);
}
</style>
""", unsafe_allow_html=True)

    # Gara Persistence (Startup loading from URL)
    if 'df_iscritti' not in st.session_state:
        g = st.query_params.get('gara')
        if g:
            with st.spinner("Caricamento gara dall'URL..."):
                try:
                    df = fetch_from_icron(g)
                    if not df.empty:
                        st.session_state['df_iscritti'] = df
                        st.session_state['icron_id_loaded'] = g
                    else: st.error(f"Gara {g} trovata ma senza iscritti.")
                except Exception as e: st.error(f"Errore: {e}")

    # Header con Logo
    logo_path = os.path.join(os.path.dirname(__file__), "icron_logo.png")
    b64_logo = get_base64_logo(logo_path)
    col_l, col_t = st.columns([1, 4])
    if b64_logo: col_l.markdown(f'<img src="data:image/png;base64,{b64_logo}" width="180">', unsafe_allow_html=True)
    col_t.markdown("<div style='display:flex;align-items:center;height:70px;margin-bottom:10px'><span style='font-size:2rem;font-weight:900;letter-spacing:-1.2px;color:white'>PERSONAL BEST <span style='color:#4caf50'>Iscritti</span></span></div>", unsafe_allow_html=True)

    # Popup Activation (Atleta popup from URL or Session State)
    atleta_id = st.query_params.get('atleta') or st.session_state.get('trigger_popup')
    if atleta_id and 'df_iscritti' in st.session_state:
        df_curr = st.session_state['df_iscritti']
        match = df_curr[df_curr['PETT'].astype(str) == str(atleta_id)]
        if match.empty: match = df_curr[df_curr['TESSERA'].astype(str) == str(atleta_id)]
        if not match.empty: 
            popup_atleta(match.iloc[0].to_dict())
            if 'trigger_popup' in st.session_state: del st.session_state['trigger_popup']
            st.query_params['atleta'] = "" 

    # Navigation
    if 'tab_section' not in st.session_state: st.session_state['tab_section'] = 'elenco'
    s_now = st.session_state['tab_section']
    n1, n2, n3 = st.columns(3)
    if n1.button("📁 Carica Gara", use_container_width=True, key="nav_carica", type="primary" if s_now=='carica' else "secondary"): st.session_state['tab_section'] = 'carica'; st.rerun()
    if n2.button("👥 Iscritti", use_container_width=True, key="nav_iscritti", type="primary" if s_now=='elenco' else "secondary"): st.session_state['tab_section'] = 'elenco'; st.rerun()
    if n3.button("🔍 Ricerca", use_container_width=True, key="nav_cerca", type="primary" if s_now=='cerca' else "secondary"): st.session_state['tab_section'] = 'cerca'; st.rerun()

    sect = st.session_state.get('tab_section')
    df_raw = st.session_state.get('df_iscritti')

    if sect == 'carica':
        st.markdown("<div style='margin-bottom:20px; padding:15px; background:rgba(255,255,255,0.05); border-radius:10px; border-left:4px solid #4caf50;'><h3 style='margin:0; font-size:1.1rem; color:#4caf50;'>Scegli tra le prossime gare o inserisci ID Gara</h3></div>", unsafe_allow_html=True)
        if 'upcoming_events' not in st.session_state: st.session_state['upcoming_events'] = fetch_upcoming_icron_events(10)
        up_events = st.session_state.get('upcoming_events', [])
        if up_events:
            event_options = ["-- Seleziona una gara --"] + [f"{e['dataEvento']} - {e['descrizione']}" for e in up_events]
            sel_event = st.selectbox("Seleziona Gara", options=event_options)
            if sel_event != event_options[0]:
                idx = event_options.index(sel_event) - 1
                st.session_state['input_id_gara'] = str(up_events[idx]['idGara'])
            id_g = st.text_input("ID Gara (ICRON)", key="input_id_gara")
        else:
            id_g = st.text_input("ID Gara (ICRON)", value=st.session_state.get('icron_id_loaded', ''), key="input_id_gara")

        if st.button("⬇️ Avvia Caricamento", use_container_width=True, type="primary") and id_g:
            try:
                df = fetch_from_icron(id_g)
                if not df.empty:
                    st.session_state['df_iscritti'] = df
                    st.session_state['icron_id_loaded'] = id_g
                    st.query_params['gara'] = id_g
                    st.session_state['tab_section'] = 'elenco'
                    st.rerun()
                else: st.error("Nessun iscritto trovato.")
            except Exception as e: st.error(f"Errore: {e}")

    elif sect == 'elenco':
        if df_raw is None or df_raw.empty: st.info("Nessuna gara caricata.")
        else:
            df_c = df_raw.copy().fillna('')
            df_c['P_VAL'] = pd.to_numeric(df_c['PETT'], errors='coerce').fillna(9999)
            df_c['ATLETA_TEXT'] = (df_c['COGNOME'] + ' ' + df_c['NOME']).str.strip()
            q = st.text_input("Filtra per nome o pettorale…", key="filter_input").strip().lower()
            df_s = df_c.sort_values('P_VAL').reset_index(drop=True)
            if q: df_s = df_s[df_s['ATLETA_TEXT'].str.lower().str.contains(q) | df_s['PETT'].str.contains(q)]
            
            st.caption(f"{len(df_s)} partecipanti")
            
            @st.fragment
            def list_fragment(df_to_show):
                for _, r in df_to_show.iterrows():
                    link_id = str(r['PETT'])
                    # Card Visuale
                    st.markdown(f'''
                    <div class="row-card card-trigger">
                        <span class="chevron">›</span>
                        <span class="bib-pill">#{link_id}</span>
                        <span class="athlete-name">{r['ATLETA_TEXT']}</span>
                        <div class="meta-line"><span class="cat-badge">{r['CATEGORIA'] or '-'}</span> {r['SOCIETA']} (Tess: {r['TESSERA']})</div>
                    </div>''', unsafe_allow_html=True)
                    
                    # Invisible Button Overlay
                    if st.button("", key=f"btn_{link_id}", use_container_width=True):
                        # Open the popup immediately from within the fragment
                        popup_atleta(r.to_dict())
            
            list_fragment(df_s)

    elif sect == 'cerca':
        if df_raw is None or df_raw.empty: st.info("Nessuna gara caricata.")
        else:
            with st.form("search_atleta_form", border=False):
                p = st.text_input("Numero del Pettorale o Tessera", key="search_pett_input")
                submit = st.form_submit_button("🔍 Mostra Scheda Atleta", use_container_width=True, type="primary")
                if submit and p:
                    p_val = p.strip()
                    m = df_raw[(df_raw['PETT'].astype(str) == p_val) | (df_raw['TESSERA'].astype(str) == p_val)]
                    if not m.empty:
                        link_id = str(m.iloc[0]['PETT'])
                        st.session_state['trigger_popup'] = link_id
                        st.query_params['atleta'] = link_id
                        st.rerun()
                    else: st.error("Atleta non trovato.")

if __name__ == "__main__":
    main()
