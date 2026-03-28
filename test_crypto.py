import base64
import urllib.parse

def decode_tessera(encoded_str):
    key = b"3gabbo83"
    try:
        encoded_str = urllib.parse.unquote(encoded_str)
        encoded_str += "=" * ((4 - len(encoded_str) % 4) % 4)
        dec_bytes = base64.b64decode(encoded_str)
        tessera = ""
        for i in range(len(dec_bytes)):
            tessera += chr((dec_bytes[i] - key[i % len(key)]) % 256)
        return tessera
    except Exception as e:
        return ""

examples = [
    ("hKuRkpegamk%3D", "QD005126"),
    ("hKuRkpaobWo%3D", "QD004957"),
    ("g6iRkpaoamU%3D", "?") # Leo Paglione
]

for enc, plain in examples:
    decoded = decode_tessera(enc)
    print(f"URL: {enc} -> Expected: {plain} -> Decoded: {decoded}")
