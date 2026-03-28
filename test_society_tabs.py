import requests
from bs4 import BeautifulSoup

url = "https://www.fidal.it/societa/A-S-D-AMAT-ATLETICA-SERAFINI/AQ014"
resp = requests.get(url)
soup = BeautifulSoup(resp.text, 'html.parser')

print("Tab Map:")
for li in soup.find_all('li'):
    a = li.find('a', href=True)
    if a and a.get('href', '').startswith('#tab'):
        print(f"Tab name: {a.get_text(strip=True)} -> {a['href']}")

print("\nAthletes per tab:")
for div in soup.find_all('div', id=lambda x: x and x.startswith('tab')):
    athletes = [a for a in div.find_all('a', href=True) if '/atleta/' in a['href'] or 'atleta.php' in a['href']]
    print(f"--- {div.get('id')} --- : {len(athletes)} athletes")

