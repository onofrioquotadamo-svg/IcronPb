from app import extract_pb

url = "https://www.fidal.it/atleta/Leo-Paglione/g6iRkpaoamU%3D"
keywords_10k = ['10.000', '10000', '10 km', '10km', 'strada km 10']
keywords_hm = ['mezza maratona', 'maratonina', 'mezza']

print("Testing 10K...")
spec, pb = extract_pb(url, keywords_10k)
print(f"Result: {spec} - {pb}")

print("Testing HM...")
spec, pb = extract_pb(url, keywords_hm)
print(f"Result: {spec} - {pb}")
