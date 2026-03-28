import requests
from bs4 import BeautifulSoup

url = "https://www.fidal.it/atleta/Leo-Paglione/g6iRkpaoamU%3D"
resp = requests.get(url)
soup = BeautifulSoup(resp.text, 'html.parser')

print("--- Text in upper sections ---")
# Try to find common intro sections like header or divs
for h1 in soup.find_all('h1'):
    print("H1:", h1.get_text(strip=True))
    parent = h1.parent
    print("Parent text:", parent.get_text(separator='|', strip=True))

import re

print("Starting regex search for tessera pattern (e.g., AB123456)...")
text = soup.get_text()
matches = re.finditer(r'\b[A-Z]{2}\d{5,6}\b', text)
for m in matches:
    print("Found potential Tessera:", m.group())
    
print("Also searching for 'codice' or 'tess' in all text...")
for line in text.split('\n'):
    if 'codice' in line.lower() or 'tess' in line.lower():
        print("Matching line:", line.strip())

