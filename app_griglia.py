import streamlit as st
import pandas as pd
import concurrent.futures
import requests
import os
import io
from fpdf import FPDF
from fidal_utils import (
    fetch_from_icron, encode_tessera, extract_all_pbs, 
    hms_to_seconds, load_cache, save_cache, get_base64_logo
)

st.set_page_config(page_title="ICRON Virtual Start", page_icon="🏁", layout="wide")

def main():
    # CSS Premium
    # CSS Premium
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;700;900&display=swap');
        
        html, body, [data-testid="stAppViewContainer"] {
            font-family: 'Outfit', sans-serif !important;
            background-color: #0e1117 !important;
            color: white !important;
        }
        
        .grid-card {
            background: linear-gradient(135deg, rgba(255,255,255,0.05) 0%, rgba(255,255,255,0.02) 100%);
            border-radius: 12px; 
            border: 1px solid rgba(255,255,255,0.1);
            padding: 15px; 
            margin-bottom: 10px; 
            position: relative;
        }
        .rank-badge {
            position: absolute; right: 15px; top: 15px;
            font-size: 1.5rem; font-weight: 900; opacity: 0.3;
        }
        .rank-1 { border-left: 5px solid #ffd700; background: linear-gradient(90deg, rgba(255,215,0,0.1) 0%, transparent 100%); }
        .rank-2 { border-left: 5px solid #c0c0c0; background: linear-gradient(90deg, rgba(192,192,192,0.1) 0%, transparent 100%); }
        .rank-3 { border-left: 5px solid #cd7f32; background: linear-gradient(90deg, rgba(205,127,50,0.1) 0%, transparent 100%); }
        
        .bib { background: #4caf50; padding: 2px 8px; border-radius: 4px; font-weight: 700; font-size: 0.8rem; }
        .name { font-size: 1.1rem; font-weight: 700; margin-left: 8px; }
        .pb-val { font-size: 1.4rem; font-weight: 900; color: #4caf50; margin-top: 5px; }
        .stButton > button, .stDownloadButton > button {
            background-color: #4caf50 !important;
            color: white !important;
            border: none !important;
            border-radius: 8px !important;
            font-weight: 700 !important;
        }
        
        .stButton > button:hover, .stDownloadButton > button:hover {
            background-color: #45a049 !important;
            border: none !important;
        }
        
        h1, h2, h3, h4, h5, p, span, div {
            color: white !important;
        }
        
        .meta { color: #aaa !important; }
        
        /* Aggressive Dark Inputs */
        div[data-baseweb="input"], div[data-baseweb="select"], .stTextInput input, .stSelectbox [data-baseweb="select"] {
            background-color: #161b22 !important;
            color: white !important;
            border-radius: 8px !important;
            border: 1px solid rgba(255,255,255,0.1) !important;
        }
        
        /* Fix per la tabella dei risultati */
        div[data-testid="stDataFrame"] {
            background-color: #0e1117 !important;
        }
        
        label p {
            color: #4caf50 !important;
            font-weight: 700 !important;
        }
        </style>
    """, unsafe_allow_html=True)

    # Header con Logo (Metodo Base64 infallibile)
    logo_path = os.path.join(os.path.dirname(__file__), "icron_logo.png")
    b64_logo = get_base64_logo(logo_path)
    
    col_l, col_t = st.columns([1, 4])
    if b64_logo:
        col_l.markdown(f'<img src="data:image/png;base64,{b64_logo}" width="180">', unsafe_allow_html=True)
    else:
        col_l.warning("⚠️ Logo non trovato")
    
    col_t.title("ICRON Virtual Start")
    col_t.markdown("Generazione seeding professionale basato sui PB FIDAL.")

    col1, col2 = st.columns([2, 1])
    id_gara = col1.text_input("ID Gara (ICRON)", placeholder="es. 1234")
    distance_keywords = col2.selectbox("Distanza di riferimento per PB", [
        "10km Strada", "10000m Pista", "Mezza Maratona", "Maratona"
    ])

    keywords_map = {
        "10km Strada": ['10 km', '10km', 'strada km 10', 'strada 10'],
        "10000m Pista": ['10.000', '10000m', '10000 mt'],
        "Mezza Maratona": ['mezza maratona', 'maratonina', 'mezza'],
        "Maratona": ['maratona']
    }
    keys = keywords_map[distance_keywords]

    if 'persistent_cache' not in st.session_state:
        st.session_state['persistent_cache'] = load_cache()
    if 'new_cache_entries' not in st.session_state:
        st.session_state['new_cache_entries'] = {}

    if st.button("🚀 Genera Griglie di Partenza", type="primary", use_container_width=True) and id_gara:
        try:
            with st.status("Recupero iscritti...", expanded=True) as status:
                df_iscritti = fetch_from_icron(id_gara)
                if df_iscritti.empty:
                    st.error("Nessun iscritto trovato per questa gara.")
                    return
                
                st.write(f"Trovati {len(df_iscritti)} iscritti. Inizio recupero PBs...")
                
                processed_data = []
                cache = st.session_state['persistent_cache']
                
                def process_athlete(row):
                    tessera = str(row.get('TESSERA', '')).strip()
                    if not tessera: return None
                    
                    ath_url = f"https://www.fidal.it/atleta/x/{encode_tessera(tessera)}"
                    
                    # Smart Update Check
                    last_seen_date = cache.get(ath_url)
                    
                    pbs, recent_bests, current_activity = extract_all_pbs(ath_url)
                    
                    # Trova il miglior PB per la distanza scelta
                    best_time_sec = 999999
                    best_time_str = "-"
                    best_date = "-"
                    best_loc = "-"
                    
                    for pb in pbs:
                        spec = pb.get('Specialità', '').lower()
                        if any(k in spec for k in keys):
                            sec = hms_to_seconds(pb.get('Prestazione', ''))
                            if sec < best_time_sec:
                                best_time_sec = sec
                                best_time_str = pb.get('Prestazione', '')
                                best_date = pb.get('Data', '')
                                best_loc = pb.get('Luogo', '')

                    # Trova la miglior prestazione recente (SB 2025/2026)
                    best_sb_sec = 999999
                    best_sb_str = "-"
                    for spec_name, sb_info in recent_bests.items():
                        if any(k in spec_name.lower() for k in keys):
                            sec = sb_info[0]
                            if sec < best_sb_sec:
                                best_sb_sec = sec
                                best_sb_str = sb_info[1]
                    
                    return {
                        'PETT': row.get('PETT', ''),
                        'ATLETA': f"{row.get('COGNOME', '')} {row.get('NOME', '')}",
                        'SESSO': row.get('SESSO', 'M'),
                        'SOCIETA': row.get('SOCIETA', ''),
                        'CATEGORIA': row.get('CATEGORIA', ''),
                        'PB_SEC': best_time_sec,
                        'PB_STR': best_time_str,
                        'SB_STR': best_sb_str,
                        'DATA': best_date,
                        'LUOGO': best_loc,
                        'LAST_ACT': current_activity
                    }

                # Multithreading per velocità (ridotto a 5 per stabilità su Render)
                with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                    futures = [executor.submit(process_athlete, row) for _, row in df_iscritti.iterrows()]
                    pbar = st.progress(0)
                    for i, f in enumerate(concurrent.futures.as_completed(futures)):
                        res = f.result()
                        if res: 
                            processed_data.append(res)
                            if res['LAST_ACT']:
                                st.session_state['new_cache_entries'][f"https://www.fidal.it/atleta/x/{encode_tessera(res['PETT'])}"] = res['LAST_ACT']
                        pbar.progress((i + 1) / len(df_iscritti))
                
                status.update(label="Griglie generate!", state="complete")
                st.session_state['grid_data'] = pd.DataFrame(processed_data)
                st.session_state['dist_name'] = distance_keywords
                
                # Salva cache
                if st.session_state['new_cache_entries']:
                    st.session_state['persistent_cache'].update(st.session_state['new_cache_entries'])
                    save_cache(st.session_state['persistent_cache'])

        except Exception as e:
            st.error(f"Errore: {e}")

    if 'grid_data' in st.session_state:
        df = st.session_state['grid_data']
        df_m = df[df['SESSO'] == 'M'].sort_values('PB_SEC').reset_index(drop=True)
        df_f = df[df['SESSO'] == 'F'].sort_values('PB_SEC').reset_index(drop=True)

        st.markdown("---")
        col_pdf1, col_pdf2 = st.columns([3, 1])
        col_pdf1.subheader("📤 Esportazione Report")
        
        pdf_bytes = generate_pdf(df_m.head(10), df_f.head(10), st.session_state.get('dist_name', 'Gara'))
        col_pdf2.download_button(
            label="📄 Scarica PDF Top 10",
            data=pdf_bytes,
            file_name="Top10_Griglia_Partenza.pdf",
            mime="application/pdf",
            type="primary",
            use_container_width=True
        )

        t1, t2 = st.tabs(["🚹 Uomini", "🚺 Donne"])
        
        with t1:
            render_grid_and_table(df_m)
            
        with t2:
            render_grid_and_table(df_f)

def generate_pdf(df_m, df_f, dist_name):
    pdf = FPDF()
    pdf.add_page()
    
    # Header
    pdf.set_fill_color(255, 255, 255) # Bianco per far risaltare il logo
    pdf.rect(0, 0, 210, 40, 'F')
    
    try:
        pdf.image("icron_logo.png", x=10, y=10, w=40)
    except: pass
    
    pdf.set_font("helvetica", "B", 24)
    pdf.set_text_color(0, 102, 204) # Blu ICRON-ish
    pdf.set_xy(60, 10)
    pdf.cell(140, 15, "ICRON VIRTUAL START", ln=True, align="L")
    pdf.set_font("helvetica", "I", 10)
    pdf.set_xy(60, 22)
    pdf.cell(140, 10, f"Seeding basato su PB FIDAL - Distanza: {dist_name}", ln=True, align="L")
    
    pdf.ln(20)
    pdf.set_text_color(0, 0, 0)
    
    def add_section(title, data):
        pdf.set_font("helvetica", "B", 14)
        pdf.set_text_color(76, 175, 80)
        pdf.cell(190, 10, title, ln=True)
        pdf.set_text_color(0, 0, 0)
        pdf.ln(5)
        
        # Table Header
        pdf.set_font("helvetica", "B", 9)
        pdf.set_fill_color(240, 240, 240)
        pdf.cell(10, 8, "Pos", 1, 0, 'C', True)
        pdf.cell(10, 8, "Pett", 1, 0, 'C', True)
        pdf.cell(50, 8, "Atleta", 1, 0, 'L', True)
        pdf.cell(22, 8, "PB", 1, 0, 'C', True)
        pdf.cell(22, 8, "SB 25/26", 1, 0, 'C', True) # Nuova colonna
        pdf.cell(22, 8, "Data PB", 1, 0, 'C', True)
        pdf.cell(45, 8, "Società", 1, 1, 'L', True)
        
        # Table Body
        pdf.set_font("helvetica", "", 8)
        for i, r in data.iterrows():
            pdf.cell(10, 8, f"#{i+1}", 1, 0, 'C')
            pdf.cell(10, 8, str(r['PETT']), 1, 0, 'C')
            pdf.cell(50, 8, str(r['ATLETA'])[:25], 1, 0, 'L')
            pdf.cell(22, 8, str(r['PB_STR']), 1, 0, 'C')
            pdf.cell(22, 8, str(r['SB_STR']), 1, 0, 'C')
            pdf.cell(22, 8, str(r['DATA']), 1, 0, 'C')
            pdf.cell(45, 8, str(r['SOCIETA'])[:22], 1, 1, 'L')
        pdf.ln(10)

    add_section("TOP 10 UOMINI", df_m)
    add_section("TOP 10 DONNE", df_f)
    
    pdf.set_font("helvetica", "I", 8)
    pdf.set_text_color(128, 128, 128)
    pdf.cell(190, 10, f"Generato il {pd.Timestamp.now().strftime('%d/%m/%Y %H:%M')} - FIDAL Scraper Suite", ln=True, align="R")
    
    return bytes(pdf.output())

def render_grid_and_table(df_view):
    if df_view.empty:
        st.info("Nessun atleta trovato per questa categoria.")
        return
    
    # Riassunto Statistico
    col_a, col_b = st.columns(2)
    col_a.metric("Iscritti", len(df_view))
    avg_sec = df_view[df_view['PB_SEC'] < 999999]['PB_SEC'].mean()
    if not pd.isna(avg_sec):
        m, s = divmod(int(avg_sec), 60)
        col_b.metric("Tempo Medio PB", f"{m:02d}:{s:02d}")

    # Tabella Dettagliata (Richiesta Utente)
    st.subheader("📋 Tabella Riepilogativa")
    # Aggiunta colonna SB alla tabella
    df_table = df_view[['PETT', 'ATLETA', 'PB_STR', 'SB_STR', 'DATA', 'LUOGO', 'SOCIETA', 'CATEGORIA']].copy()
    df_table.columns = ['Pett.', 'Atleta', 'Risultato PB', 'SB (25/26)', 'Data PB', 'Luogo PB', 'Società', 'Cat.']
    st.dataframe(df_table, use_container_width=True, hide_index=True)

    # Grid Cards
    st.subheader("🏎️ Griglia Visuale (Top 10)")
    for i, r in df_view.head(10).iterrows():
        rank = i + 1
        rank_class = f"rank-{rank}" if rank <= 3 else ""
        badge = "🥇" if rank == 1 else "🥈" if rank == 2 else "🥉" if rank == 3 else f"#{rank}"
        
        st.markdown(f"""
        <div class="grid-card {rank_class}">
            <div class="rank-badge">{badge}</div>
            <div>
                <span class="bib">#{r['PETT']}</span>
                <span class="name">{r['ATLETA']}</span>
            </div>
            <div style="display:flex; gap:20px; align-items:center; margin-top:5px;">
                <div>
                    <div style="font-size:0.75rem; color:#888;">Primato (PB)</div>
                    <div class="pb-val">{r['PB_STR'] if r['PB_STR'] != '-' else 'Senza PB'}</div>
                </div>
                <div>
                    <div style="font-size:0.75rem; color:#888;">Stagionale (SB 25/26)</div>
                    <div class="pb-val" style="color:#ffab40;">{r['SB_STR'] if r['SB_STR'] != '-' else '-'}</div>
                </div>
            </div>
            <div class="meta">{r['CATEGORIA']} | {r['SOCIETA']}</div>
            <div class="meta" style="color:#4caf50; font-weight:bold;">📍 {r['LUOGO']} ({r['DATA']})</div>
        </div>
        """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
