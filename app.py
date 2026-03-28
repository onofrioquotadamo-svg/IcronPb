import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import re
import datetime
import base64
import urllib.parse
import concurrent.futures
import os
import json

st.set_page_config(page_title="FIDAL PB/SB Scraper", page_icon="🏃‍♂️", layout="wide")

def decode_tessera(encoded_str):
    """Decodifica il link criptato della FIDAL per ottenere la Tessera Atleta."""
    key = b"3gabbo83"
    try:
        code = encoded_str.split('/')[-1]
        code = urllib.parse.unquote(code)
        code += "=" * ((4 - len(code) % 4) % 4)
        dec_bytes = base64.b64decode(code)
        tessera = ""
        for i in range(len(dec_bytes)):
            tessera += chr((dec_bytes[i] - key[i % len(key)]) % 256)
        if len(tessera) >= 8 and tessera[:2].isalpha() and tessera[2:].isdigit():
            return tessera
        return tessera
    except Exception as e:
        return "Sconosciuta"

def encode_tessera(tessera_str):
    """Codifica la Tessera con la chiave segreta FIDAL per generare il link."""
    key = b"3gabbo83"
    tessera_str = str(tessera_str).strip()
    enc_bytes = bytearray()
    for i in range(len(tessera_str)):
        enc_bytes.append((ord(tessera_str[i]) + key[i % len(key)]) % 256)
    b64 = base64.b64encode(enc_bytes).decode('utf-8')
    return urllib.parse.quote(b64)

@st.cache_data(ttl=3600*24)
def get_regions():
    url = "https://www.fidal.it/regioni.php"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        regions = []
        for a in soup.find_all('a', href=True):
            match = re.search(r'regione_one\.php\?id=([A-Z0-9]+)', a['href'])
            if match:
                name = a.get_text(strip=True)
                region_id = match.group(1)
                if name and not any(r['id'] == region_id for r in regions):
                    regions.append({'name': name, 'id': region_id})
        return sorted(regions, key=lambda x: x['name'])
    except Exception as e:
        st.error(f"Errore nel recupero delle regioni: {e}")
        return []

@st.cache_data(ttl=3600*24)
def get_societies_for_region(region_id):
    url = f"https://www.fidal.it/mappa.php?regione={region_id}"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        societies = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            if '/societa/' in href.lower() or 'codsoc=' in href.lower():
                name = a.get_text(strip=True)
                if name and len(name) > 2:
                    full_url = href if href.startswith('http') else 'https://www.fidal.it' + (href if href.startswith('/') else '/' + href)
                    if not any(s['url'] == full_url for s in societies):
                        code_part = full_url.rstrip('/').split('/')[-1]
                        if 'codsoc=' in code_part:
                            code_part = code_part.split('codsoc=')[-1][:5]
                        prov = code_part[:2].upper() if len(code_part) >= 2 and code_part[:2].isalpha() else "Altra"
                        societies.append({'name': name, 'url': full_url, 'prov': prov})
        return societies
    except Exception as e:
        return []

def get_athletes_for_society(society_url, category_filter="Tutti i tesserati (Giovanili + Assoluti + Master)", session=None):
    if session is None:
        session = requests.Session()
    try:
        resp = session.get(society_url, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        tab_map = {}
        for li in soup.find_all('li'):
            a = li.find('a', href=True)
            if a and a.get('href', '').startswith('#tab'):
                tab_name = a.get_text(strip=True).lower()
                tab_map[tab_name] = a['href'].replace('#', '')
                
        tabs_to_parse = []
        if category_filter == "Tutti i tesserati (Giovanili + Assoluti + Master)":
            for k, v in tab_map.items():
                if 'storico' not in k and 'eventi' not in k:
                    tabs_to_parse.append(v)
        elif category_filter == "Solo Giovanili":
            for k, v in tab_map.items():
                if 'giovanili' in k:
                    tabs_to_parse.append(v)
        elif category_filter == "Solo Assoluti/Master":
            for k, v in tab_map.items():
                if 'assoluti' in k or 'master' in k:
                    tabs_to_parse.append(v)
                    
        athletes = []
        divs = [soup.find('div', id=t) for t in tabs_to_parse if soup.find('div', id=t)]
        
        if not divs:
            divs = [soup]
            
        for div in divs:
            for a in div.find_all('a', href=True):
                href = a['href']
                if '/atleta/' in href.lower() or 'atleta.php' in href.lower():
                    full_url = href if href.startswith('http') else 'https://www.fidal.it' + (href if href.startswith('/') else '/' + href)
                    parts = full_url.split('/')
                    if len(parts) > 4 and parts[3] == 'atleta':
                        name = parts[4].replace('-', ' ')
                    else:
                        name = a.get_text(strip=True)
                        
                    if name and not any(ath['url'] == full_url for ath in athletes):
                        athletes.append({'name': name, 'url': full_url})
        return athletes
    except Exception as e:
        return []

def hms_to_seconds(t_str):
    t_str = t_str.lower().replace('h', ':')
    parts = t_str.split(':')
    try:
        if len(parts) == 3:
            return float(parts[0])*3600 + float(parts[1])*60 + float(parts[2])
        elif len(parts) == 2:
            return float(parts[0])*60 + float(parts[1])
        return float(parts[0])
    except:
        return 999999

def extract_perf(athlete_url, distance_keywords, target_year="Tutti gli anni (Miglior Risultato Assoluto - PB)", session=None):
    if session is None:
        session = requests.Session()
    try:
        resp = session.get(athlete_url, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        best_perf = None
        best_time_sec = 999999
        best_date = None
        best_loc = None
        best_spec = None
        best_cat = None
        
        for table in soup.find_all('table'):
            h = table.find_previous(['h1', 'h2', 'h3', 'h4'])
            if not h:
                continue
            spec_name = h.get_text(strip=True)
            if any(k.lower() in spec_name.lower() for k in distance_keywords):
                for row in table.find_all('tr'):
                    cells = row.find_all(['th', 'td'])
                    if len(cells) >= 9:
                        year = cells[0].get_text(strip=True)
                        cat = cells[4].get_text(strip=True)
                        perf = cells[6].get_text(strip=True)
                        loc = cells[8].get_text(strip=True)
                        date_str = f"{cells[1].get_text(strip=True)}/{year}"
                        
                        if target_year == "Tutti gli anni (Miglior Risultato Assoluto - PB)" or str(target_year) == year:
                            t_sec = hms_to_seconds(perf)
                            if t_sec < best_time_sec:
                                best_time_sec = t_sec
                                best_perf = perf
                                best_loc = loc
                                best_date = date_str
                                best_spec = spec_name
                                best_cat = cat
                                
        return best_spec, best_perf, best_date, best_loc, best_cat
    except Exception as e:
        return None, None, None, None, None

def extract_all_pbs(athlete_url):
    """Estrae tutti i Primati Personali e restituisce (pb_data, recent_bests)."""
    try:
        resp = requests.get(athlete_url, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        pb_data = []
        # Map specialty -> (best_recent_sec, best_recent_perf, best_recent_loc)
        recent_bests = {}
        
        for table in soup.find_all('table'):
            headers = [th.get_text(strip=True).lower() for th in table.find_all('th')]
            if not headers and table.find('tr'):
                headers = [td.get_text(strip=True).lower() for td in table.find('tr').find_all('td')]
            
            # PB table detection
            is_pb_table = (any('specialit' in h for h in headers) or
                           any('prestazione' in h for h in headers) or
                           table.parent.get('id') == 'tab3')
            # Historical table detection (has year column = first col is 4-digit year)
            is_hist_table = any(h in ['anno', 'anno/data', 'data'] for h in headers)
            
            if is_pb_table:
                for tr in table.find_all('tr'):
                    cells = tr.find_all(['td', 'th'])
                    if not cells or len(cells) < 3:
                        continue
                    specialty = cells[0].get_text(strip=True)
                    if specialty.lower() == 'specialità' or not specialty:
                        continue
                    env = cells[1].get_text(strip=True) if len(cells) > 1 else ""
                    perf = cells[2].get_text(strip=True) if len(cells) > 2 else ""
                    year = cells[4].get_text(strip=True) if len(cells) > 4 else ""
                    loc = cells[5].get_text(strip=True) if len(cells) > 5 else ""
                    pb_data.append({
                        "Specialità": specialty,
                        "Ambiente": env,
                        "Prestazione": perf,
                        "Data/Anno": year,
                        "Luogo": loc
                    })
            
            # Scrape historical rows for recent best
            if is_hist_table or is_pb_table:
                # Find parent specialty heading
                h = table.find_previous(['h1','h2','h3','h4','h5'])
                spec = h.get_text(strip=True) if h else ""
                for tr in table.find_all('tr'):
                    cells = tr.find_all(['td','th'])
                    if len(cells) < 3:
                        continue
                    year_cell = cells[0].get_text(strip=True)
                    if year_cell in ['2025', '2026']:
                        # cols: anno, mese/giorno, categoria?, ..., prestazione, ..., luogo
                        # Try to get perf from col index 6 or 2
                        perf_cell = cells[6].get_text(strip=True) if len(cells) > 6 else cells[2].get_text(strip=True)
                        loc_cell = cells[-1].get_text(strip=True)
                        sec = hms_to_seconds(perf_cell)
                        if spec and sec < 999999:
                            prev = recent_bests.get(spec)
                            if prev is None or sec < prev[0]:
                                recent_bests[spec] = (sec, perf_cell, loc_cell, year_cell)
        
        return pb_data, recent_bests
    except Exception as e:
        return [], {}

@st.cache_data(ttl=3600*2, show_spinner=False)
def fetch_from_icron(id_gara):
    """Recupera l'elenco degli iscritti da ICRON tramite POST API. Memorizzato in cache per 2 ore."""
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
        raise ValueError(f"ICRON ha risposto con errore: {data.get('messaggio', 'sconosciuto')}")
    participants = data.get("elencoPartecipanti", [])
    if not participants:
        return pd.DataFrame()
    df = pd.DataFrame(participants)
    # Normalize column names to our naming convention
    rename_map = {
        'pettorale': 'PETT',
        'cognome': 'COGNOME',
        'nome': 'NOME',
        'tessera': 'TESSERA',
        'categoria': 'CATEGORIA',
        'squadra': 'SOCIETA',
        'sesso': 'SESSO',
        'dataNascita': 'DATA_NASCITA',
    }
    df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns}, inplace=True)
    return df

def show_pb_from_row(row):
    """Mostra i PB dell'atleta in modalità commento gara (usata dentro st.dialog)."""
    tessera_trovata = str(row.get('TESSERA', '')).strip()
    encrypted_slug = encode_tessera(tessera_trovata)
    athlete_url = f"https://www.fidal.it/atleta/x/{encrypted_slug}"

    nome_completo = f"{row.get('COGNOME', '-')} {row.get('NOME', '')}".strip()
    categoria = row.get('CATEGORIA', '-')
    societa = row.get('SOCIETA', '-')
    pett = row.get('PETT', '-')

    # Header inside dialog
    st.markdown(f"**#{pett} &nbsp;·&nbsp; {nome_completo}**  \n🏅 {categoria} &nbsp;|&nbsp; 🏢 {societa}",
                unsafe_allow_html=True)
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
            return f"{match[1]} @ {match[2]} ({match[3]})"
        for k, v in recent_bests.items():
            if spec.lower() in k.lower() or k.lower() in spec.lower():
                return f"{v[1]} @ {v[2]} ({v[3]})"
        return ""

    df_pb['Miglior 2025-26'] = df_pb['Specialità'].apply(get_recent)
    df_pb['is_road'] = df_pb['Specialità'].apply(is_road_event)
    df_pb = df_pb.sort_values(by=['is_road', 'Specialità'], ascending=[False, True]).drop('is_road', axis=1)

    road_rows = df_pb[df_pb['Specialità'].apply(is_road_event)].head(4)
    other_rows = df_pb[~df_pb['Specialità'].apply(is_road_event)].head(6)

    road_html = ""
    for _, r in road_rows.iterrows():
        rec = r.get('Miglior 2025-26', '')
        rec_badge = f"<span style='font-size:0.9rem;color:#ffab40;margin-left:10px'>&#11088; {rec}</span>" if rec else ""
        luogo = r.get('Luogo', '')
        luogo_tag = f"<span style='font-size:0.8rem;color:#90caf9;margin-left:6px'>&#128205; {luogo}</span>" if luogo else ""
        road_html += (
            f"<div style='display:flex;justify-content:space-between;align-items:baseline;"
            f"border-bottom:1px solid #444;padding:8px 0'>"
            f"<span style='font-size:1.2rem;color:#a5d6a7'>{r['Specialità']}{luogo_tag}</span>"
            f"<span style='font-size:1.7rem;font-weight:800;color:white'>{r['Prestazione']}"
            f"{rec_badge}</span></div>"
        )

    other_html = ""
    for _, r in other_rows.iterrows():
        other_html += (
            f"<div style='display:flex;justify-content:space-between;padding:4px 0;opacity:0.8'>"
            f"<span style='font-size:0.95rem;color:#ccc'>{r['Specialità']}</span>"
            f"<span style='font-size:1.1rem;color:#eee'>{r['Prestazione']}</span></div>"
        )

    st.markdown(f"""
<div style="
    background:linear-gradient(135deg,#1a1a2e 0%,#16213e 50%,#0f3460 100%);
    border-radius:14px;padding:24px 32px;margin:8px 0;
    border-left:6px solid #4caf50;box-shadow:0 6px 24px rgba(0,0,0,0.5);
    font-family:'Segoe UI',sans-serif;
">
  <div style="font-size:2.4rem;font-weight:900;color:white;line-height:1.1;margin-bottom:16px;
              text-shadow:0 2px 6px rgba(0,0,0,0.5)">{nome_completo}</div>
  <div style="font-size:0.95rem;color:#81c784;font-weight:600;
              text-transform:uppercase;letter-spacing:1px;margin-bottom:6px">&#127939; Strada / Maratona</div>
  {road_html if road_html else '<div style="color:#888;font-style:italic">Nessun record su strada</div>'}
  {'<div style="margin-top:16px;font-size:0.85rem;color:#78909c;text-transform:uppercase;letter-spacing:1px">Altri Primati</div>' + other_html if other_html else ''}
</div>
""", unsafe_allow_html=True)


@st.dialog("🥇 Scheda Atleta", width="large")
def popup_atleta(row):
    """Dialog popup che mostra la scheda completa dell'atleta."""
    show_pb_from_row(row)


def process_athlete_task(ath_req, session):
    """Worker function to process a single athlete concurrently."""
    soc, ath, distance_keywords, selected_year, update_mode, existing_athletes, has_csv, gender_cat_include = ath_req
    ath_url = ath['url']
    
    # Fast incremental skip
    if has_csv and ath_url in existing_athletes:
        if "Solo Nuovi Atleti" in update_mode:
            return "skipped", existing_athletes[ath_url]
            
    # Fetch data
    specialty, perf, date, loc, cat = extract_perf(ath_url, distance_keywords, selected_year, session)
    
    if not perf:
        return "empty", None

    # Apply gender filter from category string (SM/SF/PM/PF/JM/JF etc.)
    if gender_cat_include and cat:
        cat_upper = str(cat).upper().strip()
        # FIDAL categories: SM=Senior Maschile, SF=Senior Femminile; try second char or first two
        cat_gender = None
        for ch in cat_upper:
            if ch in ('M', 'F'):
                cat_gender = ch
                break
        if cat_gender and cat_gender != gender_cat_include:
            return "empty", None
        
    new_row = {
        "Regione": soc['reg'],
        "Provincia": soc['prov'],
        "Società": soc['name'],
        "Atleta": ath['name'],
        "Tessera": decode_tessera(ath_url),
        "Categoria": cat,
        "Specialità Trovata": specialty,
        "Risultato": perf,
        "Data": date,
        "Luogo": loc,
        "Link Atleta": ath_url
    }
    
    if has_csv and ath_url in existing_athletes:
        old_perf = existing_athletes[ath_url]['Risultato']
        if hms_to_seconds(perf) < hms_to_seconds(str(old_perf)):
            return "updated", new_row
        else:
            return "preserved", existing_athletes[ath_url]
    else:
        return "new", new_row


def main():
    st.title("🏃‍♂️ FIDAL PB/SB Scraper")
    st.markdown("Estrai i Primati Personali (PB) o i Migliori Risultati Stagionali (SB) degli atleti. *(Multithreading supportato)*")
    
    tab_scraper, tab_iscritti = st.tabs(["🔍 Scraper Globale (Società/Regioni)", "🎯 Ricerca Singolo Iscritto Gara"])
    
    with tab_scraper:
        regions = get_regions()
        if not regions:
            st.warning("Impossibile caricare le regioni.")
            return
            
        region_names = ["Tutte le Regioni"] + [r['name'] for r in regions]
        col1, col2 = st.columns(2)
        selected_region_name = col1.selectbox("Seleziona la Regione", region_names)
        
    
        with st.spinner("Caricamento società..."):
            all_societies = []
            if selected_region_name == "Tutte le Regioni":
                prog = st.progress(0, text="Caricamento società da tutte le regioni...")
                for idx, r in enumerate(regions):
                    prog.progress((idx + 1) / len(regions), text=f"Caricamento società Regione: {r['name']}")
                    socs = get_societies_for_region(r['id'])
                    for s in socs:
                        s['reg'] = r['name']
                    all_societies.extend(socs)
                prog.empty()
            else:
                selected_region_id = next(r['id'] for r in regions if r['name'] == selected_region_name)
                all_societies = get_societies_for_region(selected_region_id)
                for s in all_societies:
                    s['reg'] = selected_region_name
            
        if not all_societies:
            st.error("Nessuna società trovata.")
            return
            
        provinces = sorted(list(set(s['prov'] for s in all_societies if s['prov'] != "Altra")))
        if any(s['prov'] == "Altra" for s in all_societies):
            provinces.append("Altra")
            
        prov_options = ["Tutte le province"] + provinces
        selected_prov = col2.selectbox("Filtra per Provincia (opzionale)", prov_options)
    
        available_socs = sorted([s['name'] for s in all_societies if selected_prov == "Tutte le province" or s['prov'] == selected_prov])
        soc_options = ["Tutte le società"] + available_socs
        
        col3, col4 = st.columns(2)
        selected_soc = col3.selectbox("Filtra per Società (opzionale)", soc_options)
        
        current_year = datetime.date.today().year
        years = ["Tutti gli anni (Miglior Risultato Assoluto - PB)"] + [str(y) for y in range(current_year, 1999, -1)]
        selected_year = col4.selectbox("Seleziona Anno (PB Assoluto o Season Best)", years)
        
        col_dist1, col_dist2 = st.columns(2)
        distance_option = col_dist1.selectbox("Seleziona la Distanza", [
            "10km su Strada",
            "10000m su Pista",
            "Mezza Maratona (21km)",
            "Maratona (42km)",
        ])

        gender_option = col_dist2.selectbox("Filtra per Sesso", [
            "Tutti (M+F)",
            "Solo Maschile (M)",
            "Solo Femminile (F)",
        ])
        
        col_cat = st.columns(1)[0]
        cat_atleti_option = col_cat.selectbox("Filtra Categoria Atleti da ricercare", [
            "Tutti i tesserati (Giovanili + Assoluti + Master)",
            "Solo Giovanili",
            "Solo Assoluti/Master"
        ])
        
        # Distance → scraping keywords
        if distance_option == "10km su Strada":
            distance_keywords = ['10 km', '10km', 'strada km 10', 'strada 10']
        elif distance_option == "10000m su Pista":
            distance_keywords = ['10.000', '10000m', '10000 mt', '10000 pista']
        elif distance_option == "Maratona (42km)":
            distance_keywords = ['maratona']
        else:  # Mezza Maratona
            distance_keywords = ['mezza maratona', 'maratonina', 'mezza']

        # Gender filter: map to category letter suffix
        gender_cat_include = None
        if gender_option == "Solo Maschile (M)":
            gender_cat_include = 'M'
        elif gender_option == "Solo Femminile (F)":
            gender_cat_include = 'F'
            
        st.markdown("---")
        st.subheader("🔄 Aggiornamento Dati Esistenti")
        uploaded_file = st.file_uploader("Carica un file CSV precedentemente scaricato (opzionale)", type=['csv'])
    
        existing_athletes = {}
        update_mode = "Nessun Aggiornamento"
        
        if uploaded_file is not None:
            try:
                df_old = pd.read_csv(uploaded_file)
                if 'Link Atleta' in df_old.columns and 'Risultato' in df_old.columns:
                    existing_athletes = {row['Link Atleta']: row.to_dict() for _, row in df_old.iterrows()}
                    st.success(f"Caricato CSV con {len(existing_athletes)} atleti registrati.")
                    update_mode = st.radio("Seleziona la modalità di aggiornamento:", [
                        "Solo Nuovi Atleti (Veloce - salta chi è già nel file)",
                        "Nuovi Atleti + Verifica Record Migliorati (Lento - ricarica tutti i profili)"
                    ])
                else:
                    st.error("Il file CSV caricato non contiene le colonne 'Link Atleta' e 'Risultato' richieste per l'aggiornamento.")
            except Exception as e:
                st.error(f"Errore nella lettura del CSV: {e}")
                
        if st.button("Cerca e Scarica (Avanzato)"):
            # Filter societies for scraping
            societies_to_scrape = all_societies
            if selected_prov != "Tutte le province":
                societies_to_scrape = [s for s in societies_to_scrape if s['prov'] == selected_prov]
            if selected_soc != "Tutte le società":
                societies_to_scrape = [s for s in societies_to_scrape if s['name'] == selected_soc]
                
            with st.status(f"Ottimizzazione Estrazioni in corso...", expanded=True) as status:
                st.write(f"Trovate {len(societies_to_scrape)} società da processare nei filtri.")
                
                # Central session for Keep-Alive across all requests
                master_session = requests.Session()
                
                # Phase 1: Aggregate all athletes from the target societies
                st.write("📌 Fase 1: Recapito Atleti...")
                prep_prog = st.progress(0)
                athletes_to_scrape = []
                for i, soc in enumerate(societies_to_scrape):
                    prep_prog.progress((i + 1) / len(societies_to_scrape), text=f"Recapito atleti società {i+1}/{len(societies_to_scrape)}")
                    aths = get_athletes_for_society(soc['url'], cat_atleti_option, master_session)
                    for ath in aths:
                        # Package requests to feed to executor
                        athletes_to_scrape.append((soc, ath, distance_keywords, selected_year, update_mode, existing_athletes, uploaded_file is not None, gender_cat_include))
                        
                st.write(f"✅ Identificati {len(athletes_to_scrape)} atleti totali da scansionare.")
                
                # Phase 2: Concurrent Fast Extraction
                st.write(f"🚀 Fase 2: Estrazione Risultati in Multithreading...")
                
                all_data = [] # New or updated data
                preserved_data = [] # Data kept identical from CSV
                
                ext_prog = st.progress(0)
                ath_progress = st.empty()
                
                new_records_count = 0
                updated_records_count = 0
                
                # Limit workers to 5 to avoid IP blocks from FIDAL
                MAX_WORKERS = 5
                
                processed = 0
                with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                    # Using submit instead of map to cleanly handle progressive UI updates
                    future_to_req = {executor.submit(process_athlete_task, req, master_session): req for req in athletes_to_scrape}
                    
                    for future in concurrent.futures.as_completed(future_to_req):
                        req = future_to_req[future]
                        try:
                            result_type, data = future.result()
                            if result_type == "new":
                                all_data.append(data)
                                new_records_count += 1
                            elif result_type == "updated":
                                all_data.append(data)
                                updated_records_count += 1
                            elif result_type in ["preserved", "skipped"]:
                                preserved_data.append(data)
                                
                            # Update UI
                            processed += 1
                            ath_progress.text(f"  Elaborati: {processed}/{len(athletes_to_scrape)} atleti...")
                            ext_prog.progress(processed / len(athletes_to_scrape))
                            
                            # PERIODIC BACKUP CACHING
                            if processed % 50 == 0 and processed > 0:
                                backup_df = pd.DataFrame(all_data + preserved_data)
                                backup_df.to_csv("backup_fidal.csv", index=False)
                                
                        except Exception as exc:
                            st.error(f"Errore nell'atleta {req[1]['name']}: {exc}")
                    
                status.update(label="Estrazione e Ottimizzazione completata!", state="complete")
                st.session_state['all_data'] = all_data + preserved_data
                st.session_state['new_count'] = new_records_count
                st.session_state['upd_count'] = updated_records_count
                st.session_state['had_csv'] = (uploaded_file is not None)
                
                # Force final backup
                if len(all_data + preserved_data) > 0:
                    pd.DataFrame(all_data + preserved_data).to_csv("backup_fidal.csv", index=False)
                
        if 'all_data' in st.session_state and st.session_state['all_data']:
            df = pd.DataFrame(st.session_state['all_data'])
            
            if st.session_state.get('had_csv', False):
                nc = st.session_state.get('new_count', 0)
                uc = st.session_state.get('upd_count', 0)
                if nc == 0 and uc == 0:
                    st.warning("⚠️ Non ci sono dati aggiornati per questi filtri. Tutti i risultati preesistenti sono stati mantenuti intatti.")
                else:
                    st.success(f"Dati aggiornati! Trovati {nc} nuovi atleti e {uc} record migliorati.")
            else:
                st.success(f"Trovati {len(df)} atleti con il risultato richiesto!")
                
            st.dataframe(df)
            
            file_name = "fidal_risultati"
            csv = df.to_csv(index=False).encode('utf-8')
            download_name = f"{file_name}_{selected_region_name.lower().replace(' ', '_')}"
            if selected_prov != "Tutte le province":
                download_name += f"_{selected_prov.lower()}"
            if selected_year != "Tutti gli anni (Miglior Risultato Assoluto - PB)":
                download_name += f"_{selected_year}"
            else:
                download_name += "_pb"
            download_name += ".csv"
                
            st.download_button(
                label="Scarica CSV",
                data=csv,
                file_name=download_name,
                mime="text/csv"
            )
            
            if os.path.exists("backup_fidal.csv"):
                st.info("Un backup di sicurezza (backup_fidal.csv) è stato salvato automaticamente nella cartella in caso di chiusura accidentale.")

    with tab_iscritti:
        ICRON_CACHE_FILE = "icron_cache.json"

        # ── Load df_iscritti from session or cache ─────────────────────────
        if 'df_iscritti' not in st.session_state:
            if os.path.exists(ICRON_CACHE_FILE):
                try:
                    with open(ICRON_CACHE_FILE, 'r', encoding='utf-8') as f:
                        cache_data = json.load(f)
                    cached_rows = cache_data.get('iscritti', [])
                    if cached_rows:
                        df_cached = pd.DataFrame(cached_rows)
                        df_cached['PETT'] = df_cached['PETT'].astype(str).str.strip().str.replace('.0', '', regex=False)
                        st.session_state['df_iscritti'] = df_cached
                        st.session_state['icron_id_loaded'] = cache_data.get('id_gara', '')
                except Exception:
                    pass



        # ── 3-button navigation ────────────────────────────────────────────
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

        # ════════════════════════════════════════════════════════════════════
        # SECTION 1 – CARICA GARA
        # ════════════════════════════════════════════════════════════════════
        if section == 'carica':
            st.markdown("#### 📁 Carica Gara")
            source_choice = st.radio(
                "Sorgente",
                ["🌐 Scarica da ICRON", "📄 Carica CSV locale"],
                horizontal=True, key="source_choice"
            )

            if source_choice == "🌐 Scarica da ICRON":
                cached_id = st.session_state.get('icron_id_loaded', '')
                id_gara = st.text_input(
                    "ID Gara ICRON",
                    placeholder="Es. 20264691",
                    help="L'ID è l'ultima parte dell'URL ICRON",
                    key="icron_id_value",
                    value=cached_id
                )
                col_btn1, col_btn2 = st.columns(2)
                load_btn  = col_btn1.button("⬇️ Carica Iscritti", use_container_width=True)
                clear_btn = col_btn2.button("🔄 Ricarica da ICRON", use_container_width=True)

                # Auto-show if cache already loaded
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
                                    with open(ICRON_CACHE_FILE, 'w', encoding='utf-8') as f:
                                        json.dump({'id_gara': id_gara, 'iscritti': df_icron.to_dict(orient='records')}, f)
                                    st.success(f"✅ Caricati **{len(df_icron)}** iscritti — *salvati in memoria permanente*")
                                    st.session_state['tab_section'] = 'elenco'
                                    st.rerun()
                            except Exception as e:
                                st.error(f"Errore: {e}")
                    else:
                        st.warning("Inserisci un ID gara.")

            else:  # CSV
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

        # ════════════════════════════════════════════════════════════════════
        # SECTION 2 – ELENCO ISCRITTI
        # ════════════════════════════════════════════════════════════════════
        elif section == 'elenco':
            st.markdown("#### 👥 Elenco Iscritti")
            if df_iscritti is None or df_iscritti.empty:
                st.info("Nessuna gara caricata. Vai su **📁 Carica Gara** per cominciare.")
            else:
                # Build display list: NOME COGNOME merged, ordered by PETT
                df_display = df_iscritti.copy()
                df_display['ATLETA'] = (df_display.get('COGNOME', '').astype(str).str.strip() + ' '
                                        + df_display.get('NOME', '').astype(str).str.strip()).str.strip()
                df_display['_PETT_NUM'] = pd.to_numeric(df_display['PETT'], errors='coerce')
                df_sorted = df_display.sort_values('_PETT_NUM').reset_index(drop=True)

                # Filter bar
                filter_q = st.text_input("🔎 Filtra…", placeholder="Cognome, nome o pettorale", key="elenco_filter")
                if filter_q:
                    q = filter_q.strip().lower()
                    mask = pd.Series([False] * len(df_sorted), index=df_sorted.index)
                    for col in ['ATLETA', 'PETT']:
                        if col in df_sorted.columns:
                            mask |= df_sorted[col].astype(str).str.lower().str.contains(q, na=False)
                    df_sorted = df_sorted[mask].reset_index(drop=True)

                st.caption(f"{len(df_sorted)} iscritti — clicca su una riga per aprire la scheda atleta")

                # CSS: strip button chrome so rows look like a plain table
                st.markdown("""
<style>
.row-table div[data-testid="stButton"] > button {
    background: transparent !important;
    border: none !important;
    border-bottom: 1px solid rgba(128,128,128,0.2) !important;
    border-radius: 0 !important;
    box-shadow: none !important;
    color: inherit !important;
    font-size: 0.9rem !important;
    font-weight: normal !important;
    padding: 5px 2px !important;
    text-align: left !important;
    width: 100% !important;
    transition: background 0.12s, color 0.12s;
}
.row-table div[data-testid="stButton"] > button:hover {
    background: rgba(76,175,80,0.10) !important;
    color: #4caf50 !important;
    cursor: pointer !important;
}
</style><div class="row-table">
""", unsafe_allow_html=True)

                # Header row
                h1, h2, h3, h4 = st.columns([1, 4, 2, 5])
                h1.markdown('<span style="font-weight:700;font-size:0.78rem;color:#888;text-transform:uppercase">Pett.</span>', unsafe_allow_html=True)
                h2.markdown('<span style="font-weight:700;font-size:0.78rem;color:#888;text-transform:uppercase">Atleta</span>', unsafe_allow_html=True)
                h3.markdown('<span style="font-weight:700;font-size:0.78rem;color:#888;text-transform:uppercase">Cat.</span>', unsafe_allow_html=True)
                h4.markdown('<span style="font-weight:700;font-size:0.78rem;color:#888;text-transform:uppercase">Società</span>', unsafe_allow_html=True)
                st.markdown("<hr style='margin:2px 0 0 0;border-color:rgba(128,128,128,0.4)'>", unsafe_allow_html=True)



                for i, ath in df_sorted.iterrows():
                    pv = str(int(ath['_PETT_NUM'])) if not pd.isna(ath.get('_PETT_NUM')) else str(ath.get('PETT', ''))
                    c1, c2, c3, c4 = st.columns([1, 4, 2, 5])
                    c1.markdown(f"<span style='font-size:0.9rem'><b>{pv}</b></span>", unsafe_allow_html=True)
                    if c2.button(str(ath.get('ATLETA', '')), key=f"erow_{i}", use_container_width=True):
                        m = df_iscritti[df_iscritti['PETT'] == pv]
                        if not m.empty:
                            popup_atleta(m.iloc[0].to_dict())
                    c3.markdown(f"<span style='font-size:0.9rem'>{ath.get('CATEGORIA','')}</span>", unsafe_allow_html=True)
                    c4.markdown(f"<span style='font-size:0.9rem'>{ath.get('SOCIETA','')}</span>", unsafe_allow_html=True)

                st.markdown("</div>", unsafe_allow_html=True)


        # ════════════════════════════════════════════════════════════════════
        # SECTION 3 – CERCA ATLETA
        # ════════════════════════════════════════════════════════════════════
        elif section == 'cerca':
            st.markdown("#### 🔍 Cerca Atleta")
            if df_iscritti is None or df_iscritti.empty:
                st.info("Nessuna gara caricata. Vai su **📁 Carica Gara** per cominciare.")
            else:
                sc1, sc2 = st.columns(2)
                pett_input = sc1.text_input("🏅 Pettorale", placeholder="Es. 123", key="search_pett")
                nome_input = sc2.text_input("👤 Nome o Cognome", placeholder="Es. Rossi", key="search_nome")

                cerca_btn = st.button("🔍 Cerca", use_container_width=True, type="primary")

                if cerca_btn or pett_input or nome_input:
                    found_row = None

                    if pett_input:
                        match = df_iscritti[df_iscritti['PETT'] == str(pett_input).strip()]
                        if not match.empty:
                            found_row = match.iloc[0].to_dict()
                        else:
                            st.warning(f"Nessun atleta con pettorale **{pett_input}**.")

                    elif nome_input:
                        q = nome_input.strip().lower()
                        mask = pd.Series([False] * len(df_iscritti), index=df_iscritti.index)
                        for col in ['COGNOME', 'NOME']:
                            if col in df_iscritti.columns:
                                mask |= df_iscritti[col].astype(str).str.lower().str.contains(q, na=False)
                        results = df_iscritti[mask]

                        if results.empty:
                            st.warning(f"Nessun atleta trovato con '{nome_input}'.")
                        elif len(results) == 1:
                            found_row = results.iloc[0].to_dict()
                        else:
                            st.info(f"Trovati **{len(results)}** atleti. Clicca su una riga.")
                            df_res = results.copy()
                            df_res['ATLETA'] = (df_res.get('COGNOME','').astype(str).str.strip() + ' '
                                                + df_res.get('NOME','').astype(str).str.strip()).str.strip()
                            df_res['_PETT_NUM'] = pd.to_numeric(df_res['PETT'], errors='coerce')
                            df_res_sorted = df_res.sort_values('_PETT_NUM').reset_index(drop=True)
                            show_c = [c for c in ['PETT','ATLETA','CATEGORIA','SOCIETA'] if c in df_res_sorted.columns]

                            if 'cerca_key' not in st.session_state:
                                st.session_state['cerca_key'] = 0

                            sel2 = st.dataframe(
                                df_res_sorted[show_c],
                                use_container_width=True,
                                on_select="rerun",
                                selection_mode="single-row",
                                key=f"cerca_results_{st.session_state['cerca_key']}",
                                column_config={"PETT": st.column_config.NumberColumn("Pett.", format="%d")}
                            )
                            if sel2 and sel2.selection and sel2.selection.rows:
                                i2 = sel2.selection.rows[0]
                                p2 = str(int(df_res_sorted.iloc[i2]['_PETT_NUM'])) \
                                    if not pd.isna(df_res_sorted.iloc[i2]['_PETT_NUM']) else df_res_sorted.iloc[i2]['PETT']
                                m2 = df_iscritti[df_iscritti['PETT'] == p2]
                                if not m2.empty:
                                    found_row = m2.iloc[0].to_dict()

                    if found_row:
                        st.session_state['cerca_key'] = st.session_state.get('cerca_key', 0) + 1
                        popup_atleta(found_row)


if __name__ == "__main__":
    main()

