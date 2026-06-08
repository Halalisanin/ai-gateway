#!/usr/bin/env python3
"""
AI Gateway – Unified API with multi-provider fallback, shared memory, and real-time tools.
Now includes: Groq, OpenRouter, Gemini, Hugging Face (10 keys), Inference (2 keys), Novita, Cerebras, Replicate.
Stock tool uses free API (no yfinance dependency).
"""
from flask import Flask, request, jsonify
import os, sys, requests, re, json
from serpapi import GoogleSearch

sys.path.append('/home/liviyo/lib')
from memory_store import init_db, get_recent_context, add_message

init_db()
app = Flask(__name__)

# ------------------- API Keys -------------------
GROQ_KEY = os.environ.get('GROQ_API_KEY')
OPENROUTER_KEY = os.environ.get('OPENROUTER_API_KEY')
GEMINI_KEY = os.environ.get('GEMINI_API_KEY')
SERPAPI_KEY = os.environ.get('SERPAPI_API_KEY')
NEWSAPI_KEY = os.environ.get('NEWSAPI_API_KEY')
NOVITA_KEY = os.environ.get('NOVITA_API_KEY')
CEREBRAS_KEY = os.environ.get('CEREBRAS_API_KEY')
REPLICATE_KEY = os.environ.get('REPLICATE_API_KEY')
# Inference has two keys (rotate)
INFERENCE_KEYS = [os.environ.get('INFERENCE_API_KEY_1'), os.environ.get('INFERENCE_API_KEY_2')]
INFERENCE_KEYS = [k for k in INFERENCE_KEYS if k]
current_inference_index = 0

# Hugging Face keys (10)
hf_keys = [os.environ.get(f'HF_API_KEY_{i}') for i in range(1, 11) if os.environ.get(f'HF_API_KEY_{i}')]
current_hf_index = 0

# ------------------- Provider helpers -------------------
def call_groq(messages):
    if not GROQ_KEY: raise Exception("Groq key missing")
    resp = requests.post('https://api.groq.com/openai/v1/chat/completions',
        headers={'Authorization': f'Bearer {GROQ_KEY}', 'Content-Type': 'application/json'},
        json={'model': 'llama-3.3-70b-versatile', 'messages': messages, 'max_tokens': 600}, timeout=15)
    if resp.status_code != 200: raise Exception(f"Groq error {resp.status_code}")
    return resp.json()['choices'][0]['message']['content']

def call_openrouter(messages):
    if not OPENROUTER_KEY: raise Exception("OpenRouter key missing")
    models = ['google/gemini-2.0-flash-lite-preview-02-05:free',
              'meta-llama/llama-3.2-3b-instruct:free',
              'microsoft/phi-3-mini-128k:free']
    for model in models:
        try:
            resp = requests.post('https://openrouter.ai/api/v1/chat/completions',
                headers={'Authorization': f'Bearer {OPENROUTER_KEY}', 'Content-Type': 'application/json'},
                json={'model': model, 'messages': messages, 'max_tokens': 600}, timeout=15)
            if resp.status_code == 200:
                return resp.json()['choices'][0]['message']['content']
        except: continue
    raise Exception("All OpenRouter models failed")

def call_gemini(messages):
    if not GEMINI_KEY: raise Exception("Gemini key missing")
    prompt = "\n".join([f"{m['role']}: {m['content']}" for m in messages])
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_KEY}"
    resp = requests.post(url, json={'contents': [{'parts': [{'text': prompt}]}],
                                    'generationConfig': {'maxOutputTokens': 600}}, timeout=15)
    if resp.status_code != 200: raise Exception(f"Gemini error {resp.status_code}")
    return resp.json()['candidates'][0]['content']['parts'][0]['text']

def call_huggingface(messages):
    global current_hf_index
    if not hf_keys: raise Exception("No HF keys")
    prompt = "\n".join([f"{m['role']}: {m['content']}" for m in messages])
    for attempt in range(len(hf_keys)*2):
        key = hf_keys[current_hf_index % len(hf_keys)]
        current_hf_index += 1
        try:
            resp = requests.post('https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.3',
                headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
                json={'inputs': prompt, 'parameters': {'max_new_tokens': 600}}, timeout=30)
            if resp.status_code == 200:
                return resp.json()[0]['generated_text'].strip()
            elif resp.status_code in (401,429): continue
        except: continue
    raise Exception("All HF keys exhausted")

def call_inference(messages):
    global current_inference_index
    if not INFERENCE_KEYS: raise Exception("No Inference keys")
    for attempt in range(len(INFERENCE_KEYS)*2):
        key = INFERENCE_KEYS[current_inference_index % len(INFERENCE_KEYS)]
        current_inference_index += 1
        try:
            resp = requests.post('https://api.inference.ai/v1/chat/completions',
                headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
                json={'model': 'gpt-3.5-turbo', 'messages': messages, 'max_tokens': 600}, timeout=15)
            if resp.status_code == 200:
                return resp.json()['choices'][0]['message']['content']
            else:
                continue
        except: continue
    raise Exception("All Inference keys failed")

def call_novita(messages):
    if not NOVITA_KEY: raise Exception("Novita key missing")
    resp = requests.post('https://api.novita.ai/v1/chat/completions',
        headers={'Authorization': f'Bearer {NOVITA_KEY}', 'Content-Type': 'application/json'},
        json={'model': 'meta-llama/llama-3.1-8b-instruct', 'messages': messages, 'max_tokens': 600}, timeout=15)
    if resp.status_code != 200: raise Exception(f"Novita error {resp.status_code}")
    return resp.json()['choices'][0]['message']['content']

def call_cerebras(messages):
    if not CEREBRAS_KEY: raise Exception("Cerebras key missing")
    resp = requests.post('https://api.cerebras.ai/v1/chat/completions',
        headers={'Authorization': f'Bearer {CEREBRAS_KEY}', 'Content-Type': 'application/json'},
        json={'model': 'llama3.1-70b', 'messages': messages, 'max_tokens': 600}, timeout=15)
    if resp.status_code != 200: raise Exception(f"Cerebras error {resp.status_code}")
    return resp.json()['choices'][0]['message']['content']

def call_replicate(messages):
    if not REPLICATE_KEY: raise Exception("Replicate key missing")
    resp = requests.post('https://api.replicate.com/v1/chat/completions',
        headers={'Authorization': f'Bearer {REPLICATE_KEY}', 'Content-Type': 'application/json'},
        json={'model': 'meta/llama-2-70b-chat', 'messages': messages, 'max_tokens': 600}, timeout=15)
    if resp.status_code != 200: raise Exception(f"Replicate error {resp.status_code}")
    return resp.json()['choices'][0]['message']['content']

# ------------------- Tools (stock uses free API) -------------------
def get_weather(city):
    try:
        r = requests.get(f"https://wttr.in/{city}?format=%C+%t+%w+%h", timeout=10)
        return f"Weather in {city}: {r.text.strip()}" if r.status_code == 200 else f"Weather unavailable for {city}"
    except Exception as e: return f"Weather error: {e}"

# def get_stock(ticker):
#     # Use a free API from Yahoo Finance (no yfinance)
#     try:
#         url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
#         resp = requests.get(url, timeout=10)
#         if resp.status_code == 200:
#             data = resp.json()
#             meta = data['chart']['result'][0]['meta']
#             price = meta.get('regularMarketPrice', 'N/A')
#             previous_close = meta.get('previousClose', 1)
#             change = ((price - previous_close) / previous_close) * 100 if previous_close else 0
#             return f"{ticker.upper()}: ${price:.2f} ({change:+.2f}%)"
        else:
            return f"Could not fetch stock {ticker}"
    except Exception as e:
        return f"Stock error: {e}"

def get_news(query):
    if NEWSAPI_KEY:
        try:
            r = requests.get(f"https://newsapi.org/v2/everything?q={query}&apiKey={NEWSAPI_KEY}&pageSize=3", timeout=10)
            if r.status_code == 200:
                articles = r.json().get('articles', [])
                if articles:
                    return "News:\n" + "\n".join([f"- {a['title']} ({a['source']['name']})" for a in articles[:3]])
        except: pass
    if SERPAPI_KEY:
        params = {"q": query, "api_key": SERPAPI_KEY, "engine": "google_news", "num": 3}
        try:
            results = GoogleSearch(params).get_dict()
            news = results.get("news_results", [])
            if news:
                return "News:\n" + "\n".join([f"- {n.get('title')} ({n.get('source')})" for n in news[:3]])
        except: pass
    return f"Could not fetch news for '{query}'."

def perform_search(query):
    if not SERPAPI_KEY: return "SerpAPI key missing"
    params = {"q": query, "api_key": SERPAPI_KEY, "engine": "google", "num": 3}
    try:
        results = GoogleSearch(params).get_dict()
        organic = results.get("organic_results", [])
        if not organic: return f"No results for '{query}'."
        output = f"Search results for '{query}':\n"
        for i, r in enumerate(organic[:3], 1):
            output += f"{i}. {r.get('title')}\n   {r.get('snippet')}\n"
        return output
    except Exception as e: return f"Search error: {e}"

def handle_tool(command):
    m = re.match(r'\[(\w+):\s*(.+?)\]', command, re.IGNORECASE)
    if not m: return None
    tool, arg = m.group(1).lower(), m.group(2).strip()
    if tool == 'weather': return get_weather(arg)
# # # #     if tool == 'stock':   return get_stock(arg)
    if tool == 'news':    return get_news(arg)
    if tool == 'search':  return perform_search(arg)
    return f"Unknown tool: {tool}"

# ------------------- Main endpoint with fallback chain -------------------
@app.route('/v1/chat/completions', methods=['POST'])
def chat():
    session_id = request.headers.get('X-Session-Id', 'default')
    user_msg = None
    for m in request.json.get('messages', []):
        if m.get('role') == 'user':
            user_msg = m.get('content')
            break
    if not user_msg:
        return jsonify({'error': 'No user message'}), 400

    context = get_recent_context(session_id, n=5)
    messages = [{'role': r, 'content': c} for r, c in context]
    messages.append({'role': 'user', 'content': user_msg})

    messages.insert(0, {'role': 'system', 'content': (
        "You have tools: WEATHER, STOCK, NEWS, SEARCH. Use exactly [TOOL: argument] if needed. "
        "After receiving tool result, provide final answer. If no tool needed, answer normally."
    )})

    def call_llm(msgs):
        try: return call_groq(msgs)
        except: pass
        try: return call_openrouter(msgs)
        except: pass
        try: return call_gemini(msgs)
        except: pass
        try: return call_huggingface(msgs)
        except: pass
        try: return call_inference(msgs)
        except: pass
        try: return call_novita(msgs)
        except: pass
        try: return call_cerebras(msgs)
        except: pass
        try: return call_replicate(msgs)
        except: pass
        raise Exception("All providers failed")

    final_reply = None
    for _ in range(3):
        reply = call_llm(messages)
        tool_cmd = re.search(r'\[(WEATHER|STOCK|NEWS|SEARCH):\s*(.+?)\]', reply, re.IGNORECASE)
        if tool_cmd:
            full = tool_cmd.group(0)
            print(f"🔧 Tool: {full}")
            result = handle_tool(full)
            messages.append({'role': 'assistant', 'content': reply})
            messages.append({'role': 'user', 'content': f"Tool result: {result}\nNow answer."})
        else:
            final_reply = reply
            break

    if not final_reply:
        final_reply = "I couldn't complete the request."

    add_message(session_id, 'gateway', 'user', user_msg)
    add_message(session_id, 'gateway', 'assistant', final_reply)
    return jsonify({'choices': [{'message': {'role': 'assistant', 'content': final_reply}}]})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
