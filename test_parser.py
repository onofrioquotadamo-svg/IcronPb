"""
Quick test of extract_all_pbs on a real FIDAL athlete page
Run: python test_parser.py
"""
import requests
from bs4 import BeautifulSoup

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

def extract_all_pbs(athlete_url):
    resp = requests.get(athlete_url, timeout=10)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, 'html.parser')
    pb_data = []
    recent_bests = {}
    perf_dates = {}

    for table in soup.find_all('table'):
        headers = [th.get_text(strip=True).lower() for th in table.find_all('th')]
        if not headers and table.find('tr'):
            headers = [td.get_text(strip=True).lower() for td in table.find('tr').find_all('td')]

        is_pb_table = (any('specialit' in h for h in headers) or
                       any('prestazione' in h or 'gara' in h for h in headers) or
                       table.parent.get('id') == 'tab3')
        first_h = headers[0].lower().strip() if headers else ''
        is_hist_table = first_h in ('anno', 'anno/data')
        is_pb_summary = is_pb_table and first_h not in ('anno', 'anno/data', '')

        print(f"TABLE: first_h='{first_h}' | is_pb_table={is_pb_table} | is_hist={is_hist_table} | is_pb_summary={is_pb_summary}")

        if is_pb_summary:
            for tr in table.find_all('tr'):
                cells = tr.find_all(['td', 'th'])
                if not cells or len(cells) < 3:
                    continue
                specialty = cells[0].get_text(strip=True)
                if not specialty or specialty.lower() in ('gara', 'specialità', 'specialita'):
                    continue
                perf = cells[2].get_text(strip=True) if len(cells) > 2 else ""
                year = cells[4].get_text(strip=True) if len(cells) > 4 else ""
                loc  = cells[5].get_text(strip=True) if len(cells) > 5 else ""
                pb_data.append({"Specialità": specialty, "Prestazione": perf, "Data": year, "Luogo": loc})

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
                key = (spec.lower(), perf_cell)
                if key not in perf_dates:
                    perf_dates[key] = full_date
                if year_cell in ['2025', '2026']:
                    sec = hms_to_seconds(perf_cell)
                    if spec and sec < 999999:
                        prev = recent_bests.get(spec)
                        if prev is None or sec < prev[0]:
                            recent_bests[spec] = (sec, perf_cell, loc_cell, year_cell, full_date)

    for pb in pb_data:
        key = (pb.get('Specialità', '').lower(), pb.get('Prestazione', ''))
        if key in perf_dates:
            pb['Data'] = perf_dates[key]

    return pb_data, recent_bests

# Test with a real athlete
url = "https://www.fidal.it/atleta/Marco-Ugolini/faiRkpKgbmo="
print(f"\nTesting: {url}\n" + "="*60)
pbs, recent = extract_all_pbs(url)
print(f"\n✅ PB trovati: {len(pbs)}")
for p in pbs[:5]:
    print(f"  {p['Specialità']:30s}  {p['Prestazione']:10s}  {p['Data']:15s}  {p['Luogo']}")
print(f"\n✅ Recent bests 2025-26: {len(recent)}")
for k, v in list(recent.items())[:3]:
    print(f"  {k}: {v[1]} @ {v[2]} ({v[4] if len(v)>4 else v[3]})")
