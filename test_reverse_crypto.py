import requests
from bs4 import BeautifulSoup
import base64
import urllib.parse

def encode_tessera(tessera_str):
    key = b"3gabbo83"
    enc_bytes = bytearray()
    for i in range(len(tessera_str)):
        enc_bytes.append((ord(tessera_str[i]) + key[i % len(key)]) % 256)
    
    b64 = base64.b64encode(enc_bytes).decode('utf-8')
    return urllib.parse.quote(b64)

test_tessera = "QD005126" # Francesco Ritrovato
encoded = encode_tessera(test_tessera)
print(f"Plain: {test_tessera} -> Encoded: {encoded}")
print(f"Expect: hKuRkpegamk%3D")

url = f"https://www.fidal.it/atleta/x/{encoded}"
print(f"Fetching: {url}")
resp = requests.get(url, timeout=10)
soup = BeautifulSoup(resp.text, 'html.parser')
h1 = soup.find('h1')
if h1:
    print("Found H1:", h1.get_text(strip=True))
else:
    print("No H1 found. Page might be invalid.")
    
url2 = f"https://www.fidal.it/atleta.php?id={encoded}"
print(f"Fetching fallback: {url2}")
resp2 = requests.get(url2, timeout=10)
soup2 = BeautifulSoup(resp2.text, 'html.parser')
h1_2 = soup2.find('h1')
if h1_2:
    print("Found fallback H1:", h1_2.get_text(strip=True))
