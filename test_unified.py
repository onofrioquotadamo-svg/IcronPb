import requests
from bs4 import BeautifulSoup

def hms_to_seconds(t_str):
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

def extract_perf(athlete_url, distance_keywords, target_year="Tutti"):
    try:
        resp = requests.get(athlete_url, timeout=10)
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
                        
                        if target_year == "Tutti" or str(target_year) == year:
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
        print("Error:", e)
        return None, None, None, None, None

url = "https://www.fidal.it/atleta/Leo-Paglione/g6iRkpaoamU%3D"
keywords_10k = ['10.000', '10000', '10 km', '10km', 'strada km 10']
keywords_hm = ['mezza maratona', 'maratonina', 'mezza']

print("ALL YEARS 10K PB:", extract_perf(url, keywords_10k))
print("2021 10K SB:", extract_perf(url, keywords_10k, '2021'))
print("ALL YEARS HM PB:", extract_perf(url, keywords_hm))
