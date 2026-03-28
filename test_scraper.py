import requests
from bs4 import BeautifulSoup
import re

society_url = "https://www.fidal.it/societa/A-S-D-AMAT-ATLETICA-SERAFINI/AQ014"
resp = requests.get(society_url)
soup = BeautifulSoup(resp.text, 'html.parser')

print(f"Society Page Length: {len(resp.text)}")
# Find all tabs or lists of athletes. Let's see if there are links containing 'atleta/'
athlete_links = [a['href'] for a in soup.find_all('a', href=True) if 'atleta/' in a['href'] or 'atleta.php' in a['href']]
print(f"Found {len(athlete_links)} athlete links in the society page HTML")
if athlete_links:
    print(f"Sample athlete link: {athlete_links[0]}")
    # Now try to fetch the first athlete page and find 10000m or Mezza Maratona
    athlete_url = athlete_links[0]
    if athlete_url.startswith('/'):
        athlete_url = "https://www.fidal.it" + athlete_url
    elif not athlete_url.startswith('htt'):
        athlete_url = "https://www.fidal.it/" + athlete_url
    
    print(f"Fetching athlete URL: {athlete_url}")
    a_resp = requests.get(athlete_url)
    a_soup = BeautifulSoup(a_resp.text, 'html.parser')
    
    print(f"Athlete Page Length: {len(a_resp.text)}")
    for table in a_soup.find_all('table'):
        if 'Specialit' in table.get_text() or 'Prestazione' in table.get_text():
            print("--- PB TABLE FOUND ---")
            for tr in table.find_all('tr'):
                print(tr.get_text(separator=' | ', strip=True))

