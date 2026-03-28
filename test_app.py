import requests

url = 'https://www.fidal.it/atleta/Leo-Paglione/gqiRlZifbWs%3D'
print(f"Fetching {url}...")
resp = requests.get(url)

with open('athlete_dump.html', 'w', encoding='utf-8') as f:
    f.write(resp.text)
    
print("Saved to athlete_dump.html")


