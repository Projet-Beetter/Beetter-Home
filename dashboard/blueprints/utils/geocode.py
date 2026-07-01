import urllib.request, urllib.parse, json

def geocode(street, city, postal_code):
    parts = [p for p in [street, postal_code, city] if p]
    if not parts:
        return None, None
    try:
        params = urllib.parse.urlencode({'q': ', '.join(parts), 'format': 'json', 'limit': 1})
        url = f'https://nominatim.openstreetmap.org/search?{params}'
        req = urllib.request.Request(url, headers={'User-Agent': 'Beetter/1.0 (mel.tsma@gmail.com)'})
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read())
        if data:
            return float(data[0]['lat']), float(data[0]['lon'])
    except Exception:
        pass
    return None, None