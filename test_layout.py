import requests
from bs4 import BeautifulSoup

url = "https://www.fidal.it/atleta/Leo-Paglione/g6iRkpaoamU%3D"
resp = requests.get(url)
soup = BeautifulSoup(resp.text, 'html.parser')

distance_keywords = ['10000', 'maratonina', '10 km']
for table in soup.find_all('table'):
    headers = [th.get_text(strip=True).lower() for th in table.find_all('th')]
    if not headers and table.find('tr'):
        headers = [td.get_text(strip=True).lower() for td in table.find('tr').find_all('td')]
    
    if any('specialit' in h for h in headers) or any('prestazione' in h for h in headers) or table.parent.get('id') == 'tab3':
        for tr in table.find_all('tr'):
            cells = tr.find_all(['td', 'th'])
            if not cells or len(cells) < 3:
                continue
            specialty = cells[0].get_text(strip=True)
            row_text = specialty.lower()
            if any(k.lower() in row_text for k in distance_keywords):
                print("RAW ROW:", [c.get_text(strip=True) for c in cells])
