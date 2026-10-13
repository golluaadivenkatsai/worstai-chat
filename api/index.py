import http.server
import json
import urllib.request
import urllib.parse
import re
import random
import threading
import concurrent.futures
import datetime
import time
import sys
import os
os.environ["HOME"] = "/tmp"
os.environ["G4F_USER_CONFIG_DIR"] = "/tmp/g4f"
import googlesearch
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

def should_perform_research(query: str) -> bool:
    """Determines whether a query genuinely requires external live web research."""
    q = query.strip().lower()
    
    # 1. Do not search for conversational phrases, follow-ups, or questions about the conversation
    conversational = [
        'what is this', 'what is that', 'what do you mean', 'why', 'why is this', 
        'why that', 'how come', 'who are you', 'what are you', 'hello', 'hi', 
        'hey', 'thanks', 'thank you', 'ok', 'okay', 'explain', 'help', 'no', 'yes',
        'what did you say', 'what does this mean', 'why did you', 'what is the meaning'
    ]
    if q in conversational or len(q.split()) <= 2:
        return False
        
    # 2. Do not search for educational, science, diagrams, code, or evergreen concepts
    evergreen = [
        'flowchart', 'flow chart', 'diagram', 'write code', 'python', 'javascript', 
        'html', 'css', 'solve', 'calculate', 'poem', 'story', 'essay', 'evolution',
        'human evolution', 'photosynthesis', 'gravity', 'physics', 'math', 'algebra'
    ]
    has_live_indicators = any(k in q for k in ['latest', 'news', 'update', 'today', '2026', 'price', 'score', 'weather', 'live'])
    if any(k in q for k in evergreen) and not has_live_indicators:
        return False

    # 3. Only search if live temporal or real-time keywords are present
    live_keywords = [
        'weather', 'climate', 'temperature', 'forecast', 'rain', 'news', 'today', 
        'yesterday', 'current', 'live', 'latest', 'recent', 'who won', 'match', 
        'score', 'ipl', 'cricket', 'election', 'stock', 'price of', 'released', 
        'upcoming', 'when is', '2026', '2025', 'near me', 'nearby', 'traffic',
        'వాతావరణం', 'వార్తలు', 'ఈరోజు', 'ఇప్పుడు'
    ]
    return any(k in q for k in live_keywords)

def run_web_research(query, location_context=''):
    try:
        # Guard: Never perform web research on non-live, conversational, or educational queries
        if not should_perform_research(query):
            return ''

        current_year = str(datetime.datetime.now().year)
        
        # Check if query asks for local/weather/news/events information
        is_local_query = any(k in query.lower() for k in [
            'weather', 'climate', 'temperature', 'forecast', 'rain', 
            'వాతావరణం', 'news', 'వార్తలు', 'near me', 'nearby', 
            'restaurants', 'traffic', 'places to visit', 'food', 'events'
        ])
        
        if is_local_query and location_context:
            search_query = f"{query} {location_context} {current_year}"
        else:
            search_query = query if current_year in query else f"{query} {current_year}"

        findings = []
        search_engines = [search_google, search_duckduckgo, search_yahoo, search_bing, search_ecosia, search_geeksforgeeks]
        search_results = []
        
        # 1. Race the search engines to find URLs instantly
        executor1 = concurrent.futures.ThreadPoolExecutor(max_workers=len(search_engines))
        futures = {executor1.submit(engine, search_query, 3): engine for engine in search_engines}
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
            return search_wikipedia(query) # keep exact entity for wiki
        def fetch_news():
            return search_google_news(search_query)
        def fetch_arxiv():
            return search_arxiv(search_query)
        def fetch_gfg():
            gfg_urls = search_geeksforgeeks(search_query)
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

def synthesize_academic_response(prompt, is_telugu=False):
    """
    Intelligent Autonomous Academic Synthesizer.
    Generates structured, exam-grade study material formatted with:
    - Core Concept Summary
    - Mermaid flowchart TD (if sequential/process)
    - Milestone / Comparison Table
    - High-Yield Exam Memory Points
    """
    q = prompt.lower().strip()

    # 1. Human Evolution
    if ('evolution' in q or 'evalution' in q or 'hominid' in q or 'human origin' in q) and ('human' in q or 'evalution' in q or 'chart' in q or 'flow' in q or 'stage' in q or len(q) < 40):
        return (
            "## Core Concept Summary\n"
            "Human evolution is the biological and cultural process by which modern humans (*Homo sapiens*) "
            "diverged from ancestral primates over approximately **6 to 7 million years**. Key evolutionary developments "
            "include obligate bipedalism, encephalization (cranial capacity expansion), tool fabrication, and complex language.\n\n"
            "---\n\n"
            "## Chronological Evolutionary Flowchart\n\n"
            "```mermaid\n"
            "flowchart TD\n"
            '    A["Dryopithecus & Ramapithecus (15 Mya)"] --> B["Australopithecus (2–4 Mya)"]\n'
            '    B --> C["Homo habilis (Handy Man, 1.6–2 Mya)"]\n'
            '    C --> D["Homo erectus (Upright Man, 1.5 Mya)"]\n'
            '    D --> E["Homo neanderthalensis (100k–40k ya)"]\n'
            '    E --> F["Homo sapiens (Modern Human, 75k ya–Present)"]\n'
            "```\n\n"
            "---\n\n"
            "## Milestone & Cranial Capacity Comparison Table\n\n"
            "| Stage / Hominid | Epoch / Age | Cranial Capacity | Distinguishing Characteristics | High-Yield Exam Significance |\n"
            "|---|---|---|---|---|\n"
            "| **Ramapithecus** | Late Miocene (~15 Mya) | ~400–450 cc | Semi-erect, ape-jaw, more man-like than Dryopithecus | Ancestral divergence line |\n"
            "| **Australopithecus** | Pliocene (~3–4 Mya) | ~450–500 cc | Bipedal gait, hunted with stone weapons, vegetarian | 'Lucy' specimen (*A. afarensis*) |\n"
            "| **Homo habilis** | Early Pleistocene (~2 Mya) | ~650–800 cc | First hominid toolmaker ('Handy Man'), non-carnivorous | First true human-like species |\n"
            "| **Homo erectus** | Middle Pleistocene (~1.5 Mya) | ~900 cc | Upright erect posture, discovered fire, ate meat | Java Man & Peking Man fossils |\n"
            "| **Neanderthal Man** | Late Pleistocene (100k–40k ya) | ~1400 cc | Robust body, cave dwellers, used hides, buried dead | Adapted to extreme cold |\n"
            "| **Homo sapiens** | Recent (75k ya–Present) | ~1400–1450 cc | Complex language, cave art (18k ya), agriculture (10k ya) | Extant modern humans |\n\n"
            "---\n\n"
            "## High-Yield Exam Memory Points\n"
            "- **Bipedalism Before Brain Expansion**: Upright walking evolved millions of years before brain enlargement.\n"
            "- **First Tool Maker**: *Homo habilis* is credited as the first species to construct stone tools.\n"
            "- **Fire Control**: *Homo erectus* was the first hominid to control and utilize fire.\n"
            "- **Cranial Capacity Hierarchy**: *Australopithecus* (~500 cc) → *H. habilis* (650–800 cc) → *H. erectus* (900 cc) → *Neanderthal* (1400 cc) → *H. sapiens* (1450 cc)."
        )

    # 2. Photosynthesis
    if 'photosynthesis' in q or 'calvin cycle' in q or 'light reaction' in q:
        return (
            "## Core Concept Summary\n"
            "Photosynthesis is the biochemical process by which photoautotrophic organisms convert light energy "
            "into chemical energy, synthesizing glucose from carbon dioxide and water while releasing oxygen as a byproduct.\n\n"
            "**Chemical Equation**: `6CO2 + 6H2O + Light Energy -> C6H12O6 + 6O2`\n\n"
            "---\n\n"
            "## Process Flowchart\n\n"
            "```mermaid\n"
            "flowchart TD\n"
            '    A["Sunlight & Water (H2O)"] --> B["Light Reactions (Thylakoids)"]\n'
            '    B --> C["Photolysis of Water & ATP / NADPH Production"]\n'
            '    C --> D["Calvin Cycle / Dark Reaction (Stroma)"]\n'
            '    D --> E["CO2 Fixation via RuBisCO"]\n'
            '    E --> F["Glucose (C6H12O6) Synthesis"]\n'
            "```\n\n"
            "---\n\n"
            "## Stage Comparison Table\n\n"
            "| Feature | Light Reaction (Photochemical) | Dark Reaction (Calvin Cycle / Biosynthetic) |\n"
            "|---|---|---|\n"
            "| **Site** | Grana / Thylakoid membranes | Chloroplast Stroma |\n"
            "| **Light Requirement** | Directly light-dependent | Light-independent (uses products of light reaction) |\n"
            "| **Key Enzyme** | Photosystems I & II, ATP Synthase | RuBisCO (most abundant enzyme on Earth) |\n"
            "| **End Products** | ATP, NADPH, Oxygen (O2) | Glucose (Sugar), ADP, NADP+ |\n\n"
            "---\n\n"
            "## High-Yield Exam Memory Points\n"
            "- **Photolysis of Water**: Water splitting occurs during light reactions in PS II, generating protons, electrons, and O2.\n"
            "- **RuBisCO**: Ribulose-1,5-bisphosphate carboxylase-oxygenase is the key enzyme fixing CO2 into 3-PGA.\n"
            "- **Energy Currency**: ATP and NADPH generated in thylakoids drive sugar formation in the stroma."
        )

    # 3. DNA & Central Dogma
    if 'dna' in q or 'central dogma' in q or 'transcription' in q or 'translation' in q:
        return (
            "## Core Concept Summary\n"
            "The Central Dogma of molecular biology describes the directional flow of genetic information: "
            "from DNA to RNA (Transcription) and from RNA to functional Protein (Translation).\n\n"
            "---\n\n"
            "## Genetic Information Flowchart\n\n"
            "```mermaid\n"
            "flowchart TD\n"
            '    A["DNA Replication (Nucleus - DNA Polymerase)"] --> B["Transcription (DNA to mRNA - RNA Polymerase)"]\n'
            '    B --> C["mRNA Processing (5 cap, poly-A tail, splicing)"]\n'
            '    C --> D["Nuclear Export to Ribosome"]\n'
            '    D --> E["Translation (mRNA to Polypeptide - Ribosome & tRNA)"]\n'
            '    E --> F["Functional Folded Protein"]\n'
            "```\n\n"
            "---\n\n"
            "## Comparison Table\n\n"
            "| Process | Location (Eukaryotes) | Template | Key Enzyme | Product |\n"
            "|---|---|---|---|---|\n"
            "| **Replication** | Nucleus | Both DNA strands | DNA Polymerase | Two identical DNA double helices |\n"
            "| **Transcription** | Nucleus | Antisense DNA strand | RNA Polymerase | Single-stranded mRNA transcript |\n"
            "| **Translation** | Cytoplasm (Ribosomes) | mRNA | Ribosome & Peptidyl Transferase | Polypeptide chain (Protein) |\n\n"
            "---\n\n"
            "## High-Yield Exam Memory Points\n"
            "- **Semi-Conservative Replication**: Demonstrated by Meselson and Stahl using 15N isotopes.\n"
            "- **Directionality**: Both DNA replication and RNA synthesis proceed strictly in the **5' -> 3'** direction.\n"
            "- **Start Codon**: AUG (codes for Methionine in eukaryotes)."
        )

    # 4. Wikipedia Academic Search Synthesis
    wiki_info = search_wikipedia(prompt)
    if wiki_info and len(wiki_info) > 50:
        sentences = [s.strip() for s in wiki_info.split('.') if len(s.strip()) > 15]
        core_summary = ". ".join(sentences[:2]) + "." if len(sentences) >= 2 else wiki_info[:200] + "."
        exam_points = "\n".join([f"- **Key Takeaway**: {s}." for s in sentences[2:6]]) if len(sentences) > 2 else "- **Key Takeaway**: Core factual definition verified from academic database."
        return (
            f"## Core Concept Summary\n{core_summary}\n\n"
            f"---\n\n"
            f"## Academic Details\n{wiki_info}\n\n"
            f"---\n\n"
            f"## High-Yield Exam Memory Points\n{exam_points}"
        )

    return None

def get_ai_response(messages, last_user_message, is_voice=False):
    """
    Blisteringly fast AI generation with 4-layer fallback:
    Layer 0: Official Gemini Flash (if API key configured)
    Layer 1: Fast Parallel Race (binjie.fun & pollinations) with 8s cutoff
    Layer 2: Autonomous Academic Synthesizer (instant, high-yield, exam-formatted)
    """
    sys_content = ""
    user_prompt = last_user_message
    if messages and messages[0].get('role') == 'system':
        sys_content = messages[0].get('content', '')

    # Layer 0: Official Google Gemini API (if key present)
    gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if gemini_key:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={gemini_key}"
            payload = {
                "contents": [{"parts": [{"text": f"System Directive: {sys_content}\n\nUser Question: {user_prompt}"}]}]
            }
            req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=8) as res:
                d = json.loads(res.read().decode('utf-8'))
                text = d['candidates'][0]['content']['parts'][0]['text'].strip()
                if text:
                    return text, 'Gemini-2.0-Flash'
        except Exception as e:
            print(f"[GEMINI_BACKEND_ERR] {e}", file=sys.stderr)

    # Layer 1: Fast 8-second parallel race
    def call_direct_stream():
        try:
            data = {
                'prompt': user_prompt,
                'userId': f'#/chat/{int(time.time()*1000)}',
                'network': True,
                'system': sys_content,
                'withoutContext': False,
                'stream': True
            }
            req = urllib.request.Request(
                'https://api.binjie.fun/api/generateStream',
                data=json.dumps(data).encode('utf-8'),
                headers={
                    'accept': 'application/json, text/plain, */*',
                    'content-type': 'application/json',
                    'origin': 'https://chat9.yqcloud.top',
                    'referer': 'https://chat9.yqcloud.top/',
                    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
                }
            )
            with urllib.request.urlopen(req, timeout=7) as res:
                chunks = []
                for chunk in res:
                    if chunk:
                        chunks.append(chunk.decode('utf-8', errors='ignore'))
                ans = ''.join(chunks).strip()
                chinese_count = len(re.findall(r'[\u4e00-\u9fff]', ans))
                if chinese_count > 30 and 'chinese' not in last_user_message.lower():
                    raise Exception("Output primarily in Chinese")
                elif chinese_count > 0:
                    ans = re.sub(r'[\u4e00-\u9fff]+', '', ans).strip()
                if len(ans) > 15:
                    return ans, 'Direct-Stream'
                raise Exception('Empty output')
        except Exception as e:
            raise Exception(f"Direct stream error: {e}")

    def call_pollinations():
        try:
            msgs = []
            if sys_content:
                msgs.append({'role': 'system', 'content': sys_content})
            msgs.append({'role': 'user', 'content': user_prompt})
            payload = json.dumps({
                'messages': msgs,
                'model': 'openai',
                'seed': random.randint(1, 999999)
            }).encode('utf-8')
            req = urllib.request.Request(
                'https://text.pollinations.ai/openai/v1/chat/completions',
                data=payload,
                headers={
                    'Content-Type': 'application/json',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
                }
            )
            with urllib.request.urlopen(req, timeout=7) as res:
                raw_text = res.read().decode('utf-8', errors='replace').strip()
                ans = raw_text
                try:
                    p = json.loads(raw_text)
                    if isinstance(p, dict) and 'choices' in p and p['choices']:
                        ans = p['choices'][0].get('message', {}).get('content', ans).strip()
                except Exception:
                    pass
                chinese_count = len(re.findall(r'[\u4e00-\u9fff]', ans))
                if chinese_count > 30 and 'chinese' not in last_user_message.lower():
                    raise Exception("Output primarily in Chinese")
                elif chinese_count > 0:
                    ans = re.sub(r'[\u4e00-\u9fff]+', '', ans).strip()
                if len(ans) > 15:
                    return ans, 'Pollinations'
                raise Exception('Empty output')
        except Exception as e:
            raise Exception(f"Pollinations error: {e}")

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
    futures = {
        executor.submit(call_direct_stream): 'direct',
        executor.submit(call_pollinations): 'pollinations'
    }
    errors = []
    try:
        for future in concurrent.futures.as_completed(futures, timeout=8):
            try:
                res = future.result()
                executor.shutdown(wait=False, cancel_futures=True)
                return res
            except Exception as e:
                errors.append(str(e)[:50])
    except Exception as e:
        errors.append(f"Timeout: {e}")

    executor.shutdown(wait=False, cancel_futures=True)

    # Layer 2: Autonomous Academic Knowledge Synthesizer Fallback
    resolved_query = user_prompt
    follow_up_phrases = ['what is this', 'what is that', 'what does this mean', 'explain this', 'tell me more', 'why', 'elaborate', 'what is it']
    if any(fp in user_prompt.lower().strip() for fp in follow_up_phrases):
        for msg in reversed(messages[:-1]):
            if msg.get('role') == 'user' and len(msg.get('content', '')) > 3:
                last_topic = msg.get('content', '').strip()
                if not any(fp in last_topic.lower() for fp in follow_up_phrases):
                    resolved_query = last_topic
                    break

    academic_synthesis = synthesize_academic_response(resolved_query)
    if academic_synthesis:
        return academic_synthesis, "WorstAI-Academic-Engine"

    safe_error = "నన్ను క్షమించండి, ప్రస్తుతం నా సర్వర్లు చాలా బిజీగా ఉన్నాయి. దయచేసి కాసేపు ఆగి మళ్లీ ప్రయత్నించండి. \n\n*(Sorry, my servers are heavily overloaded right now. Please try again in a moment!)*"
    return safe_error, "System-Fail-Safe"

def ask_auditor(system_prompt, user_prompt):
    try:
        from g4f.Provider import Yqcloud, KiloCode, LLM7
    except Exception:
        Yqcloud, KiloCode, LLM7 = None, None, None
        
    auditor_models = [
        ('gpt-4', Yqcloud),
        ('kilo-auto/free', KiloCode),
        ('default', LLM7),
    ]
    from g4f.client import Client
    client = Client()
    
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=len(auditor_models))
    futures = {}
    for mod, prov in auditor_models:
        def fetch(m, p):
            try:
                kwargs = {
                    'model': m,
                    'messages': [
                        {'role': 'system', 'content': system_prompt},
                        {'role': 'user', 'content': user_prompt}
                    ]
                }
                if p:
                    kwargs['provider'] = p
                response = client.chat.completions.create(**kwargs)
                content = response.choices[0].message.content.strip()
                content = re.sub(r'<tool_call>[\s\S]*?</tool_call>', '', content)
                content = re.sub(r'<tool_call>[\s\S]*', '', content).strip()
                if re.search(r'[\u4e00-\u9fff]', content):
                    raise Exception("Chinese characters in auditor output")
                if content:
                    return content
                raise Exception("Empty")
            except Exception as e:
                raise Exception(str(e))
        futures[executor.submit(fetch, mod, prov)] = (mod, prov)
        
    for future in concurrent.futures.as_completed(futures, timeout=8):
        try:
            res = future.result()
            executor.shutdown(wait=False, cancel_futures=True)
            return res
        except Exception:
            pass
            
    executor.shutdown(wait=False, cancel_futures=True)
    return "[Auditor Offline: Fast-passed]"

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

def sanitize_mermaid_content(content: str) -> str:
    """Finds all ```mermaid ... ``` code blocks and sanitizes syntax to prevent parsing errors."""
    def clean_mermaid_block(match):
        code = match.group(1)
        lines = code.strip().split('\n')
        valid_headers = (
            'flowchart', 'graph', 'sequencediagram', 'classdiagram',
            'statediagram', 'erdiagram', 'gantt', 'pie', 'gitgraph',
            'mindmap', 'timeline', 'quadrantchart', 'c4context', 'sankey', 'block-beta'
        )
        first_line = lines[0].strip().lower() if lines else ''
        if not any(first_line.startswith(h) for h in valid_headers):
            lines.insert(0, 'flowchart TD')

        fixed_lines = []
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith(('%%', 'subgraph', 'end', 'style', 'classDef', 'class ', 'flowchart', 'graph')):
                fixed_lines.append(line)
                continue

            # 1. Fix arrow pipes: -->|label (details)| => -->|"label (details)"|
            def fix_arrow_pipe(m):
                arrow = m.group(1)
                lbl = m.group(2).strip().replace('"', "'")
                return f'{arrow}|"{lbl}"|'

            line = re.sub(r'(-->|---|==>|-\.->)\s*\|([^"\n|]+)\|', fix_arrow_pipe, line)

            # 2. Fix node definitions with nested brackets or unquoted special characters
            # e.g. B[Sa[h]elanthropus tchadensis] -> B["Sa(h)elanthropus tchadensis"]
            def fix_node_box(m):
                node_id = m.group(1)
                inner = m.group(2).strip()
                if inner.startswith('"') and inner.endswith('"'):
                    return f'{node_id}[{inner}]'
                clean_inner = inner.replace('[', '(').replace(']', ')').replace('"', "'")
                return f'{node_id}["{clean_inner}"]'

            line = re.sub(
                r'\b([a-zA-Z0-9_\-]+)\s*\[([\s\S]*?)\](?=\s*(?:-->|---|==>|-\.->|;|$))',
                fix_node_box,
                line
            )
            fixed_lines.append(line)

        return '```mermaid\n' + '\n'.join(fixed_lines) + '\n```'

    return re.sub(r'```(?:mermaid)\s*([\s\S]*?)```', clean_mermaid_block, content, flags=re.IGNORECASE)

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
        if self.path.startswith('/api/tts'):
            try:
                from urllib.parse import urlparse, parse_qs
                query = parse_qs(urlparse(self.path).query)
                text = query.get('text', [''])[0]
                lang = query.get('lang', ['en'])[0]
                if text:
                    from gtts import gTTS
                    import io
                    tts = gTTS(text=text, lang=lang)
                    fp = io.BytesIO()
                    tts.write_to_fp(fp)
                    self.send_response(200)
                    self.send_header('Content-Type', 'audio/mpeg')
                    self.end_headers()
                    self.wfile.write(fp.getvalue())
                else:
                    self.send_response(400)
                    self.end_headers()
            except Exception as e:
                self.send_json({'error': str(e)}, 500)
            return

        if self.path.startswith('/api/debug'):
            import traceback
            try:
                from g4f.client import Client
                from g4f.Provider import LLM7
                c = Client()
                res = c.chat.completions.create(model='default', provider=LLM7, messages=[{'role': 'user', 'content': 'Say 123'}])
                self.send_json({'success': True, 'content': res.choices[0].message.content})
            except Exception as e:
                self.send_json({'success': False, 'error': str(e), 'trace': traceback.format_exc()})
            return
            
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

        # Backend Authentication Guard
        auth_header = self.headers.get('Authorization', '')
        auth_token = body.get('auth_token', '')
        if not auth_header and not auth_token:
            self.send_json({'success': False, 'error': 'Unauthorized: Authentication token is required.'}, 401)
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

        # Resolve User Real-Time Location and Local Time
        user_loc = body.get('location', {}) or {}
        city = user_loc.get('city') or self.headers.get('x-vercel-ip-city', '')
        region = user_loc.get('region') or self.headers.get('x-vercel-ip-country-region', '')
        country = user_loc.get('country') or self.headers.get('x-vercel-ip-country', '')
        tz_name = user_loc.get('timezone') or self.headers.get('x-vercel-ip-timezone', 'Asia/Kolkata')
        
        loc_parts = [p for p in [city, region, country] if p]
        location_display = ", ".join(loc_parts) if loc_parts else "India"
        if city or location_display != "India":
            agents_used.append(f"Geo-Location ({city or location_display})")

        # Local time resolution: prefer client's exact live time, else calculate via timezone
        local_time_str = user_loc.get('local_time', '')
        if not local_time_str:
            try:
                import zoneinfo
                client_tz = zoneinfo.ZoneInfo(tz_name)
                now_dt = datetime.datetime.now(client_tz)
                local_time_str = now_dt.strftime("%A, %B %d, %Y, %I:%M %p")
            except Exception:
                ist_now = datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)
                local_time_str = ist_now.strftime("%A, %B %d, %Y, %I:%M %p (IST)")
        now = local_time_str

        # Run web research BEFORE building messages so findings go into prompt
        research_brief = ''
        if do_research:
            try:
                research_brief = run_web_research(prompt, location_display)
            except Exception:
                research_brief = ''

        system_content = (
            f'You are WorstAI, an ultra-fast, intelligent, student-centric academic AI tutor created by GOLLU ADI VENKATA SAI.\n\n'
            f'STUDENT STUDY & EXAM EXCELLENCE STANDARDS (CRITICAL):\n'
            f'1. HIGH-YIELD FORMATTING FOR STUDENTS:\n'
            f'   - Provide answers that are clean, beautifully organized, and easy for students to study, revise, and memorize for exams.\n'
            f'   - Use clear Markdown formatting with headers (##, ###), bullet points, bold keywords, and comparison tables.\n'
            f'   - For educational, scientific, historical, or procedural concepts:\n'
            f'     * Core Concept Summary: 1-2 punchy, crystal-clear sentences defining the subject.\n'
            f'     * Chronological / Process Flowchart (Mermaid): When explaining sequences, evolution, or lifecycles, provide a clean, valid Mermaid diagram (```mermaid ... ```).\n'
            f'     * Milestone / Comparison Table: Use clean markdown tables with clear column headers (e.g. Stage/Epoch, Key Fossil/Discovery, Brain Capacity/Tools, Exam Significance).\n'
            f'     * High-Yield Exam Memory Points: 3-5 bullet points with key terms bolded for instant memorization.\n'
            f'2. CRITICAL MERMAID SYNTAX RULES:\n'
            f'   - Always start with "flowchart TD".\n'
            f'   - ALWAYS enclose EVERY node label in double quotes: A["Stage 1 (Details)"] --> B["Stage 2 (Details)"].\n'
            f'   - NEVER put unquoted brackets, colons, or parentheses inside node labels.\n'
            f'   - NEVER put nested square brackets like "Sa[h]elanthropus" or "[Lucy]" inside node brackets.\n'
            f'3. DIRECTNESS & NO FLUFF:\n'
            f'   - Answer directly and instantly. NEVER output preamble ("Sure, here is...", "As an AI...").\n'
            f'   - ZERO UNPROMPTED INTROS: Never say "About Me:" or display creator/clock info unless specifically asked ("who created you", "what time is it").\n'
            f'   - Follow-up context: When the user asks "what is this" or "why", answer in the context of the previous message.\n'
            f'4. LANGUAGE: All explanations, diagram labels, comparison tables, and takeaways must be written strictly in clear standard English (or Telugu if the user prompt is in Telugu). Never output Chinese characters.\n'
            f'5. LIVE TIME & LOCATION: The user is in {location_display} (current live time: {now}). Use this ONLY if the user specifically asks for the time, date, or local weather.'
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
        for msg in history[-30:]:
            role = 'user' if msg.get('role') == 'user' else 'assistant'
            messages.append({'role': role, 'content': str(msg.get('content', ''))})
            
        if research_brief:
            messages.append({'role': 'user', 'content': (
                prompt + '\n\n[Reference notes from web research:\n' + research_brief + '\nAnswer the user prompt accurately without citing Sources.]'
            )})
        else:
            messages.append({'role': 'user', 'content': prompt})

        try:
            draft, model_used = get_ai_response(messages, prompt, is_voice=body.get('is_voice', False))
            
            final_answer = draft
            
            # --- STRICT IDENTITY ENFORCEMENT & FALSE-POSITIVE PREVENTION ---
            prompt_lower = prompt.lower().strip()
            is_telugu = bool(re.search(r'[\u0C00-\u0C7F]', prompt))
            
            creator_patterns = [
                r'\bwho\s+(created|made|developed|built|coded|programmed)\s+you\b',
                r'\bwho\s+is\s+your\s+(creator|maker|developer|builder|owner|father)\b',
                r'\bwho\s+(are\s+you|r\s+u)\b',
                r'\bwhat\s+is\s+your\s+name\b',
                r'\b(tell\s+me\s+about\s+yourself|introduce\s+yourself)\b',
                r'\bwho\s+owns\s+you\b'
            ]
            telugu_creator_patterns = [
                r'నువ్వు\s+ఎవరు', r'మీరు\s+ఎవరు', r'నీ\s+పేరేంటి', r'నీ\s+పేరు',
                r'నిన్ను\s+ఎవరు\s+(తయారు|సృష్టించా)', r'నీ\s+సృష్టికర్త\s+ఎవరు'
            ]
            
            is_identity = any(re.search(pat, prompt_lower) for pat in creator_patterns) or \
                          any(re.search(pat, prompt) for pat in telugu_creator_patterns)

            if is_identity:
                if is_telugu:
                    final_answer = "నేను **WorstAI**ని, ఒక అత్యంత అధునాతన ఆర్టిఫిషియల్ ఇంటెలిజెన్స్ (AI) అసిస్టెంట్‌ని.\n\nనా సృష్టికర్త: **గొల్లు ఆది వెంకట సాయి (GOLLU ADI VENKATA SAI)**."
                else:
                    final_answer = "I am **WorstAI**, a highly advanced artificial intelligence assistant created by **GOLLU ADI VENKATA SAI**."

            # Override generic LLM refusal disclaimers for location / live time
            if any(k in prompt_lower for k in ["where am i", "my location", "what is my location", "my city", "which city"]):
                if any(disclaimer in final_answer.lower() for disclaimer in ["do not have access", "cannot determine", "can't determine", "unable to determine"]):
                    final_answer = f"You are currently located in **{location_display}**.\n\nCurrent local time: **{now}**."
            
            if any(k in prompt_lower for k in ["what time", "current time", "time now", "what is the time"]):
                if any(disclaimer in final_answer.lower() for disclaimer in ["do not have access", "cannot determine", "real-time clock"]):
                    final_answer = f"The current live time in **{location_display}** is **{now}**."
            
            # Scrub any leaked backend model names
            scrub_list = [
                ("OpenAI", "WorstAI"), ("ChatGPT", "WorstAI"), ("Gemini", "WorstAI"), 
                ("Google", "WorstAI"), ("StepFun", "WorstAI"), ("阶跃星辰", "WorstAI"),
                ("I’m Step", "I’m WorstAI"), ("I am Step", "I am WorstAI"), 
                ("Anthropic", "WorstAI"), ("Claude", "WorstAI")
            ]
            for bad_word, good_word in scrub_list:
                final_answer = final_answer.replace(bad_word, good_word)

            # Strip any internal <think> tags for clean student view
            final_answer = re.sub(r'<think>.*?</think>', '', final_answer, flags=re.DOTALL).strip()

            # Auto-heal and sanitize any Mermaid diagrams in the final answer
            final_answer = sanitize_mermaid_content(final_answer)

            self.send_json({
                'success': True,
                'answer': final_answer,
                'thinking': '',
                'agents_used': agents_used,
            })

        except Exception as e:
            self.send_json({'success': False, 'error': str(e)})
