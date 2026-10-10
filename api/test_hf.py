import http.server
import json
import urllib.request

class handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        result = {}
        try:
            req = urllib.request.Request(
                'https://api-inference.huggingface.co/models/HuggingFaceH4/zephyr-7b-beta',
                headers={'Content-Type': 'application/json'},
                data=json.dumps({"inputs": "Say hi"}).encode()
            )
            resp = urllib.request.urlopen(req, timeout=10)
            result['hf'] = json.loads(resp.read())
        except Exception as e:
            result['hf_error'] = str(e)
            
        body = json.dumps(result).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(body)
