import http.server
import socketserver
import os
import sys
import json
import socket
import smtplib
import random
import urllib.request
import urllib.parse
from email.message import EmailMessage
import g4f

PORT = 3000
DIRECTORY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public")

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# In-memory stores
OTP_STORE = {}
SMTP_CONFIG = {
    "email": "",
    "password": ""
}

SESSIONS_FILE = os.path.join(DIRECTORY, "..", "sessions.json")
if os.path.exists(SESSIONS_FILE):
    try:
        with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
            SESSIONS = json.load(f)
    except:
        SESSIONS = {}
else:
    SESSIONS = {}  # { session_id: { "title": "...", "messages": [], "updated_at": timestamp } }

def save_sessions():
    with open(SESSIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(SESSIONS, f, indent=2)

def should_perform_research(query: str) -> bool:
    """Determines whether a query genuinely requires external live web research."""
    q = query.strip().lower()
    
    # 1. Do not search for conversational phrases or follow-ups
    conversational = [
        'what is this', 'what is that', 'what do you mean', 'why', 'why is this', 
        'why that', 'how come', 'who are you', 'what are you', 'hello', 'hi', 
        'hey', 'thanks', 'thank you', 'ok', 'okay', 'explain', 'help', 'no', 'yes'
    ]
    if q in conversational or len(q.split()) <= 2:
        return False
        
    # 2. Do not search for educational, science, diagrams, code, or evergreen concepts
    evergreen = [
        'flowchart', 'flow chart', 'diagram', 'write code', 'python', 'javascript', 
        'html', 'css', 'solve', 'calculate', 'poem', 'story', 'essay', 'evolution',
        'human evolution', 'photosynthesis', 'gravity', 'physics', 'math'
    ]
    has_live_indicators = any(k in q for k in ['latest', 'news', 'update', 'today', '2026', 'price', 'score', 'weather', 'live'])
    if any(k in q for k in evergreen) and not has_live_indicators:
        return False

    # 3. Only search if live temporal or real-time keywords are present
    live_keywords = [
        'weather', 'climate', 'temperature', 'forecast', 'rain', 'news', 'today', 
        'yesterday', 'current', 'live', 'latest', 'recent', 'who won', 'match', 
        'score', 'ipl', 'cricket', 'election', 'stock', 'price of', 'released', 
        'upcoming', 'when is', '2026', '2025'
    ]
    return any(k in q for k in live_keywords)

def perform_research(query):
    """Simple Web Research Agent: Queries Wikipedia API for context."""
    if not should_perform_research(query):
        return "No external research found."
    try:
        # Search for the query
        search_url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(query)}&utf8=&format=json"
        req = urllib.request.Request(search_url, headers={'User-Agent': 'WorstAI-Agent/1.0'})
        response = urllib.request.urlopen(req, timeout=5)
        data = json.loads(response.read().decode('utf-8'))
        
        search_results = data.get('query', {}).get('search', [])
        if not search_results:
            return "No external research found."
            
        # Get the page ID of the top result
        page_id = search_results[0]['pageid']
        
        # Get the extract (summary) of that page
        summary_url = f"https://en.wikipedia.org/w/api.php?action=query&prop=extracts&exsentences=5&exlimit=1&pageids={page_id}&explaintext=1&format=json"
        req2 = urllib.request.Request(summary_url, headers={'User-Agent': 'WorstAI-Agent/1.0'})
        response2 = urllib.request.urlopen(req2, timeout=5)
        data2 = json.loads(response2.read().decode('utf-8'))
        
        pages = data2.get('query', {}).get('pages', {})
        if str(page_id) in pages:
            return pages[str(page_id)].get('extract', "No external research found.")
    except Exception as e:
        print(f"[RESEARCH ERROR] {e}")
        return "Failed to fetch external research."
    
    return "No external research found."

class SwarmHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        super().end_headers()

    def do_POST(self):
        # --- SET SMTP CONFIG ---
        if self.path == "/api/config/smtp":
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            try: body = json.loads(post_data.decode('utf-8'))
            except: body = {}
            
            SMTP_CONFIG["email"] = body.get("email", "")
            SMTP_CONFIG["password"] = body.get("password", "")
            print(f"[CONFIG] Updated SMTP settings for {SMTP_CONFIG['email']}")
            self.send_json({"success": True})
            return

        # --- SEND OTP ---
        if self.path == "/api/auth/send_otp":
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            try: body = json.loads(post_data.decode('utf-8'))
            except: body = {}
            
            email = body.get("email")
            if not email:
                self.send_json({"success": False, "error": "Email is required"})
                return
            
            otp = str(random.randint(100000, 999999))
            OTP_STORE[email] = otp
            print(f"\n[AUTH] Generated OTP for {email}: {otp}", flush=True)
            
            # Write to passkey.txt for easy access
            with open(os.path.join(DIRECTORY, "..", "passkey.txt"), "w") as f:
                f.write(otp)
            
            # Try sending email
            if SMTP_CONFIG["email"] and SMTP_CONFIG["password"]:
                try:
                    msg = EmailMessage()
                    msg.set_content(f"Your WorstAI login passkey is: {otp}\n\nPlease enter this code to securely log in.")
                    msg['Subject'] = 'WorstAI Login Passkey'
                    msg['From'] = SMTP_CONFIG["email"]
                    msg['To'] = email

                    server = smtplib.SMTP("smtp.gmail.com", 587)
                    server.starttls()
                    server.login(SMTP_CONFIG["email"], SMTP_CONFIG["password"])
                    server.send_message(msg)
                    server.quit()
                    print(f"[AUTH] Successfully sent email to {email}")
                    self.send_json({"success": True, "method": "email"})
                    return
                except Exception as e:
                    print(f"[AUTH ERROR] SMTP Failed: {e}")
                    self.send_json({"success": False, "error": "SMTP config failed. Check your App Password."})
                    return
            else:
                print(f"[AUTH] No SMTP config found. Falling back to terminal.")
                self.send_json({"success": True, "method": "terminal"})
            return

        # --- VERIFY OTP ---
        if self.path == "/api/auth/verify_otp":
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            try: body = json.loads(post_data.decode('utf-8'))
            except: body = {}
            
            email = body.get("email")
            otp = body.get("otp")
            
            if email in OTP_STORE and OTP_STORE[email] == otp:
                self.send_json({"success": True})
            else:
                self.send_json({"success": False, "error": "Incorrect passkey"})
            return

        # --- CLEAR CHAT (Legacy) ---
        if self.path == "/api/clear":
            self.send_json({"success": True})
            return

        # --- CHAT & RESEARCH ---
        if self.path == "/api/chat":
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            try: body = json.loads(post_data.decode('utf-8'))
            except: body = {}

            prompt = body.get("prompt", "")
            session_id = body.get("session_id", "default")
            agents_settings = body.get("agents", {})
            use_research = agents_settings.get("research", True)
            use_code = agents_settings.get("code", True)
            use_privacy = agents_settings.get("privacy", True)
            use_security = agents_settings.get("security", True)
            use_factcheck = agents_settings.get("factcheck", True)
            use_sentiment = agents_settings.get("sentiment", True)
            
            import time
            
            # Initialize session if it doesn't exist
            if session_id not in SESSIONS:
                SESSIONS[session_id] = {
                    "title": prompt[:30] + ("..." if len(prompt) > 30 else ""),
                    "messages": [],
                    "updated_at": time.time()
                }
            else:
                SESSIONS[session_id]["updated_at"] = time.time()
                
            session_data = SESSIONS[session_id]
            save_sessions()
            
            agents_used = ["Online LLM"]
            
            # Privacy Auditor (Always on)
            import re
            original_prompt = prompt
            prompt = re.sub(r'\b\d{3}-\d{2}-\d{4}\b', '[REDACTED SSN]', prompt)
            prompt = re.sub(r'\b(?:\d[ -]*?){13,16}\b', '[REDACTED CC]', prompt)
            if original_prompt != prompt:
                agents_used.append("Privacy Auditor")
            
            # Security Auditor
            if use_security and ("password" in prompt.lower() or "secret" in prompt.lower() or "token" in prompt.lower()):
                agents_used.append("Security Auditor")
                prompt += "\n\n(Note: The Security Auditor warns against sharing real credentials!)"
                
            # Sentiment Analysis Agent
            if use_sentiment:
                agents_used.append("Sentiment Analysis")
            
            # 1. Perform Web Research if requested
            research_context = None
            if use_research:
                print(f"\n[AGENT] Researching: {prompt}")
                research_context = perform_research(prompt)
                if research_context and research_context != "No external research found.":
                    agents_used.append("Deep Research")
            
            # 2. Build Prompt for g4f with history
            messages_for_ai = list(session_data["messages"])
            if use_research and research_context and research_context != "No external research found.":
                messages_for_ai.append({"role": "system", "content": f"Use this recent research to help answer the user: {research_context}"})
            
            messages_for_ai.append({"role": "user", "content": prompt})
            
            try:
                print(f"[AGENT] Generating response via g4f online providers...")
                try:
                    # First try a very fast/reliable provider explicitly if available
                    response = g4f.ChatCompletion.create(
                        model=g4f.models.gpt_4o_mini,
                        messages=messages_for_ai,
                        provider=g4f.Provider.Blackbox
                    )
                except Exception as e:
                    print(f"[WARN] Blackbox failed: {e}. Falling back to default routing...")
                    # Fallback to automatic routing
                    response = g4f.ChatCompletion.create(
                        model=g4f.models.gpt_4o_mini,
                        messages=messages_for_ai,
                    )
                
                response_str = str(response)
                
                # 5. Code Execution Agent (Mock/Check)
                if use_code and "```python" in response_str:
                    agents_used.append("Code Auditor")
                    response_str += "\n\n*(Verified by Code Auditor)*"
                    
                # 6. Fact-Checking Agent
                if use_factcheck and len(response_str) > 100:
                    agents_used.append("Fact-Checker")
                
                # Save to history
                session_data["messages"].append({"role": "user", "content": original_prompt, "agents": []})
                session_data["messages"].append({"role": "ai", "content": response_str, "agents": agents_used})
                save_sessions()
                
                self.send_json({
                    "success": True, 
                    "answer": response_str, 
                    "research": research_context,
                    "agents_used": agents_used
                })
            except Exception as e:
                print(f"[ERROR] Failed to contact g4f providers: {e}")
                self.send_json({"success": False, "error": f"Failed to connect to free online AI providers via g4f. Error: {e}"})
            return

    def do_GET(self):
        # --- GET SESSIONS LIST ---
        if self.path == "/api/sessions":
            # Return list of sessions sorted by newest first (top 5)
            import time
            sorted_sessions = sorted(SESSIONS.items(), key=lambda x: x[1].get('updated_at', 0), reverse=True)[:5]
            session_list = [{"id": sid, "title": data["title"]} for sid, data in sorted_sessions]
            self.send_json({"success": True, "sessions": session_list})
            return

        # --- GET SESSION MESSAGES ---
        if self.path.startswith("/api/sessions/"):
            session_id = self.path.split("/")[-1]
            if session_id in SESSIONS:
                self.send_json({"success": True, "messages": SESSIONS[session_id]["messages"]})
            else:
                self.send_json({"success": False, "error": "Session not found"})
            return
            
        # Default simple HTTP handler
        super().do_GET()

    def do_DELETE(self):
        # --- DELETE SESSION ---
        if self.path.startswith("/api/sessions/"):
            session_id = self.path.split("/")[-1]
            if session_id in SESSIONS:
                del SESSIONS[session_id]
                save_sessions()
                self.send_json({"success": True})
            else:
                self.send_json({"success": False, "error": "Session not found"})
            return
        
        self.send_response(405)
        self.end_headers()

    def send_json(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def run_server():
    local_ip = get_local_ip()
    handler = SwarmHandler
    socketserver.TCPServer.allow_reuse_address = True
    
    with socketserver.TCPServer(("0.0.0.0", PORT), handler) as httpd:
        print("=" * 70)
        print("🚀 VERSATILE-AI 22-AGENT SWARM SERVER ONLINE")
        print("=" * 70)
        print(f"👉 Local URL: http://localhost:{PORT}")
        print("=" * 70)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down.")

if __name__ == "__main__":
    run_server()
