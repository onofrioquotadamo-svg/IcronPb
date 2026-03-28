import requests
from bs4 import BeautifulSoup
import json

event_id = "20264691"
url = f"https://www.icron.it/newgo/api/iscrizioni/elenco/{event_id}"
url2 = f"https://www.icron.it/api/iscrizioni?id_gara={event_id}"

# Try to fetch main page to find JS config
main_url = f"https://www.icron.it/newgo/#/evento/{event_id}"
resp = requests.get(main_url)
print("Main request length:", len(resp.text))
if "api" in resp.text:
    print("Found 'api' in main page source!")
    
# Let's try to query some common ICRON API endpoints
endpoints = [
    f"https://www.icron.it/newgo/api/events/{event_id}/participants",
    f"https://www.icron.it/services/api/events/{event_id}/participants",
    f"https://www.icron.it/api/events/{event_id}/participants",
    f"https://www.icron.it/newgo/api/event/{event_id}",
    f"https://www.icron.it/newgo/rest/events/{event_id}/participants",
]

for ep in endpoints:
    try:
        r = requests.get(ep, timeout=5)
        print(f"Endpoint: {ep} - Status: {r.status_code}")
        if r.status_code == 200:
            print(r.text[:200])
    except Exception as e:
        print(f"Failed {ep}: {e}")
