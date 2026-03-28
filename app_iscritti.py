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

def decode_tessera(encoded_str):
    key = b"3gabbo83"
    try:
        code = encoded_str.split('/')[-1]
        code = urllib.parse.unquote(code)
        code += "=" * ((4 - len(code) % 4) % 4)
        dec_bytes = base64.b64decode(code)
        tessera = ""
        for i in range(len(dec_bytes)):
            tessera += chr((dec_bytes[i] - key[i % len(key)]) % 256)
        return tessera
    except Exception:
        return "Sconosciuta"

def encode_tessera(tessera_str):
    key = b"3gabbo83"
    tessera_str = str(tessera_str).strip()
    enc_bytes = bytearray()
    for i in range(len(tessera_str)):
        enc_bytes.append((ord(tessera_str[i]) + key[i % len(key)]) % 256)
    b64 = base64.b64encode(enc_bytes).decode('utf-8')
    return urllib.parse.quote(b64)

def hms_to_seconds(t_str):
    t_str = str(t_str).lower().replace('h', ':')
    parts = t_str.split(':')
    try:
        if len(parts) == 3:
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
        elif len(parts) == 2:
            return float(parts[0]) * 60 + float(parts[1])
        return float(parts[0])
    except Exception:
        return 999999

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_from_icron(id_gara):
    url = "https://www.icron.it/IcronNewGO/getIscrizioni"
    headers = {"Content-Type": "application/json;charset=UTF-8", "Referer": "https://www.icron.it/newgo/"}
    payload = {"idGara": str(id_gara).strip()}
    resp = requests.post(url, json=payload, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if data.get("esito") != "OK":
        raise ValueError(f"ICRON errore: {data.get('messaggio', 'sconosciuto')}")
    participants = data.get("elencoPartecipanti", [])
    if not participants: return pd.DataFrame()
    df = pd.DataFrame(participants)
    rename_map = {
        'pettorale': 'PETT', 'cognome': 'COGNOME', 'nome': 'NOME',
        'tessera': 'TESSERA', 'categoria': 'CATEGORIA', 'squadra': 'SOCIETA',
        'sesso': 'SESSO', 'dataNascita': 'DATA_NASCITA',
    }
    df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns}, inplace=True)
    return df

def extract_all_pbs(athlete_url):
    try:
        resp = requests.get(athlete_url, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        pb_data, recent_bests, perf_dates = [], {}, {}

        for table in soup.find_all('table'):
            headers = [th.get_text(strip=True).lower() for th in table.find_all('th')]
            if not headers and table.find('tr'):
                headers = [td.get_text(strip=True).lower() for td in table.find('tr').find_all('td')]

            first_h = headers[0].lower().strip() if headers else ''
            is_hist_table = first_h in ('anno', 'anno/data')
            is_pb_summary = (any('specialit' in h for h in headers) or any('prestazione' in h for h in headers)) and not is_hist_table

            if is_pb_summary:
                for tr in table.find_all('tr'):
                    cells = tr.find_all(['td', 'th'])
                    if not cells or len(cells) < 3: continue
                    specialty = cells[0].get_text(strip=True)
                    if not specialty or specialty.lower() in ('gara', 'specialità', 'specialita'): continue
                    pb_data.append({"Specialità": specialty, "Ambiente": cells[1].get_text(strip=True),
                                    "Prestazione": cells[2].get_text(strip=True), "Data": cells[4].get_text(strip=True), 
                                    "Luogo": cells[5].get_text(strip=True)})

            if is_hist_table:
                h_tag = table.find_previous(['h1', 'h2', 'h3', 'h4', 'h5'])
                spec = h_tag.get_text(strip=True) if h_tag else ""
                for tr in table.find_all('tr'):
                    cells = tr.find_all(['td', 'th'])
                    if len(cells) < 3: continue
                    year_cell = cells[0].get_text(strip=True)
                    if not (year_cell.isdigit() and len(year_cell) == 4): continue
                    date_part = cells[1].get_text(strip=True)
                    perf_cell = cells[6].get_text(strip=True) if len(cells) > 6 else cells[2].get_text(strip=True)
                    full_date = f"{date_part}/{year_cell}" if date_part else year_cell
                    perf_dates[(spec.lower(), perf_cell)] = full_date
                    if year_cell in ['2025', '2026']:
                        sec = hms_to_seconds(perf_cell)
                        if spec and sec < 999999:
                            if spec not in recent_bests or sec < recent_bests[spec][0]:
                                recent_bests[spec] = (sec, perf_cell, cells[-1].get_text(strip=True), year_cell, full_date)

        for pb in pb_data:
            key = (pb.get('Specialità', '').lower(), pb.get('Prestazione', ''))
            if key in perf_dates: pb['Data'] = perf_dates[key]
        return pb_data, recent_bests
    except Exception: return [], {}

def show_pb_from_row(row):
    tessera = str(row.get('TESSERA', '')).strip()
    athlete_url = f"https://www.fidal.it/atleta/x/{encode_tessera(tessera)}"
    nome = f"{row.get('COGNOME', '-')} {row.get('NOME', '')}".strip()
    categoria, societa = row.get('CATEGORIA', '-'), row.get('SOCIETA', '-')

    with st.spinner("Recupero PB da FIDAL..."):
        pbs, recent_bests = extract_all_pbs(athlete_url)

    if not pbs:
        st.warning("Nessun primato registrato su FIDAL.")
        return

    df_pb = pd.DataFrame(pbs)
    df_pb['is_road'] = df_pb['Specialità'].apply(lambda x: any(k in str(x).lower() for k in ['strada', 'maratona', 'maratonina', 'km']))
    
    def get_sb(spec):
        match = recent_bests.get(spec) or next((v for k,v in recent_bests.items() if spec.lower() in k.lower()), None)
        return f"<div style='font-size:0.75rem;color:#ffab40;margin-top:3px'>⭐ SB: {match[1]} ({match[4]})</div>" if match else ""

    road_rows = df_pb[df_pb['is_road']].head(4)
    other_rows = df_pb[~df_pb['is_road']].head(6)

    road_html = "".join([f"<div style='padding:10px 0;border-bottom:1px solid #333'><div style='font-size:0.95rem;color:#a5d6a7;font-weight:600'>{r['Specialità']}</div><div style='font-size:1.6rem;font-weight:900;color:white;line-height:1.1'>{r['Prestazione']}</div><div style='font-size:0.75rem;color:#90caf9'>📍 {r['Luogo']}</div><div style='font-size:0.7rem;color:#78909c'>{r['Data']}</div>{get_sb(r['Specialità'])}</div>" for _,r in road_rows.iterrows()])
    other_html = "".join([f"<div style='display:flex;justify-content:space-between;align-items:center;padding:5px 0;border-bottom:1px solid #2a2a2a'><span style='font-size:0.85rem;color:#bbb'>{r['Specialità']}</span><span style='font-size:1rem;font-weight:700;color:#eee'>{r['Prestazione']}</span></div>" for _,r in other_rows.iterrows()])

    altri_label = f"<div style='margin-top:16px;font-size:0.7rem;color:#78909c;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px'>Altri Primati</div>" if other_html else ""

    st.markdown(f"""
<div style="background:linear-gradient(160deg,#1a1a2e 0%,#0f3460 100%);border-radius:12px;padding:16px 18px;border-left:5px solid #4caf50;font-family:sans-serif;">
  <div style="font-size:1.4rem;font-weight:900;color:white;margin-bottom:4px">{nome}</div>
  <div style="font-size:0.85rem;color:#81c784;margin-bottom:12px">🏅 {categoria} | 🏢 {societa}</div>
  <div style="font-size:0.75rem;color:#81c784;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px">🏃 Strada / Maratona</div>
  {road_html if road_html else '<div style="color:#888;font-style:italic;font-size:0.85rem">Nessun record strada</div>'}
  {altri_label}{other_html}
</div>
""", unsafe_allow_html=True)

@st.dialog("🥇 Scheda Atleta", width="large")
def popup_atleta(row):
    show_pb_from_row(row)

# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    # Global 'WOW' Premium CSS (Unificato)
    st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;700;900&display=swap');
html, body, [data-testid="stAppViewContainer"] { font-family: 'Outfit', sans-serif !important; background: #0e1117; color: white; }

/* Control Buttons (Nav) */
div[data-testid="stButton"] > button {
    border-radius: 12px !important; font-weight: 700 !important; font-size: 0.9rem !important;
    background: linear-gradient(145deg, #1e2130, #161824) !important; border: 1px solid rgba(255,255,255,0.05) !important;
    color: #999 !important; transition: all 0.2s ease !important;
}
div[data-testid="stButton"] > button:hover { border-color: #4caf50 !important; color: #4caf50 !important; transform: translateY(-2px); }
div[data-testid="stButton"] > button[kind="primary"] { background: linear-gradient(135deg, #4caf50 0%, #3d8c40 100%) !important; color: white !important; }

/* PREMIUM CARD LINK STYLE */
.athlete-link { text-decoration: none !important; display: block !important; margin-bottom: 8px !important; }
.row-card {
    background: linear-gradient(90deg, rgba(255,255,255,0.02) 0%, rgba(255,255,255,0.04) 100%);
    border-radius: 16px; border: 1px solid rgba(255,255,255,0.03);
    padding: 16px 20px; position: relative; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}
.athlete-link:hover .row-card {
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
.chevron { position: absolute; right: 20px; top: 50%; transform: translateY(-50%); color: rgba(255,255,255,0.05); font-size: 1.2rem; }
.athlete-link:hover .chevron { color: #4caf50; }

/* Rimuove gap Streamlit tra blocchi markdown */
[data-testid="stVerticalBlock"] > div:has(div.row-card) { margin-top: 0 !important; margin-bottom: 0 !important; }
</style>
""", unsafe_allow_html=True)

    # Header
    st.markdown("<div style='display:flex;align-items:center;height:70px;margin-bottom:10px'><span style='font-size:2rem;font-weight:900;letter-spacing:-1.2px;color:white'>PERSONAL BEST <span style='color:#4caf50'>Iscritti</span></span></div>", unsafe_allow_html=True)

    # URL Persistence
    if 'df_iscritti' not in st.session_state:
        g = st.query_params.get('gara', '')
        if g:
            try:
                df = fetch_from_icron(g); df['PETT'] = df['PETT'].astype(str).str.strip().str.replace('.0', '', regex=False)
                st.session_state['df_iscritti'] = df; st.session_state['icron_id_loaded'] = g
            except: pass

    # Popup Activation
    atleta_id = st.query_params.get('atleta')
    if atleta_id and 'df_iscritti' in st.session_state:
        match = st.session_state['df_iscritti'].query(f'PETT == "{atleta_id}"')
        if not match.empty: popup_atleta(match.iloc[0].to_dict())

    # Nav
    if 'tab_section' not in st.session_state: st.session_state['tab_section'] = 'elenco'
    s_now = st.session_state['tab_section']
    n1, n2, n3 = st.columns(3)
    if n1.button("📁 Carica", use_container_width=True, type="primary" if s_now=='carica' else "secondary"): st.session_state['tab_section'] = 'carica'; st.rerun()
    if n2.button("👥 Iscritti", use_container_width=True, type="primary" if s_now=='elenco' else "secondary"): st.session_state['tab_section'] = 'elenco'; st.rerun()
    if n3.button("🔍 Cerca Atleta", use_container_width=True, type="primary" if s_now=='cerca' else "secondary"): st.session_state['tab_section'] = 'cerca'; st.rerun()
    # RIMOSSO DIVIDER qui per evitare spazio eccessivo

    sect = st.session_state['tab_section']
    df_raw = st.session_state.get('df_iscritti')

    if sect == 'carica':
        id_g = st.text_input("ID Gara", value=st.session_state.get('icron_id_loaded', ''))
        if st.button("⬇️ Carica", use_container_width=True, type="primary") and id_g:
            try:
                df = fetch_from_icron(id_g); df['PETT'] = df['PETT'].astype(str).str.strip().str.replace('.0', '', regex=False)
                st.session_state['df_iscritti']=df; st.session_state['icron_id_loaded']=id_g; st.query_params['gara']=id_g; st.session_state['tab_section']='elenco'; st.rerun()
            except Exception as e: st.error(f"Errore: {e}")

    elif sect == 'elenco':
        if df_raw is None or df_raw.empty: st.info("Nessuna gara caricata.")
        else:
            # Data Cleaning Totale
            df_c = df_raw.copy().fillna('')
            df_c['PETT'] = df_c['PETT'].astype(str).str.strip().str.replace('.0', '', regex=False)
            df_c['P_VAL'] = pd.to_numeric(df_c['PETT'], errors='coerce').fillna(9999)
            df_c['ATLETA_TEXT'] = (df_c['COGNOME'] + ' ' + df_c['NOME']).str.strip()
            
            # Filtro
            q = st.text_input("Filtra per nome o pettorale…").strip().lower()
            df_s = df_c.sort_values('P_VAL').reset_index(drop=True)
            if q: df_s = df_s[df_s['ATLETA_TEXT'].str.lower().str.contains(q) | df_s['PETT'].str.contains(q)]
            
            # Skip empty (nan) rows
            df_s = df_s[df_s['ATLETA_TEXT'] != '']
            
            st.caption(f"{len(df_s)} partecipanti")
            g_id = st.session_state.get('icron_id_loaded', '')

            # UNIQUE HTML BLOCK - Zero Gaps, One Style
            rows_html = "".join([f'''
            <a href="/?gara={g_id}&atleta={r['PETT']}" target="_self" class="athlete-link">
                <div class="row-card">
                    <span class="chevron">›</span>
                    <span class="bib-pill">#{r['PETT']}</span>
                    <span class="athlete-name">{r['ATLETA_TEXT']}</span>
                    <div class="meta-line"><span class="cat-badge">{r['CATEGORIA'] if r['CATEGORIA'] else '-'}</span> {r['SOCIETA']}</div>
                </div>
            </a>''' for _, r in df_s.iterrows()])
            
            if rows_html: st.markdown(rows_html, unsafe_allow_html=True)

    elif sect == 'cerca':
        if df_raw is None or df_raw.empty: st.info("Nessuna gara caricata.")
        else:
            p = st.text_input("Numero Pettorale")
            if st.button("🔍 Cerca Atleta", use_container_width=True, type="primary") or p:
                if p: st.query_params['atleta'] = p.strip(); st.rerun()

if __name__ == "__main__":
    main()
