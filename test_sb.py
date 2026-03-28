import requests
from bs4 import BeautifulSoup
import re

def hms_to_seconds(t_str):
    # parses MM:SS.ms or HhMM:SS or HH:MM:SS
    t_str = t_str.lower().replace('h', ':')
    parts = t_str.split(':')
    try:
        if len(parts) == 3: # H:M:S
            return float(parts[0])*3600 + float(parts[1])*60 + float(parts[2])
        elif len(parts) == 2: # M:S
            return float(parts[0])*60 + float(parts[1])
        return float(parts[0])
    except:
        return 999999

def extract_sb(athlete_url, distance_keywords, target_year):
    try:
        resp = requests.get(athlete_url, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        best_perf = None
        best_time_sec = 999999
        best_date = None
        best_loc = None
        best_spec = None
        
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
                        if year == str(target_year):
                            perf = cells[6].get_text(strip=True)
                            loc = cells[8].get_text(strip=True)
                            date_str = f"{cells[1].get_text(strip=True)}/{year}"
                            
                            t_sec = hms_to_seconds(perf)
                            if t_sec < best_time_sec:
                                best_time_sec = t_sec
                                best_perf = perf
                                best_loc = loc
                                best_date = date_str
                                best_spec = spec_name
                                
        return best_spec, best_perf, best_date, best_loc
    except Exception as e:
        print("Error:", e)
        return None, None, None, None

url = "https://www.fidal.it/atleta/Leo-Paglione/g6iRkpaoamU%3D"
keywords_10k = ['10.000', '10000', '10 km', '10km', 'strada km 10']
keywords_hm = ['mezza maratona', 'maratonina', 'mezza']

print("2021 10K SB:", extract_sb(url, keywords_10k, '2021'))
print("2024 HM SB:", extract_sb(url, keywords_hm, '2024'))
print("2023 HM SB (no perf):", extract_sb(url, keywords_hm, '2023'))
