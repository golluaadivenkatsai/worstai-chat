import urllib.request
import json
import sys

url = "http://localhost:11434/api/generate"
payload = {
    "model": "gemma4:26b",
    "prompt": "hi",
    "stream": False
}

req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), method='POST')
req.add_header('Content-Type', 'application/json')

try:
    response = urllib.request.urlopen(req, timeout=10)
    print("SUCCESS")
    print(response.read().decode('utf-8')[:200])
except Exception as e:
    print(f"FAILED: {e}")
    if hasattr(e, 'read'):
        print(e.read().decode('utf-8'))
