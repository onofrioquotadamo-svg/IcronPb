"""
app_scraper.py — FIDAL Scraper Globale (Società/Regioni)
Avvio: streamlit run app_scraper.py
"""

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

st.set_page_config(page_title="FIDAL Scraper Globale", page_icon="🔍", layout="wide")

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


def hms_to_seconds(t_str):
    t_str = t_str.lower().replace('h', ':')
    parts = t_str.split(':')
    try:
        if len(parts) == 3:
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
        elif len(parts) == 2:
            return float(parts[0]) * 60 + float(parts[1])
        return float(parts[0])
    except Exception:
        return 999999


@st.cache_data(ttl=3600 * 24)
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


@st.cache_data(ttl=3600 * 24)
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
    except Exception:
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
    except Exception:
        return []


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
    except Exception:
        return None, None, None, None, None


def process_athlete_task(ath_req, session):
    soc, ath, distance_keywords, selected_year, update_mode, existing_athletes, has_csv, gender_cat_include = ath_req
    ath_url = ath['url']
    if has_csv and ath_url in existing_athletes:
        if "Solo Nuovi Atleti" in update_mode:
            return "skipped", existing_athletes[ath_url]
    specialty, perf, date, loc, cat = extract_perf(ath_url, distance_keywords, selected_year, session)
    if not perf:
        return "empty", None
    if gender_cat_include and cat:
        cat_upper = str(cat).upper().strip()
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


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    st.title("🔍 FIDAL Scraper Globale — Società/Regioni")
    st.markdown("Estrai i Primati Personali (PB) o i Migliori Risultati Stagionali (SB) degli atleti. *(Multithreading supportato)*")

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
                prog.progress((idx + 1) / len(regions), text=f"Caricamento società: {r['name']}")
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

    cat_atleti_option = st.selectbox("Filtra Categoria Atleti da ricercare", [
        "Tutti i tesserati (Giovanili + Assoluti + Master)",
        "Solo Giovanili",
        "Solo Assoluti/Master"
    ])

    if distance_option == "10km su Strada":
        distance_keywords = ['10 km', '10km', 'strada km 10', 'strada 10']
    elif distance_option == "10000m su Pista":
        distance_keywords = ['10.000', '10000m', '10000 mt', '10000 pista']
    elif distance_option == "Maratona (42km)":
        distance_keywords = ['maratona']
    else:
        distance_keywords = ['mezza maratona', 'maratonina', 'mezza']

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
                st.error("Il CSV non contiene le colonne 'Link Atleta' e 'Risultato'.")
        except Exception as e:
            st.error(f"Errore nella lettura del CSV: {e}")

    if st.button("Cerca e Scarica (Avanzato)"):
        societies_to_scrape = all_societies
        if selected_prov != "Tutte le province":
            societies_to_scrape = [s for s in societies_to_scrape if s['prov'] == selected_prov]
        if selected_soc != "Tutte le società":
            societies_to_scrape = [s for s in societies_to_scrape if s['name'] == selected_soc]

        with st.status("Ottimizzazione Estrazioni in corso...", expanded=True) as status:
            st.write(f"Trovate {len(societies_to_scrape)} società da processare.")
            master_session = requests.Session()
            st.write("📌 Fase 1: Recapito Atleti...")
            prep_prog = st.progress(0)
            athletes_to_scrape = []
            for i, soc in enumerate(societies_to_scrape):
                prep_prog.progress((i + 1) / len(societies_to_scrape), text=f"Recapito atleti società {i+1}/{len(societies_to_scrape)}")
                aths = get_athletes_for_society(soc['url'], cat_atleti_option, master_session)
                for ath in aths:
                    athletes_to_scrape.append((soc, ath, distance_keywords, selected_year, update_mode, existing_athletes, uploaded_file is not None, gender_cat_include))

            st.write(f"✅ Identificati {len(athletes_to_scrape)} atleti totali da scansionare.")
            st.write("🚀 Fase 2: Estrazione Risultati in Multithreading...")
            all_data = []
            preserved_data = []
            ext_prog = st.progress(0)
            ath_progress = st.empty()
            new_records_count = 0
            updated_records_count = 0
            MAX_WORKERS = 5
            processed = 0

            with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
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
                        processed += 1
                        ath_progress.text(f"  Elaborati: {processed}/{len(athletes_to_scrape)} atleti...")
                        ext_prog.progress(processed / len(athletes_to_scrape))
                        if processed % 50 == 0 and processed > 0:
                            pd.DataFrame(all_data + preserved_data).to_csv("backup_fidal.csv", index=False)
                    except Exception as exc:
                        st.error(f"Errore nell'atleta {req[1]['name']}: {exc}")

            status.update(label="Estrazione completata!", state="complete")
            st.session_state['all_data'] = all_data + preserved_data
            st.session_state['new_count'] = new_records_count
            st.session_state['upd_count'] = updated_records_count
            st.session_state['had_csv'] = (uploaded_file is not None)

            if len(all_data + preserved_data) > 0:
                pd.DataFrame(all_data + preserved_data).to_csv("backup_fidal.csv", index=False)

    if 'all_data' in st.session_state and st.session_state['all_data']:
        df = pd.DataFrame(st.session_state['all_data'])
        if st.session_state.get('had_csv', False):
            nc = st.session_state.get('new_count', 0)
            uc = st.session_state.get('upd_count', 0)
            if nc == 0 and uc == 0:
                st.warning("⚠️ Nessun dato aggiornato per questi filtri.")
            else:
                st.success(f"Dati aggiornati! {nc} nuovi atleti e {uc} record migliorati.")
        else:
            st.success(f"Trovati {len(df)} atleti con il risultato richiesto!")
        st.dataframe(df)

        file_name = f"fidal_risultati_{selected_region_name.lower().replace(' ', '_')}"
        if selected_prov != "Tutte le province":
            file_name += f"_{selected_prov.lower()}"
        file_name += f"_{selected_year if selected_year != 'Tutti gli anni (Miglior Risultato Assoluto - PB)' else 'pb'}.csv"
        st.download_button("Scarica CSV", df.to_csv(index=False).encode('utf-8'), file_name, "text/csv")

        if os.path.exists("backup_fidal.csv"):
            st.info("Backup automatico salvato in backup_fidal.csv")


if __name__ == "__main__":
    main()
