import requests
from bs4 import BeautifulSoup

url = "https://www.fidal.it/atleta/Leo-Paglione/g6iRkpaoamU%3D"
resp = requests.get(url)
soup = BeautifulSoup(resp.text, 'html.parser')

t_count = 0
for table in soup.find_all('table'):
    h = table.find_previous(['h1', 'h2', 'h3', 'h4'])
    print(f"Table {t_count} - Preceded by: {h.get_text() if h else 'None'}")
    for row in table.find_all('tr')[:2]:
        cells = row.find_all(['th', 'td'])
        if cells:
            print([c.get_text(strip=True) for c in cells])
    t_count += 1

