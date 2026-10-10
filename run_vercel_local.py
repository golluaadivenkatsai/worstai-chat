import sys
import os
import urllib.request
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from api.index import handler
import http.server
import socketserver

PORT = 3000
PUBLIC_DIR = os.path.join(os.path.dirname(__file__), 'public')

class LocalHandler(handler):
    def do_GET(self):
        if self.path.startswith('/api/'):
            return super().do_GET()
        
        # Serve static files from public/
        if self.path == '/':
            self.path = '/index.html'
        
        filepath = os.path.join(PUBLIC_DIR, self.path.lstrip('/'))
        if os.path.exists(filepath) and os.path.isfile(filepath):
            try:
                with open(filepath, 'rb') as f:
                    content = f.read()
                self.send_response(200)
                if filepath.endswith('.html'): self.send_header('Content-Type', 'text/html; charset=utf-8')
                elif filepath.endswith('.css'): self.send_header('Content-Type', 'text/css')
                elif filepath.endswith('.js'): self.send_header('Content-Type', 'application/javascript')
                self.end_headers()
                self.wfile.write(content)
            except Exception as e:
                self.send_error(500, str(e))
        else:
            self.send_error(404, "File not found")

print(f"Starting fully fixed local server on http://localhost:{PORT}")
with socketserver.TCPServer(("", PORT), LocalHandler) as httpd:
    httpd.serve_forever()
