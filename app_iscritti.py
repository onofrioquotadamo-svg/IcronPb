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
    categoria, societa, pett = row.get('CATEGORIA', '-'), row.get('SOCIETA', '-'), row.get('PETT', '-')

    with st.spinner("Recupero PB da FIDAL..."):
        pbs, recent_bests = extract_all_pbs(athlete_url)

    if not pbs:
        st.warning("Nessun primato registrato su FIDAL.")
        return

    df_pb = pd.DataFrame(pbs)
    df_pb['is_road'] = df_pb['Specialità'].apply(lambda x: any(k in str(x).lower() for k in ['strada', 'maratona', 'maratonina', 'km']))
    
    def get_sb(spec):
        match = recent_bests.get(spec) or next((v for k,v in recent_bests.items() if spec.lower() in k.lower()), None)
        return f"<div style='font-size:0.78rem;color:#ffab40;margin-top:3px'>⭐ SB: {match[1]} ({match[4]})</div>" if match else ""

    road_html = "".join([f"<div style='padding:10px 0;border-bottom:1px solid #333'><div style='font-size:0.95rem;color:#a5d6a7;font-weight:600'>{r['Specialità']}</div><div style='font-size:1.6rem;font-weight:900;color:white;line-height:1.1'>{r['Prestazione']}</div><div style='font-size:0.78rem;color:#90caf9'>📍 {r['Luogo']}</div><div style='font-size:0.72rem;color:#78909c'>{r['Data']}</div>{get_sb(r['Specialità'])}</div>" for _,r in df_pb[df_pb['is_road']].head(4).iterrows()])
    other_html = "".join([f"<div style='display:flex;justify-content:space-between;align-items:center;padding:5px 0;border-bottom:1px solid #2a2a2a'><span style='font-size:0.85rem;color:#bbb'>{r['Specialità']}</span><span style='font-size:1rem;font-weight:700;color:#eee'>{r['Prestazione']}</span></div>" for _,r in df_pb[~df_pb['is_road']].head(6).iterrows()])

    st.markdown(f"""
<div style="background:linear-gradient(160deg,#1a1a2e 0%,#0f3460 100%);border-radius:12px;padding:16px 18px;border-left:5px solid #4caf50;font-family:sans-serif;">
  <div style="font-size:1.3rem;font-weight:900;color:white;margin-bottom:4px">{nome}</div>
  <div style="font-size:0.8rem;color:#81c784;margin-bottom:12px">🏅 {categoria} | 🏢 {societa}</div>
  <div style="font-size:0.72rem;color:#81c784;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin-bottom:4px">🏃 Strada / Maratona</div>
  {road_html if road_html else '<div style="color:#888;font-style:italic;font-size:0.85rem">Nessun record su strada</div>'}
  {('<div style="margin-top:14px;font-size:0.72rem;color:#78909c;text-transform:uppercase;letter-spacing:1px;margin-bottom:4px">Altri Primati</div>'+other_html) if other_html else ""}
</div>
""", unsafe_allow_html=True)

@st.dialog("🥇 Scheda Atleta", width="large")
def popup_atleta(row):
    show_pb_from_row(row)

# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    # Global CSS
    st.markdown("""
<style>
[data-testid="stHorizontalBlock"] { display: flex !important; flex-direction: row !important; flex-wrap: nowrap !important; align-items: center !important; justify-content: space-between !important; }
[data-testid="stHorizontalBlock"] > div { flex: 1 1 0% !important; min-width: 0 !important; }
div[data-testid="stButton"] > button { border-radius: 8px !important; font-weight: 700 !important; font-size: 0.8rem !important; padding: 8px 2px !important; width: 100% !important; white-space: nowrap !important; overflow: hidden !important; text-overflow: ellipsis !important; }
div[data-testid="stButton"].row-btn > button { background: transparent !important; border: none !important; border-bottom: 1px solid #2a2a2a !important; border-radius: 0 !important; color: inherit !important; text-align: left !important; width: 100% !important; padding: 8px 4px !important; display: block !important; }
div[data-testid="stButton"].row-btn > button:hover { background: rgba(76,175,80,0.08) !important; color: #4caf50 !important; }
</style>
""", unsafe_allow_html=True)

    # Header
    c1, c2 = st.columns([1, 8])
    with c1:
        if os.path.exists("icron_logo.png"): st.image("icron_logo.png", width=80)
    with c2:
        st.markdown("<div style='display:flex;align-items:center;height:80px'><span style='font-size:2rem;font-weight:900;letter-spacing:-1px'>PERSONAL BEST <span style='color:#4caf50'>Iscritti</span></span></div>", unsafe_allow_html=True)

    # Query Param Sync
    if 'df_iscritti' not in st.session_state:
        g = st.query_params.get('gara', '')
        if g:
            try:
                df = fetch_from_icron(g)
                if not df.empty:
                    df['PETT'] = df['PETT'].astype(str).str.strip().str.replace('.0', '', regex=False)
                    st.session_state['df_iscritti'] = df
                    st.session_state['icron_id_loaded'] = g
            except: pass

    # Navigation
    if 'tab_section' not in st.session_state: st.session_state['tab_section'] = 'elenco'
    s_now = st.session_state['tab_section']
    
    n1, n2, n3 = st.columns(3)
    if n1.button("📁 Carica", use_container_width=True, type="primary" if s_now=='carica' else "secondary"):
        st.session_state['tab_section'] = 'carica'; st.rerun()
    if n2.button("👥 Elenco", use_container_width=True, type="primary" if s_now=='elenco' else "secondary"):
        st.session_state['tab_section'] = 'elenco'; st.rerun()
    if n3.button("🔍 Cerca", use_container_width=True, type="primary" if s_now=='cerca' else "secondary"):
        st.session_state['tab_section'] = 'cerca'; st.rerun()
    st.divider()

    sect = st.session_state['tab_section']
    df_main = st.session_state.get('df_iscritti')

    if sect == 'carica':
        st.markdown("#### 📁 Carica Gara")
        src = st.radio("Sorgente", ["🌐 Scarica da ICRON", "📄 Carica CSV locale"], horizontal=True)
        if src == "🌐 Scarica da ICRON":
            c_id = st.session_state.get('icron_id_loaded', '')
            id_g = st.text_input("ID Gara ICRON", value=c_id, placeholder="Es. 20264691")
            b1, b2 = st.columns(2)
            if b1.button("⬇️ Carica Iscritti", use_container_width=True) or b2.button("🔄 Forza Ricarica", use_container_width=True):
                if id_g:
                    try:
                        df_i = fetch_from_icron(id_g)
                        df_i['PETT'] = df_i['PETT'].astype(str).str.strip().str.replace('.0', '', regex=False)
                        st.session_state['df_iscritti'] = df_i
                        st.session_state['icron_id_loaded'] = id_g
                        st.query_params['gara'] = id_g
                        st.session_state['tab_section'] = 'elenco'; st.rerun()
                    except Exception as e: st.error(f"Errore: {e}")
        else:
            f = st.file_uploader("Carica CSV", type=['csv'])
            if f:
                df_c = pd.read_csv(f, sep=None, engine='python')
                df_c.columns = df_c.columns.str.strip()
                m = {c: 'PETT' for c in df_c.columns if 'pett' in c.lower()}
                m.update({c: 'COGNOME' for c in df_c.columns if 'cogn' in c.lower()})
                # ... etc
                df_c.rename(columns=m, inplace=True)
                st.session_state['df_iscritti'] = df_c
                st.session_state['tab_section'] = 'elenco'; st.rerun()

    elif sect == 'elenco':
        st.markdown("#### 👥 Elenco Iscritti")
        if df_main is None or df_main.empty:
            st.info("Nessuna gara caricata. Vai su **📁 Carica Gara** per cominciare.")
        else:
            df_d = df_main.copy()
            df_d['ATLETA'] = (df_d.get('COGNOME', '') + ' ' + df_d.get('NOME', '')).str.strip()
            df_d['_P_N'] = pd.to_numeric(df_d['PETT'], errors='coerce')
            df_s = df_d.sort_values('_P_N').reset_index(drop=True)
            q = st.text_input("🔎 Filtra…").strip().lower()
            if q:
                df_s = df_s[df_s['ATLETA'].str.lower().str.contains(q) | df_s['PETT'].str.contains(q)]
            st.caption(f"{len(df_s)} iscritti")
            st.markdown("<div style='display:flex;gap:8px;padding:4px;border-bottom:2px solid #333;font-size:0.7rem;font-weight:700;color:#666'> <span style='width:36px'>Pett.</span> <span style='flex:1'>Atleta</span> <span style='width:60px'>Cat.</span> </div>", unsafe_allow_html=True)
            for i, r in df_s.iterrows():
                pv = str(int(r['_P_N'])) if not pd.isna(r['_P_N']) else str(r['PETT'])
                st.markdown('<div class="row-btn">', unsafe_allow_html=True)
                if st.button(f"#{pv} {r['ATLETA']}\n{r.get('CATEGORIA','-')} · {r.get('SOCIETA','-')}", key=f"r_{i}", use_container_width=True):
                    popup_atleta(r.to_dict())
                st.markdown('</div>', unsafe_allow_html=True)

    elif sect == 'cerca':
        if df_main is None or df_main.empty:
            st.info("Nessuna gara caricata. Vai su **📁 Carica Gara** per cominciare.")
        else:
            p = st.text_input("🔢 N° Pettorale", key="search_p")
            if st.button("🔍 Cerca Atleta", use_container_width=True, type="primary") or p:
                match = df_main[df_main['PETT'] == p.strip()]
                if not match.empty: popup_atleta(match.iloc[0].to_dict())
                else: st.warning("Atleta non trovato.")

if __name__ == "__main__":
    main()
