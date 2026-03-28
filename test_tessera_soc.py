import requests
from bs4 import BeautifulSoup

url = "https://www.fidal.it/societa/A-S-D-AMAT-ATLETICA-SERAFINI/AQ014"
resp = requests.get(url)
soup = BeautifulSoup(resp.text, 'html.parser')

print("Looking at tables in society page...")
for div in soup.find_all('div', id=lambda x: x and x.startswith('tab')):
    print(f"\n--- {div.get('id')} ---")
    table = div.find('table')
    if table:
        headers = [th.get_text(strip=True) for th in table.find_all('th')]
        print("Headers:", headers)
        for row in table.find_all('tr')[:2]:
            cells = [td.get_text(strip=True) for td in row.find_all('td')]
            if cells:
                print("Row:", cells)
    else:
        print("No table found")
