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

st.set_page_config(page_title="PERSONAL BEST Iscritti", page_icon="🏅", layout="wide")

ICRON_CACHE_FILE = "icron_cache.json"

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


@st.cache_data(ttl=3600 * 2, show_spinner=False)
def fetch_from_icron(id_gara):
    url = "https://www.icron.it/IcronNewGO/getIscrizioni"
    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "Referer": "https://www.icron.it/newgo/"
    }
    payload = {"idGara": str(id_gara).strip()}
    resp = requests.post(url, json=payload, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if data.get("esito") != "OK":
        raise ValueError(f"ICRON errore: {data.get('messaggio', 'sconosciuto')}")
    participants = data.get("elencoPartecipanti", [])
    if not participants:
        return pd.DataFrame()
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
        pb_data = []
        recent_bests = {}
        # (spec_lowercase, prestazione) → full_date "dd/mm/yyyy"
        perf_dates = {}

        for table in soup.find_all('table'):
            headers = [th.get_text(strip=True).lower() for th in table.find_all('th')]
            if not headers and table.find('tr'):
                headers = [td.get_text(strip=True).lower() for td in table.find('tr').find_all('td')]

            is_pb_table = (any('specialit' in h for h in headers) or
                           any('prestazione' in h or 'gara' in h for h in headers) or
                           table.parent.get('id') == 'tab3')
            # FIDAL: tabella storico ha 'anno' come PRIMA colonna; tabella primati ha 'gara' o 'specialità'
            first_h = headers[0].lower().strip() if headers else ''
            is_hist_table = first_h in ('anno', 'anno/data')
            is_pb_summary = is_pb_table and first_h not in ('anno', 'anno/data', '')

            # ── Tabella Primati/riepilogo (tab3): Gara | Tipo | Prestazione | Vento | Anno | Città ──
            if is_pb_summary:
                for tr in table.find_all('tr'):
                    cells = tr.find_all(['td', 'th'])
                    if not cells or len(cells) < 3:
                        continue
                    specialty = cells[0].get_text(strip=True)
                    if not specialty or specialty.lower() in ('gara', 'specialità', 'specialita'):
                        continue
                    env  = cells[1].get_text(strip=True) if len(cells) > 1 else ""
                    perf = cells[2].get_text(strip=True) if len(cells) > 2 else ""
                    year = cells[4].get_text(strip=True) if len(cells) > 4 else ""
                    loc  = cells[5].get_text(strip=True) if len(cells) > 5 else ""
                    pb_data.append({"Specialità": specialty, "Ambiente": env,
                                    "Prestazione": perf, "Data": year, "Luogo": loc})

            # ── Tabella Storico (tutti gli anni) ──
            if is_hist_table:
                h_tag = table.find_previous(['h1', 'h2', 'h3', 'h4', 'h5'])
                spec = h_tag.get_text(strip=True) if h_tag else ""
                for tr in table.find_all('tr'):
                    cells = tr.find_all(['td', 'th'])
                    if len(cells) < 3:
                        continue
                    year_cell = cells[0].get_text(strip=True)
                    if not (year_cell.isdigit() and len(year_cell) == 4):
                        continue
                    date_part = cells[1].get_text(strip=True) if len(cells) > 1 else ""
                    perf_cell = cells[6].get_text(strip=True) if len(cells) > 6 else cells[2].get_text(strip=True)
                    loc_cell  = cells[-1].get_text(strip=True)
                    full_date = f"{date_part}/{year_cell}" if date_part else year_cell
                    # Dizionario data per ogni prestazione
                    key = (spec.lower(), perf_cell)
                    if key not in perf_dates:
                        perf_dates[key] = full_date
                    # Recent bests 2025-26
                    if year_cell in ['2025', '2026']:
                        sec = hms_to_seconds(perf_cell)
                        if spec and sec < 999999:
                            prev = recent_bests.get(spec)
                            if prev is None or sec < prev[0]:
                                recent_bests[spec] = (sec, perf_cell, loc_cell, year_cell, full_date)

        # ── Arricchisci pb_data con la data completa dallo storico ──
        for pb in pb_data:
            key = (pb.get('Specialità', '').lower(), pb.get('Prestazione', ''))
            if key in perf_dates:
                pb['Data'] = perf_dates[key]

        return pb_data, recent_bests
    except Exception:
        return [], {}


def show_pb_from_row(row):
    tessera_trovata = str(row.get('TESSERA', '')).strip()
    encrypted_slug = encode_tessera(tessera_trovata)
    athlete_url = f"https://www.fidal.it/atleta/x/{encrypted_slug}"
    nome_completo = f"{row.get('COGNOME', '-')} {row.get('NOME', '')}".strip()
    categoria = row.get('CATEGORIA', '-')
    societa = row.get('SOCIETA', '-')
    pett = row.get('PETT', '-')

    st.markdown(f"**#{pett} &nbsp;·&nbsp; {nome_completo}**  \n🏅 {categoria} &nbsp;|&nbsp; 🏢 {societa}", unsafe_allow_html=True)
    st.divider()

    with st.spinner("Recupero PB da FIDAL..."):
        pbs, recent_bests = extract_all_pbs(athlete_url)

    if not pbs:
        st.warning("Nessun primato registrato su FIDAL.")
        return

    df_pb = pd.DataFrame(pbs)

    def is_road_event(spec):
        s = str(spec).lower()
        return any(k in s for k in ['strada', 'maratona', 'maratonina', 'km'])

    def get_recent(spec):
        match = recent_bests.get(spec)
        if match:
            full_date = match[4] if len(match) > 4 else match[3]
            return f"{match[1]} @ {match[2]} ({full_date})"
        for k, v in recent_bests.items():
            if spec.lower() in k.lower() or k.lower() in spec.lower():
                full_date = v[4] if len(v) > 4 else v[3]
                return f"{v[1]} @ {v[2]} ({full_date})"
        return ""

    df_pb['Miglior 2025-26'] = df_pb['Specialità'].apply(get_recent)
    df_pb['is_road'] = df_pb['Specialità'].apply(is_road_event)
    df_pb = df_pb.sort_values(by=['is_road', 'Specialità'], ascending=[False, True]).drop('is_road', axis=1)

    road_rows = df_pb[df_pb['Specialità'].apply(is_road_event)].head(4)
    other_rows = df_pb[~df_pb['Specialità'].apply(is_road_event)].head(6)

    road_html = ""
    for _, r in road_rows.iterrows():
        rec   = r.get('Miglior 2025-26', '')
        luogo = r.get('Luogo', '')
        data  = r.get('Data', r.get('Data/Anno', ''))
        rec_line = f"<div style='font-size:0.78rem;color:#ffab40;margin-top:3px'>⭐ SB: {rec}</div>" if rec else ""
        loc_line = f"<div style='font-size:0.78rem;color:#90caf9'>📍 {luogo}</div>" if luogo else ""
        dat_line = f"<div style='font-size:0.72rem;color:#78909c'>{data}</div>" if data else ""
        road_html += f"""
<div style='padding:10px 0;border-bottom:1px solid #333'>
  <div style='font-size:0.95rem;color:#a5d6a7;font-weight:600'>{r['Specialità']}</div>
  <div style='font-size:1.6rem;font-weight:900;color:white;line-height:1.1'>{r['Prestazione']}</div>
  {loc_line}{dat_line}{rec_line}
</div>"""

    other_html = ""
    for _, r in other_rows.iterrows():
        other_html += f"""
<div style='display:flex;justify-content:space-between;align-items:center;padding:5px 0;border-bottom:1px solid #2a2a2a'>
  <span style='font-size:0.85rem;color:#bbb'>{r['Specialità']}</span>
  <span style='font-size:1rem;font-weight:700;color:#eee'>{r['Prestazione']}</span>
</div>"""

    altri_section = (
        f"<div style='margin-top:14px;font-size:0.72rem;color:#78909c;"
        f"text-transform:uppercase;letter-spacing:1px;margin-bottom:4px'>Altri Primati</div>"
        + other_html
    ) if other_html else ""

    st.markdown(f"""
<div style="
    background:linear-gradient(160deg,#1a1a2e 0%,#0f3460 100%);
    border-radius:12px;padding:16px 18px;margin:4px 0;
    border-left:5px solid #4caf50;
    font-family:'Segoe UI',sans-serif;
    word-break:break-word;
">
  <div style="font-size:1.3rem;font-weight:900;color:white;margin-bottom:4px">{nome_completo}</div>
  <div style="font-size:0.8rem;color:#81c784;margin-bottom:12px">🏅 {categoria} &nbsp;|&nbsp; 🏢 {societa}</div>
  <div style="font-size:0.72rem;color:#81c784;font-weight:700;text-transform:uppercase;
              letter-spacing:1px;margin-bottom:4px">🏃 Strada / Maratona</div>
  {road_html if road_html else '<div style="color:#888;font-style:italic;font-size:0.85rem">Nessun record su strada</div>'}
  {altri_section}
</div>
""", unsafe_allow_html=True)


@st.dialog("🥇 Scheda Atleta", width="large")
def popup_atleta(row):
    show_pb_from_row(row)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    # Header with logo + title
    col_logo, col_title = st.columns([1, 8])
    with col_logo:
        logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icron_logo.png")
        if os.path.exists(logo_path):
            st.image(logo_path, width=80)
    with col_title:
        st.markdown("""
<div style='display:flex;align-items:center;height:80px'>
  <span style='font-size:2rem;font-weight:900;letter-spacing:-1px'>PERSONAL BEST <span style='color:#4caf50'>Iscritti</span></span>
</div>""", unsafe_allow_html=True)

    # Ripristino dati da URL query param (?gara=ID) — persiste al reload, isolato per utente
    if 'df_iscritti' not in st.session_state:
        gara_from_url = st.query_params.get('gara', '')
        if gara_from_url:
            try:
                df_restored = fetch_from_icron(gara_from_url)
                if not df_restored.empty:
                    df_restored['PETT'] = df_restored['PETT'].astype(str).str.strip().str.replace('.0', '', regex=False)
                    st.session_state['df_iscritti'] = df_restored
                    st.session_state['icron_id_loaded'] = gara_from_url
            except Exception:
                pass

    # 3-button navigation
    if 'tab_section' not in st.session_state:
        st.session_state['tab_section'] = 'elenco'

    nav1, nav2, nav3 = st.columns(3)
    if nav1.button("📁 Carica Gara", use_container_width=True,
                   type="primary" if st.session_state['tab_section'] == 'carica' else "secondary"):
        st.session_state['tab_section'] = 'carica'
        st.rerun()
    if nav2.button("👥 Elenco Iscritti", use_container_width=True,
                   type="primary" if st.session_state['tab_section'] == 'elenco' else "secondary"):
        st.session_state['tab_section'] = 'elenco'
        st.rerun()
    if nav3.button("🔍 Cerca Atleta", use_container_width=True,
                   type="primary" if st.session_state['tab_section'] == 'cerca' else "secondary"):
        st.session_state['tab_section'] = 'cerca'
        st.rerun()
    st.divider()

    section = st.session_state['tab_section']
    df_iscritti = st.session_state.get('df_iscritti')

    # ── CARICA GARA ──────────────────────────────────────────────────────────
    if section == 'carica':
        st.markdown("#### 📁 Carica Gara")
        source_choice = st.radio("Sorgente", ["🌐 Scarica da ICRON", "📄 Carica CSV locale"],
                                 horizontal=True, key="source_choice")
        if source_choice == "🌐 Scarica da ICRON":
            cached_id = st.session_state.get('icron_id_loaded', '')
            id_gara = st.text_input("ID Gara ICRON", placeholder="Es. 20264691",
                                    help="L'ID è l'ultima parte dell'URL ICRON",
                                    key="icron_id_value", value=cached_id)
            col_btn1, col_btn2 = st.columns(2)
            load_btn  = col_btn1.button("⬇️ Carica Iscritti", use_container_width=True)
            clear_btn = col_btn2.button("🔄 Ricarica da ICRON", use_container_width=True)
            if df_iscritti is not None and cached_id == id_gara:
                st.success(f"✅ **{len(df_iscritti)}** iscritti in memoria (ID: {id_gara})")
            if load_btn or clear_btn:
                if clear_btn:
                    fetch_from_icron.clear()
                if id_gara:
                    with st.spinner(f"Recupero da ICRON (ID: {id_gara})..."):
                        try:
                            df_icron = fetch_from_icron(id_gara)
                            if df_icron.empty:
                                st.warning("Nessun iscritto trovato.")
                            else:
                                df_icron['PETT'] = df_icron['PETT'].astype(str).str.strip().str.replace('.0', '', regex=False)
                                st.session_state['df_iscritti'] = df_icron
                                st.session_state['icron_id_loaded'] = id_gara
                                # Salva ID nella URL — persiste al reload, unico per ogni utente
                                st.query_params['gara'] = id_gara
                                st.success(f"✅ Caricati **{len(df_icron)}** iscritti")
                                st.session_state['tab_section'] = 'elenco'
                                st.rerun()
                        except Exception as e:
                            st.error(f"Errore: {e}")
                else:
                    st.warning("Inserisci un ID gara.")
        else:
            file_iscritti = st.file_uploader("Carica CSV Iscritti", type=['csv'], key="csv_iscritti")
            if file_iscritti:
                try:
                    df_csv = pd.read_csv(file_iscritti, sep=None, engine='python')
                    df_csv.columns = df_csv.columns.str.strip()
                    rename_csv = {}
                    for c in df_csv.columns:
                        cl = c.lower()
                        if 'pett' in cl: rename_csv[c] = 'PETT'
                        elif 'tess' in cl: rename_csv[c] = 'TESSERA'
                        elif 'cogn' in cl: rename_csv[c] = 'COGNOME'
                        elif 'nom' in cl and 'cogn' not in cl: rename_csv[c] = 'NOME'
                        elif 'soc' in cl: rename_csv[c] = 'SOCIETA'
                        elif 'cat' in cl: rename_csv[c] = 'CATEGORIA'
                    df_csv.rename(columns=rename_csv, inplace=True)
                    df_csv['PETT'] = df_csv['PETT'].astype(str).str.strip().str.replace('.0', '', regex=False)
                    st.session_state['df_iscritti'] = df_csv
                    st.session_state.pop('icron_id_loaded', None)
                    st.success(f"✅ CSV caricato con **{len(df_csv)}** iscritti.")
                    st.session_state['tab_section'] = 'elenco'
                    st.rerun()
                except Exception as e:
                    st.error(f"Errore nella lettura del CSV: {e}")

    # ── ELENCO ISCRITTI ──────────────────────────────────────────────────────
    elif section == 'elenco':
        st.markdown("#### 👥 Elenco Iscritti")
        if df_iscritti is None or df_iscritti.empty:
            st.info("Nessuna gara caricata. Vai su **📁 Carica Gara** per cominciare.")
        else:
            df_display = df_iscritti.copy()
            df_display['ATLETA'] = (df_display.get('COGNOME', '').astype(str).str.strip() + ' '
                                    + df_display.get('NOME', '').astype(str).str.strip()).str.strip()
            df_display['_PETT_NUM'] = pd.to_numeric(df_display['PETT'], errors='coerce')
            df_sorted = df_display.sort_values('_PETT_NUM').reset_index(drop=True)

            filter_q = st.text_input("🔎 Filtra…", placeholder="Cognome, nome o pettorale", key="elenco_filter")
            if filter_q:
                q = filter_q.strip().lower()
                mask = pd.Series([False] * len(df_sorted), index=df_sorted.index)
                for col in ['ATLETA', 'PETT']:
                    if col in df_sorted.columns:
                        mask |= df_sorted[col].astype(str).str.lower().str.contains(q, na=False)
                df_sorted = df_sorted[mask].reset_index(drop=True)

            st.caption(f"{len(df_sorted)} iscritti — clicca sul nome per aprire la scheda atleta")

            # CSS tabella dark con nomi cliccabili
            st.markdown("""
<style>
.fidal-table { width:100%; border-collapse:collapse; margin-top:4px; }
.fidal-table .hdr {
    font-size:0.72rem; font-weight:700; color:#888;
    text-transform:uppercase; letter-spacing:.6px;
    padding:6px 4px; border-bottom:2px solid #333;
}
/* Azzera i bottoni Streamlit all'interno della tabella */
div[data-testid="stHorizontalBlock"] div[data-testid="stButton"] > button {
    background: transparent !important;
    border: none !important;
    border-radius: 0 !important;
    box-shadow: none !important;
    color: #e0e0e0 !important;
    font-size: 0.9rem !important;
    font-weight: 500 !important;
    padding: 0 !important;
    text-align: left !important;
    width: 100% !important;
    transition: color 0.15s;
}
div[data-testid="stHorizontalBlock"] div[data-testid="stButton"] > button:hover {
    color: #4caf50 !important;
    text-decoration: underline !important;
    cursor: pointer !important;
    background: transparent !important;
}
</style>
""", unsafe_allow_html=True)

            # Intestazione
            h1, h2, h3, h4 = st.columns([1, 4, 2, 4])
            h1.markdown('<p class="hdr">Pett.</p>', unsafe_allow_html=True)
            h2.markdown('<p class="hdr">Atleta</p>', unsafe_allow_html=True)
            h3.markdown('<p class="hdr">Cat.</p>', unsafe_allow_html=True)
            h4.markdown('<p class="hdr">Società</p>', unsafe_allow_html=True)

            for i, ath in df_sorted.iterrows():
                pv = str(int(ath['_PETT_NUM'])) if not pd.isna(ath.get('_PETT_NUM')) else str(ath.get('PETT', ''))
                bg = "background:rgba(255,255,255,0.03);" if i % 2 == 0 else ""
                c1, c2, c3, c4 = st.columns([1, 4, 2, 4])
                c1.markdown(f"<div style='{bg}padding:6px 4px;border-bottom:1px solid #222;font-size:0.9rem;font-weight:700'>{pv}</div>", unsafe_allow_html=True)
                with c2:
                    st.markdown(f"<div style='{bg}border-bottom:1px solid #222;'>", unsafe_allow_html=True)
                    if st.button(str(ath.get('ATLETA', '')), key=f"erow_{i}", use_container_width=True):
                        m = df_iscritti[df_iscritti['PETT'] == pv]
                        if not m.empty:
                            popup_atleta(m.iloc[0].to_dict())
                    st.markdown("</div>", unsafe_allow_html=True)
                c3.markdown(f"<div style='{bg}padding:6px 4px;border-bottom:1px solid #222;font-size:0.85rem;color:#ccc'>{ath.get('CATEGORIA','')}</div>", unsafe_allow_html=True)
                c4.markdown(f"<div style='{bg}padding:6px 4px;border-bottom:1px solid #222;font-size:0.85rem;color:#aaa'>{ath.get('SOCIETA','')}</div>", unsafe_allow_html=True)

    # ── CERCA ATLETA ─────────────────────────────────────────────────────────
    elif section == 'cerca':
        if df_iscritti is None or df_iscritti.empty:
            st.info("Nessuna gara caricata. Vai su **📁 Carica Gara** per cominciare.")
        else:
            # Force numeric keyboard on mobile/tablet via JS
            st.markdown("""
<script>
window.addEventListener('load', function() {
    setTimeout(function() {
        var inputs = window.parent.document.querySelectorAll('input[data-baseweb="input"]');
        inputs.forEach(function(el) {
            el.setAttribute('inputmode', 'numeric');
            el.setAttribute('pattern', '[0-9]*');
        });
    }, 500);
});
</script>
""", unsafe_allow_html=True)

            pett_input = st.text_input("", placeholder="🔢 N° Pettorale",
                                       key="search_pett", label_visibility="collapsed")
            cerca_btn = st.button("🔍 Cerca", use_container_width=True, type="primary")

            if cerca_btn or pett_input:
                found_row = None
                if pett_input:
                    match = df_iscritti[df_iscritti['PETT'] == str(pett_input).strip()]
                    if not match.empty:
                        found_row = match.iloc[0].to_dict()
                    else:
                        st.warning(f"Nessun atleta con pettorale **{pett_input}**.")
                if found_row:
                    st.session_state['cerca_key'] = st.session_state.get('cerca_key', 0) + 1
                    popup_atleta(found_row)


if __name__ == "__main__":
    main()
