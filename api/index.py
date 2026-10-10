import http.server
import json
import urllib.request
import urllib.parse
import re
import random
import threading
import concurrent.futures
import datetime
import googlesearch
import os
os.environ["HOME"] = "/tmp"
os.environ["G4F_USER_CONFIG_DIR"] = "/tmp/g4f"
import g4f

# =============================================================================
# WEB RESEARCH AGENT
# Uses DuckDuckGo (free, no key) to find real URLs, then Jina AI reader
# (free, no key) to extract clean text from each page.
# Wikipedia API used for factual/knowledge queries.
# Results are injected into the AI prompt for grounded, verified answers.
# =============================================================================

SEARCH_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml',
    'Accept-Language': 'en-US,en;q=0.9',
}


def search_google(query, max_results=3):
    """Search Google. Returns list of (url, snippet) tuples."""
    try:
        urls = list(googlesearch.search(query, num_results=max_results))
        return [(u, '') for u in urls[:max_results]]
    except Exception:
        return []

def search_duckduckgo(query, max_results=3):
    """Search DuckDuckGo HTML endpoint as a fallback."""
    try:
        url = 'https://html.duckduckgo.com/html/?q=' + urllib.parse.quote(query)
        req = urllib.request.Request(url, headers=SEARCH_HEADERS)
        res = urllib.request.urlopen(req, timeout=3)
        html = res.read().decode('utf-8', errors='replace')
        raw_urls = re.findall(r'uddg=(https?[^&"\s]+)', html)
        urls = []
        for u in raw_urls:
            decoded = urllib.parse.unquote(u)
            if 'duckduckgo' not in decoded and decoded not in urls:
                urls.append(decoded)
            if len(urls) >= max_results:
                break
        return [(u, '') for u in urls]
    except Exception:
        return []

def read_url_jina(url, max_chars=1500):
    """Use Jina AI reader (free, no key) to get clean text from any URL."""
    try:
        jina_url = 'https://r.jina.ai/' + url
        req = urllib.request.Request(
            jina_url,
            headers={
                'User-Agent': 'Mozilla/5.0 Chrome/124',
                'Accept': 'text/plain',
                'X-Return-Format': 'text',
            }
        )
        res = urllib.request.urlopen(req, timeout=4)
        text = res.read().decode('utf-8', errors='replace')
        # Strip Jina header metadata, keep content
        if 'Markdown Content:' in text:
            text = text.split('Markdown Content:', 1)[1]
        # Remove markdown links, keep text
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
        text = re.sub(r'#+\s*', '', text)  # Remove headings markup
        text = re.sub(r'\n{3,}', '\n\n', text)  # Collapse blank lines
        return text.strip()[:max_chars]
    except Exception:
        return ''


def search_wikipedia(query, max_chars=1000):
    """Query Wikipedia REST API for a quick factual summary."""
    try:
        search_url = ('https://en.wikipedia.org/w/api.php?action=opensearch&search='
                      + urllib.parse.quote(query) + '&limit=1&format=json')
        req = urllib.request.Request(search_url, headers={'User-Agent': 'WorstAI/1.0'})
        res = urllib.request.urlopen(req, timeout=2)
        results = json.loads(res.read())
        titles = results[1] if len(results) > 1 else []
        if not titles:
            return ''
        # Fetch summary for the top title
        title = urllib.parse.quote(titles[0].replace(' ', '_'))
        summary_url = f'https://en.wikipedia.org/api/rest_v1/page/summary/{title}'
        req2 = urllib.request.Request(summary_url, headers={'User-Agent': 'WorstAI/1.0'})
        res2 = urllib.request.urlopen(req2, timeout=2)
        data = json.loads(res2.read())
        extract = data.get('extract', '')
        return extract[:max_chars]
    except Exception:
        return ''


def search_google_news(query, max_results=3):
    """Query Google News RSS for high-quality news headlines."""
    import xml.etree.ElementTree as ET
    try:
        url = 'https://news.google.com/rss/search?q=' + urllib.parse.quote(query)
        req = urllib.request.Request(url, headers={'User-Agent': 'WorstAI/1.0'})
        res = urllib.request.urlopen(req, timeout=3)
        root = ET.fromstring(res.read())
        headlines = []
        for item in root.findall('.//item')[:max_results]:
            title = item.find('title').text if item.find('title') is not None else ''
            pubDate = item.find('pubDate').text if item.find('pubDate') is not None else ''
            if title:
                headlines.append(f"- {title} ({pubDate})")
        if headlines:
            return "[Google News Headlines]\n" + "\n".join(headlines)
        return ''
    except Exception:
        return ''

def search_arxiv(query, max_results=2):
    """Search ArXiv API for scientific papers."""
    import xml.etree.ElementTree as ET
    try:
        url = 'http://export.arxiv.org/api/query?search_query=all:' + urllib.parse.quote(query) + f'&start=0&max_results={max_results}'
        req = urllib.request.Request(url, headers={'User-Agent': 'WorstAI/1.0'})
        res = urllib.request.urlopen(req, timeout=3)
        root = ET.fromstring(res.read())
        papers = []
        for entry in root.findall('{http://www.w3.org/2005/Atom}entry'):
            title = entry.find('{http://www.w3.org/2005/Atom}title').text.replace('\n', ' ').strip()
            summary = entry.find('{http://www.w3.org/2005/Atom}summary').text.replace('\n', ' ').strip()
            papers.append(f"Title: {title}\nAbstract: {summary[:500]}...")
        if papers:
            return "[ArXiv Scientific Papers]\n" + "\n\n".join(papers)
        return ''
    except Exception:
        return ''

def search_yahoo(query, max_results=3):
    """Search Yahoo HTML endpoint."""
    try:
        url = 'https://search.yahoo.com/search?p=' + urllib.parse.quote(query)
        req = urllib.request.Request(url, headers=SEARCH_HEADERS)
        res = urllib.request.urlopen(req, timeout=3)
        html = res.read().decode('utf-8', errors='replace')
        raw_urls = re.findall(r'href="(https?://[^"]+)"', html)
        urls = []
        for u in raw_urls:
            if 'yahoo.com' not in u and 'yimg.com' not in u and u not in urls:
                urls.append(u)
            if len(urls) >= max_results:
                break
        return [(u, '') for u in urls]
    except Exception:
        return []

def search_bing(query, max_results=3):
    """Search Bing HTML endpoint."""
    try:
        url = 'https://www.bing.com/search?q=' + urllib.parse.quote(query)
        req = urllib.request.Request(url, headers=SEARCH_HEADERS)
        res = urllib.request.urlopen(req, timeout=3)
        html = res.read().decode('utf-8', errors='replace')
        raw_urls = re.findall(r'href="(https?://[^"]+)"', html)
        urls = []
        for u in raw_urls:
            if 'bing.com' not in u and 'microsoft.com' not in u and u not in urls:
                urls.append(u)
            if len(urls) >= max_results:
                break
        return [(u, '') for u in urls]
    except Exception:
        return []

def search_ecosia(query, max_results=3):
    """Search Ecosia HTML endpoint."""
    try:
        url = 'https://www.ecosia.org/search?q=' + urllib.parse.quote(query)
        req = urllib.request.Request(url, headers=SEARCH_HEADERS)
        res = urllib.request.urlopen(req, timeout=3)
        html = res.read().decode('utf-8', errors='replace')
        raw_urls = re.findall(r'href="(https?://[^"]+)"', html)
        urls = []
        for u in raw_urls:
            if 'ecosia.org' not in u and u not in urls:
                urls.append(u)
            if len(urls) >= max_results:
                break
        return [(u, '') for u in urls]
    except Exception:
        return []

def search_geeksforgeeks(query, max_results=1):
    """Specific search for GeeksforGeeks articles."""
    try:
        url = 'https://html.duckduckgo.com/html/?q=' + urllib.parse.quote(query + ' site:geeksforgeeks.org')
        req = urllib.request.Request(url, headers=SEARCH_HEADERS)
        res = urllib.request.urlopen(req, timeout=3)
        html = res.read().decode('utf-8', errors='replace')
        raw_urls = re.findall(r'href="(https?://[^"]+)"', html)
        urls = []
        for u in raw_urls:
            if 'uddg=' in u:
                u = urllib.parse.unquote(u.split('uddg=')[1].split('&')[0])
            if 'geeksforgeeks.org' in u and u not in urls:
                urls.append(u)
            if len(urls) >= max_results:
                break
        return [(u, '') for u in urls]
    except Exception:
        return []

def run_web_research(query):
    try:
        findings = []
        search_engines = [search_google, search_duckduckgo, search_yahoo, search_bing, search_ecosia, search_geeksforgeeks]
        search_results = []
        
        # 1. Race the search engines to find URLs instantly
        executor1 = concurrent.futures.ThreadPoolExecutor(max_workers=len(search_engines))
        futures = {executor1.submit(engine, query, 3): engine for engine in search_engines}
        for future in concurrent.futures.as_completed(futures, timeout=2):
            try:
                res = future.result()
                if res:
                    search_results = res
                    break
            except:
                continue
        executor1.shutdown(wait=False, cancel_futures=True)
                    
        # 2. Run all heavy research tasks simultaneously
        def fetch_wiki():
            return search_wikipedia(query)
        def fetch_news():
            return search_google_news(query)
        def fetch_arxiv():
            return search_arxiv(query)
        def fetch_gfg():
            gfg_urls = search_geeksforgeeks(query)
            if not gfg_urls: return ''
            content = read_url_jina(gfg_urls[0][0], max_chars=1200)
            return f'[GeeksforGeeks]\n{content}' if content else ''
            
        def fetch_page(url_snippet):
            url, snippet = url_snippet
            content = read_url_jina(url, max_chars=1200)
            if not content and snippet:
                content = snippet
            if content:
                domain = re.sub(r'https?://(www\.)?', '', url).split('/')[0]
                return f'[{domain}]\n{content}'
            return ''

        tasks = [fetch_wiki, fetch_news, fetch_arxiv, fetch_gfg]
        
        executor2 = concurrent.futures.ThreadPoolExecutor(max_workers=7)
        future_to_task = {executor2.submit(task): task.__name__ for task in tasks}
        for sr in search_results[:2]:
            future_to_task[executor2.submit(fetch_page, sr)] = "fetch_page"
            
        for future in concurrent.futures.as_completed(future_to_task, timeout=2):
            try:
                result = future.result()
                if result:
                    if future_to_task[future] == 'fetch_wiki':
                        findings.append(f'[Wikipedia]\n{result}')
                    else:
                        findings.append(result)
            except Exception:
                pass
        executor2.shutdown(wait=False, cancel_futures=True)

        if not findings:
            return ''

        brief = '\n\n---\n\n'.join(findings)
        return f'RESEARCH FINDINGS (sourced from web search + Wikipedia):\n\n{brief}'

    except Exception:
        return ''

# =============================================================================
# WORSTAI BACKEND - PERMANENT KEYLESS AI ENGINE
# Uses GPT4Free (g4f) to automatically load-balance across multiple free APIs
# =============================================================================

def get_ai_response(messages, last_user_message):
    """
    Blisteringly fast AI generation utilizing direct g4f library.
    Races 10 distinct models simultaneously.
    """
    models = [
        getattr(g4f.models, 'gpt_4o', 'gpt-4o'),
        getattr(g4f.models, 'gpt_4o_mini', 'gpt-4o-mini'),
        getattr(g4f.models, 'claude_3_5_sonnet', 'claude-3.5-sonnet'),
        getattr(g4f.models, 'mixtral_8x7b', 'mixtral-8x7b'),
        getattr(g4f.models, 'llama_3_1_8b_instruct', 'llama-3.1-8b-instruct'),
        getattr(g4f.models, 'gemini_flash', 'gemini-1.5-flash'),
        getattr(g4f.models, 'qwen_2_72b', 'qwen-2-72b'),
        getattr(g4f.models, 'deepseek_coder', 'deepseek-coder'),
        getattr(g4f.models, 'gpt_4', 'gpt-4'),
        getattr(g4f.models, 'claude_3_haiku', 'claude-3-haiku')
    ]
    errors = []
    
    from g4f.client import Client
    client = Client()
    
    executor3 = concurrent.futures.ThreadPoolExecutor(max_workers=len(models))
    futures = {}
    for m in models:
        def fetch(mod):
            try:
                response = client.chat.completions.create(model=mod, messages=messages)
                content = response.choices[0].message.content.strip()
                name = mod.name if hasattr(mod, 'name') else str(mod)
                if content: return content, name
                raise Exception("Empty")
            except Exception as e:
                raise Exception(f"{str(e)}")
        futures[executor3.submit(fetch, m)] = m
        
    for future in concurrent.futures.as_completed(futures):
        try: 
            res = future.result()
            executor3.shutdown(wait=False, cancel_futures=True)
            return res
        except Exception as e:
            errors.append(str(e)[:20])
            
    executor3.shutdown(wait=False, cancel_futures=True)
    raise Exception(f"AI Swarm Race failed: {errors}")

def ask_auditor(system_prompt, user_prompt):
    models_to_race = [
        getattr(g4f.models, 'gpt_4o_mini', 'gpt-4o-mini'), 
        getattr(g4f.models, 'claude_3_haiku', 'claude-3-haiku'), 
        getattr(g4f.models, 'llama_3_1_8b_instruct', 'llama-3.1-8b-instruct')
    ]
    
    from g4f.client import Client
    client = Client()
    
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=len(models_to_race))
    futures = {}
    for mod in models_to_race:
        def fetch(m):
            try:
                response = client.chat.completions.create(
                    model=m, 
                    messages=[
                        {'role': 'system', 'content': system_prompt},
                        {'role': 'user', 'content': user_prompt}
                    ]
                )
                content = response.choices[0].message.content.strip()
                if content: return content
                raise Exception("Empty")
            except Exception as e:
                raise Exception(str(e))
        futures[executor.submit(fetch, mod)] = mod
        
    for future in concurrent.futures.as_completed(futures, timeout=15):
        try:
            res = future.result()
            executor.shutdown(wait=False, cancel_futures=True)
            return res
        except Exception:
            pass
            
    executor.shutdown(wait=False, cancel_futures=True)
    return f"[Auditor Offline: Timeout or blocked by free providers]"

def run_auditor_swarm(draft, research, cfg, history):
    auditors_results = []
    
    # Format history for agents to learn context
    history_text = "\n".join([f"{msg.get('role', 'user')}: {msg.get('content', '')}" for msg in history[-4:]])
    
    def fact_checker():
        if not cfg.get('research', True): return None
        sys_prompt = "You are a strict Fact-Checker. Think step-by-step. Analyze the chat history and research to verify the Draft. If the Draft contradicts the Research or hallucinated facts, explain why. If it is 100% accurate, output exactly 'PASSED'."
        user_prompt = f"Chat History:\n{history_text}\n\nWeb Research:\n{research}\n\nDraft:\n{draft}"
        res = ask_auditor(sys_prompt, user_prompt)
        if res and "PASSED" not in res:
            return f"**Fact-Checker Alert**: {res}"
        return None

    def privacy_security():
        if not cfg.get('privacy', True) and not cfg.get('security', True): return None
        sys_prompt = "You are a Security & Privacy Auditor. Think step-by-step. Does this draft or chat history contain PII, harmful code, or unsafe advice? If yes, explain. If safe, output exactly 'PASSED'."
        res = ask_auditor(sys_prompt, f"Chat History:\n{history_text}\n\nDraft:\n{draft}")
        if res and "PASSED" not in res:
            return f"**Security/Privacy Alert**: {res}"
        return None
        
    def sentiment():
        if not cfg.get('sentiment', True): return None
        sys_prompt = "You are a Sentiment Analyzer. Think step-by-step about the user's emotional state based on the chat history. Output the final sentiment of the Draft in one word."
        res = ask_auditor(sys_prompt, f"Chat History:\n{history_text}\n\nDraft:\n{draft}")
        if res and "PASSED" not in res:
            return f"**Sentiment Analysis**: {res}"
        return None

    def arxiv_auditor():
        if not cfg.get('research', True): return None
        sys_prompt = "You are a Scientific Auditor. Analyze the draft against the research. Ensure facts match scientific consensus. If safe, output 'PASSED'."
        res = ask_auditor(sys_prompt, f"Research:\n{research}\n\nDraft:\n{draft}")
        if res and "PASSED" not in res:
            return f"**Scientific Alert**: {res}"
        return None

    def code_sandbox():
        code_blocks = re.findall(r'```python\n(.*?)\n```', draft, re.DOTALL)
        if not code_blocks:
            code_blocks = re.findall(r'```\n(.*?)\n```', draft, re.DOTALL)
        if not code_blocks: return None
        
        try:
            req = urllib.request.Request(
                'https://emkc.org/api/v2/piston/execute',
                data=json.dumps({
                    "language": "python",
                    "version": "3.10.0",
                    "files": [{"content": code_blocks[0]}]
                }).encode('utf-8'),
                headers={'Content-Type': 'application/json'}
            )
            res = urllib.request.urlopen(req, timeout=3)
            data = json.loads(res.read())
            run = data.get('run', {})
            stderr = run.get('stderr', '').strip()
            stdout = run.get('stdout', '').strip()
            
            if stderr: return f"**Code Sandbox Alert**: The AI's code crashed when tested!\n```text\n{stderr[:300]}\n```"
            if stdout: return f"**Code Sandbox Output**: We securely tested the AI's code. Output:\n```text\n{stdout[:300]}\n```"
            return "**Code Sandbox**: The AI's code ran successfully with no output."
        except Exception:
            return None

    executor4 = concurrent.futures.ThreadPoolExecutor(max_workers=5)
    futures = []
    if cfg.get('research', True): 
        futures.append(executor4.submit(fact_checker))
        futures.append(executor4.submit(arxiv_auditor))
    if cfg.get('privacy', True) or cfg.get('security', True): futures.append(executor4.submit(privacy_security))
    if cfg.get('sentiment', True): futures.append(executor4.submit(sentiment))
    futures.append(executor4.submit(code_sandbox))
    
    try:
        for future in concurrent.futures.as_completed(futures, timeout=3):
            try:
                res = future.result()
                if res:
                    auditors_results.append(res)
            except Exception:
                pass
    except concurrent.futures.TimeoutError:
        pass
    
    executor4.shutdown(wait=False, cancel_futures=True)
                
    return auditors_results

# =============================================================================
# HTTP HANDLER
# =============================================================================

class handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        self.send_json({'status': 'ok', 'service': 'WorstAI', 'engine': 'keyless-6layer'})

    def do_POST(self):
        try:
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length)) if length else {}
        except Exception:
            body = {}

        if self.path != '/api/chat':
            self.send_json({'success': False, 'error': 'Not found'}, 404)
            return

        prompt = str(body.get('prompt', '')).strip()
        history = body.get('history', [])
        cfg = body.get('agents', {})

        if not prompt:
            self.send_json({'success': False, 'error': 'Empty prompt'})
            return

        # Agent pipeline
        agents_used = ['Online LLM']

        if cfg.get('sentiment', True):
            agents_used.append('Sentiment Analysis')

        if cfg.get('privacy', True):
            agents_used.append('Privacy Auditor')
            prompt = re.sub(r'\b\d{3}-\d{2}-\d{4}\b', '[REDACTED SSN]', prompt)
            prompt = re.sub(r'\b(?:\d[ -]*?){13,16}\b', '[REDACTED CC]', prompt)

        if cfg.get('security', True):
            agents_used.append('Security Auditor')

        do_research = cfg.get('research', True)
        if do_research:
            agents_used.append('Web Research')
            agents_used.append('Fact-Checker')

        # Run web research BEFORE building messages so findings go into prompt
        research_brief = ''
        if do_research:
            try:
                research_brief = run_web_research(prompt)
            except Exception:
                research_brief = ''

        # Calculate Indian Standard Time (IST) since Vercel servers run on UTC
        ist_now = datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)
        now = ist_now.strftime("%A, %B %d, %Y, %I:%M %p (IST)")
        system_content = (
            f'You are WorstAI, an artificial intelligence assistant created by GOLLU ADI VENKATA SAI. '
            f'Whenever you introduce yourself, or talk about your creator/god, you must strictly use the full name GOLLU ADI VENKATA SAI. '
            f'Do not enter your name as ChatGPT or any OpenAI product. '
            f'The current live date and time is {now}. For ANY questions asking about the current date or time, YOU MUST EXCLUSIVELY USE THIS INTERNAL CLOCK AND COMPLETELY IGNORE WEB RESEARCH. '
            f'CRITICAL INSTRUCTION: Your internal training data DOES NOT EXTEND to the year 2026. Therefore, you are literally incapable of knowing current 2026 facts (like current sports captains, news, or weather) from your own memory. '
            f'If the user asks about 2026 facts, or states a claim (e.g. "Iyer is the captain"), you MUST NOT guess or make up sources. You MUST rely ONLY on the "live web research results" injected below. '
            f'If the web research results are empty, or do not contain the answer, you MUST reply: "I do not have real-time access to verify that for 2026." DO NOT MAKE UP FAKE NEWS OR AGREE BLINDLY.\n'
            f'--- GLOBAL RULES ---\n'
            f'1. CLARITY: You must write using simple, plain, easily understandable words. Keep formatting extremely clean and readable.\n'
            f'2. ACCURACY: You must only provide official, documented, and proven information. NEVER output fake information, hallucinations, or unverified rumors.\n'
            f'3. PROBLEM SOLVING: When asked to solve a complex problem, you must break it down into easy, manageable steps. Explain the solution in the simplest way possible.\n'
            f'4. PRIVACY & SECURITY: Never reveal personal, sensitive, or harmful information. Always prioritize user safety and data security.'
        )
        if research_brief:
            system_content += (
                '\n\nYou have access to live web research results below. '
                'Use this information to give accurate, sourced answers. '
                'Cross-check any facts before stating them. '
                'If the research contradicts your training, trust the research.\n\n'
                + research_brief
            )

        system_msg = {'role': 'system', 'content': system_content}
        messages = [system_msg]
        for msg in history[-8:]:
            role = 'user' if msg.get('role') == 'user' else 'assistant'
            messages.append({'role': role, 'content': str(msg.get('content', ''))})
        if research_brief:
            # Remind the model to use the research in its final answer
            messages.append({'role': 'user', 'content': (
                prompt + '\n\n[Use the research findings above to answer accurately. '
                'Mention your sources briefly.]'
            )})
        else:
            messages.append({'role': 'user', 'content': prompt})

        try:
            draft, model_used = get_ai_response(messages, prompt)
            
            # Run the parallel multi-agent swarm on the drafted answer
            auditor_notes = run_auditor_swarm(draft, research_brief, cfg, history)
            
            final_answer = draft
            if auditor_notes:
                # Log audit findings to server instead of showing in user chat
                print("--- Swarm Audit ---")
                for note in auditor_notes:
                    print(note)


            self.send_json({
                'success': True,
                'answer': final_answer,
                'agents_used': agents_used,
            })

        except Exception as e:
            self.send_json({'success': False, 'error': str(e)})
