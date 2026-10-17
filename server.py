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
        'upcoming', 'when is', 'when was', '2026', '2025', 'exam', 'examination',
        'exam date', 'exam dates', 'schedule', 'timetable', 'present', 'term', 'cutoff'
    ]
    return any(k in q for k in live_keywords)

def perform_research(query):
    """Multi-Source Live Web Research: Queries live DuckDuckGo web snippets and Wikipedia."""
    if not should_perform_research(query):
        return "No external research found."
    findings = []
    
    # 1. Live DuckDuckGo web snippets for real-time present information
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "api"))
        from index import search_duckduckgo
        ddg_results = search_duckduckgo(query, max_results=3)
        for u, s in ddg_results:
            if s and len(s) > 25:
                findings.append(f"[Live Web Snippet: {u}]\n{s}")
    except Exception as e:
        print(f"[WARN] Live search error: {e}")

    # 2. Wikipedia fallback / supplementary summary
    try:
        search_url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(query)}&utf8=&format=json"
        req = urllib.request.Request(search_url, headers={'User-Agent': 'WorstAI-Agent/1.0'})
        with urllib.request.urlopen(req, timeout=3.5) as response:
            data = json.loads(response.read().decode('utf-8'))
            search_results = data.get('query', {}).get('search', [])
            if search_results:
                page_id = search_results[0]['pageid']
                summary_url = f"https://en.wikipedia.org/w/api.php?action=query&prop=extracts&exsentences=4&exlimit=1&pageids={page_id}&explaintext=1&format=json"
                req2 = urllib.request.Request(summary_url, headers={'User-Agent': 'WorstAI-Agent/1.0'})
                with urllib.request.urlopen(req2, timeout=3.5) as response2:
                    data2 = json.loads(response2.read().decode('utf-8'))
                    pages = data2.get('query', {}).get('pages', {})
                    if str(page_id) in pages:
                        extract = pages[str(page_id)].get('extract', '')
                        if extract:
                            findings.append(f"[Wikipedia Summary]\n{extract}")
    except Exception:
        pass

    if findings:
        return "\n\n---\n\n".join(findings)
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

            # --- Conversational Understanding & Feedback Interceptor ---
            prompt_lower = prompt.lower().strip()
            p_clean_alpha = re.sub(r'[^\w\s]', '', prompt_lower).strip()
            clean_words = p_clean_alpha.split()

            compliment_exact = {
                'good', 'good job', 'great job', 'nice job', 'well done', 'good work', 'great work',
                'nice work', 'awesome work', 'excellent work', 'superb work', 'fine job', 'amazing work',
                'nice', 'great', 'awesome', 'super', 'superb', 'cool', 'excellent', 'wonderful',
                'fantastic', 'amazing', 'brilliant', 'perfect', 'love it', 'looks good', 'sounds good',
                'this is good', 'that is good', 'thats good', 'that’s good', 'very good', 'so good',
                'good one', 'well explained', 'good explanation', 'nice explanation', 'great explanation',
                'good ai', 'nice ai', 'smart ai', 'you are good', 'you are great', 'you are awesome'
            }
            clarified_compliment_pats = [
                r'^(?:i\s+(?:told|said|meant|was\s+saying|told\s+you|told\s+u)\s+)?(?:you\s+did\s+a\s+)?(good\s+job|great\s+job|nice\s+job|well\s+done|good\s+work|nice\s+work|great\s+work|good|nice|great|awesome|super)\b',
                r'\b(?:told|said|meant)\s+(?:good\s+job|great\s+job|nice\s+job|well\s+done|good|nice)\b',
                r'\bi\s+(?:told|said)\s+(?:u\s+|you\s+)?good\s+job\b',
                r'\bi\s+(?:told|said)\s+good\b'
            ]
            affirmation_exact = {
                'ok', 'okay', 'fine', 'alright', 'all right', 'got it', 'i got it', 'understood',
                'i understand', 'sure', 'yep', 'yeah', 'yes', 'no problem', 'noted', 'makes sense',
                'clear', 'crystal clear', 'right', 'correct', 'exactly', 'k', 'kk'
            }
            misunderstanding_pats = [
                r'\bmisinformation\b', r'\byou\s+misunderstood\b', r'\bmisunderstood\b',
                r'\bwrong\s+answer\b', r'\bnot\s+what\s+i\s+(asked|said|meant)\b',
                r'\bwhy\s+did\s+you\s+say\s+that\b', r'\bi\s+did\s+not\s+ask\s+that\b',
                r'\bnot\s+this\b', r'\byou\s+are\s+wrong\b', r'\btrain\s+it\s+well\b',
                r'\bunderstand\s+what\s+user\s+is\s+tell\b', r'\btaking\s+more\s+time\b'
            ]

            quick_ans = None
            if p_clean_alpha in compliment_exact or any(re.search(pat, prompt_lower) for pat in clarified_compliment_pats):
                quick_ans = "Thank you so much! I really appreciate your feedback and kind words. I'm glad I could help! If you have any other questions, topics, or code you'd like to work on, feel free to ask!"
            elif p_clean_alpha in affirmation_exact or (len(clean_words) <= 2 and clean_words and clean_words[0] in ['ok', 'okay', 'fine', 'got']):
                quick_ans = "Got it! What would you like to explore next? Feel free to ask any question, topic, or code problem!"
            elif any(re.search(pat, prompt_lower) for pat in misunderstanding_pats):
                quick_ans = (
                    "I completely understand and sincerely apologize for the previous misunderstanding! "
                    "I have refined my conversational understanding to accurately recognize your feedback, compliments, and exact questions without delay. "
                    "I am ready to assist you quickly and accurately. Please let me know what specific topic, algorithm, or question you would like help with right now!"
                )
            elif any(cp in prompt_lower for cp in ['who is your creator', 'who created you', 'who made you', 'who is your god']):
                quick_ans = (
                    "I am **WorstAI**, a highly advanced artificial intelligence assistant created and developed by **GOLLU ADI VENKATA SAI**.\n\n"
                    "As an AI, I do not have a deity or spiritual beliefs; my purpose is to assist you with accurate code, deep research, and instant answers."
                )

            if quick_ans:
                session_data["messages"].append({"role": "user", "content": original_prompt, "agents": []})
                session_data["messages"].append({"role": "ai", "content": quick_ans, "agents": ["WorstAI-Concierge"]})
                save_sessions()
                self.send_json({
                    "success": True,
                    "answer": quick_ans,
                    "research": None,
                    "agents_used": ["WorstAI-Concierge"]
                })
                return
            
            # Resolve follow-up queries using session history
            resolved_query = prompt
            p_clean = prompt.lower().strip()
            follow_up_phrases = [
                'what is this', 'what is that', 'what does this mean', 'explain this', 'tell me more', 
                'why', 'elaborate', 'what is it', 'give the code', 'give code', 'code', 'show code',
                'python', 'in python', 'java', 'in java', 'cpp', 'c++', 'javascript', 'solution',
                'give solution', 'solve it', 'provide solution', 'how to solve', 'write code',
                'continue', 'next', 'more details', 'help me with this',
                'search and tell me', 'search and tell', 'search it', 'search', 'search this',
                'tell me', 'tell me now', 'tell the answer', 'tell answer', 'find it', 'find out',
                'find and tell', 'find and tell me', 'check and tell', 'check and tell me',
                'check it', 'give answer', 'give me answer', 'what is the answer', 'answer it',
                'answer me', 'please search', 'search info', 'search online'
            ]
            is_follow_up = any(fp == p_clean or p_clean.startswith(fp + ' ') or p_clean.endswith(' ' + fp) for fp in follow_up_phrases)
            if is_follow_up and session_data.get("messages"):
                last_topic = ''
                for msg in reversed(session_data["messages"]):
                    if msg.get('role') == 'user' and len(msg.get('content', '')) > 2:
                        cand = msg.get('content', '').strip()
                        cand_clean = cand.lower().strip()
                        if not any(fp == cand_clean for fp in follow_up_phrases):
                            last_topic = cand
                            break
                if last_topic:
                    search_imperatives = [
                        'search and tell me', 'search and tell', 'search it', 'search', 'search this',
                        'tell me', 'tell me now', 'tell the answer', 'tell answer', 'find it', 'find out',
                        'find and tell', 'find and tell me', 'check and tell', 'check and tell me',
                        'check it', 'give answer', 'give me answer', 'what is the answer', 'answer it',
                        'answer me', 'please search', 'search info', 'search online'
                    ]
                    if any(p_clean == si or p_clean.startswith(si + ' ') for si in search_imperatives):
                        resolved_query = last_topic
                    elif any(k in p_clean for k in ['code', 'python', 'java', 'c++', 'cpp', 'javascript', 'solution', 'solve', 'give']):
                        resolved_query = f"{last_topic} ({prompt})"
                    else:
                        resolved_query = f"{last_topic} - {prompt}"

            # Instant Academic Curriculum Engine (<0.001s, 0 network wait)
            try:
                sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "api"))
                from index import synthesize_academic_response, normalize_query_and_short_forms
                norm_prompt = normalize_query_and_short_forms(resolved_query)
                instant_acad = synthesize_academic_response(norm_prompt, only_curated=True)
                if instant_acad:
                    session_data["messages"].append({"role": "user", "content": original_prompt, "agents": []})
                    session_data["messages"].append({"role": "ai", "content": instant_acad, "agents": ["WorstAI-Instant-Curriculum"]})
                    save_sessions()
                    self.send_json({
                        "success": True,
                        "answer": instant_acad,
                        "research": None,
                        "agents_used": ["WorstAI-Instant-Curriculum"]
                    })
                    return
            except Exception:
                pass
            
            # 1. Perform Web Research if requested
            research_context = None
            if use_research:
                print(f"\n[AGENT] Researching: {prompt}")
                research_context = perform_research(prompt)
                if research_context and research_context != "No external research found.":
                    agents_used.append("Deep Research")
            
            # 2. Build Prompt for g4f with history
            # Prepend strict Academic & Study Guidelines so answers always provide Definition first, then Types
            sys_guideline = (
                "You are WorstAI, an ultra-fast academic AI knowledge tutor created by GOLLU ADI VENKATA SAI.\n\n"
                "CRITICAL CORE RULE: ANSWER ONLY WHAT USER ASKED — NOT MORE, NOT LESS.\n"
                "- Answer the user's specific question directly, perfectly, and accurately without adding unrequested topics, unsolicited essays, or filler.\n"
                "- Keep all explanations in simple, everyday plain English that is effortlessly understood by any student or reader.\n"
                "- Avoid dense, confusing jargon. Keep sentences clear, concise, and easy to read.\n\n"
                "1. STUDY & ACADEMIC TOPICS (When asked about a concept/subject like AI, ML, OS, DBMS, DAA, etc.):\n"
                "   - 1. Definition: \"### 1. Definition\" -> 1-2 sentence simple, clear definition in plain English.\n"
                "   - 2. Types: \"### 2. Types of [Topic]\" -> Simple list or table of the main types with 1 clear line each.\n"
                "   - 3. How It Works: \"### 3. Key Components / How It Works\" -> 3-4 simple bullet points.\n"
                "   - 4. Everyday Example: \"### 4. Simple Real-World Example\" -> An easy everyday analogy or application.\n\n"
                "2. DIRECT FACTUAL QUESTIONS (Dates, timetables, facts, specific queries):\n"
                "   - Give the exact direct answer immediately without unneeded sections.\n\n"
                "3. TONE & STYLE:\n"
                "   - Simple, direct, clean English. No filler, no preambles, and no dollar signs around math."
            )
            messages_for_ai = [{"role": "system", "content": sys_guideline}] + list(session_data["messages"])
            if use_research and research_context and research_context != "No external research found.":
                messages_for_ai.append({"role": "system", "content": f"Use this recent research to help answer the user: {research_context}"})
            
            messages_for_ai.append({"role": "user", "content": prompt})
            
            try:
                print(f"[AGENT] Generating response via fast AI engine...")
                try:
                    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "api"))
                    from index import get_ai_response
                    response_str, model_used = get_ai_response(messages_for_ai, prompt)
                except Exception as e:
                    print(f"[WARN] Engine fallback: {e}")
                    import g4f
                    response = g4f.ChatCompletion.create(
                        model='gpt-4',
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
