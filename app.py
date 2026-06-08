#!/usr/bin/env python3
from flask import Flask, request, jsonify
import os, sys, requests, re, json
from serpapi import GoogleSearch

sys.path.append('/home/liviyo/lib')
from memory_store import init_db, get_recent_context, add_message

init_db()
app = Flask(__name__)

# API keys
GROQ_KEY = os.environ.get('GROQ_API_KEY')
OPENROUTER_KEY = os.environ.get('OPENROUTER_API_KEY')
GEMINI_KEY = os.environ.get('GEMINI_API_KEY')
SERPAPI_KEY = os.environ.get('SERPAPI_API_KEY')

# Hugging Face keys (10)
hf_keys = []
for i in range(1, 11):
    key = os.environ.get(f'HF_API_KEY_{i}')
    if key:
        hf_keys.append(key)
current_hf_index = 0

# ---------- Provider helpers (unchanged) ----------
def call_groq(messages):
    if not GROQ_KEY:
        raise Exception("Groq key not set")
    resp = requests.post(
        'https://api.groq.com/openai/v1/chat/completions',
        headers={'Authorization': f'Bearer {GROQ_KEY}', 'Content-Type': 'application/json'},
        json={'model': 'llama-3.3-70b-versatile', 'messages': messages, 'max_tokens': 500},
        timeout=15
    )
    if resp.status_code != 200:
        raise Exception(f"Groq error {resp.status_code}")
    return resp.json()['choices'][0]['message']['content']

def call_openrouter(messages):
    if not OPENROUTER_KEY:
        raise Exception("OpenRouter key not set")
    models = [
        'google/gemini-2.0-flash-lite-preview-02-05:free',
        'meta-llama/llama-3.2-3b-instruct:free',
        'microsoft/phi-3-mini-128k:free'
    ]
    for model in models:
        try:
            resp = requests.post(
                'https://openrouter.ai/api/v1/chat/completions',
                headers={'Authorization': f'Bearer {OPENROUTER_KEY}', 'Content-Type': 'application/json'},
                json={'model': model, 'messages': messages, 'max_tokens': 500},
                timeout=15
            )
            if resp.status_code == 200:
                return resp.json()['choices'][0]['message']['content']
        except:
            continue
    raise Exception("All OpenRouter models failed")

def call_gemini(messages):
    if not GEMINI_KEY:
        raise Exception("Gemini key not set")
    prompt = "\n".join([f"{m['role']}: {m['content']}" for m in messages])
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_KEY}"
    resp = requests.post(url, json={'contents': [{'parts': [{'text': prompt}]}], 'generationConfig': {'maxOutputTokens': 500}}, timeout=15)
    if resp.status_code != 200:
        raise Exception(f"Gemini error: {resp.text}")
    return resp.json()['candidates'][0]['content']['parts'][0]['text']

def call_huggingface(messages):
    global current_hf_index
    if not hf_keys:
        raise Exception("No HF keys available")
    prompt = "\n".join([f"{m['role']}: {m['content']}" for m in messages])
    for attempt in range(len(hf_keys) * 2):
        key = hf_keys[current_hf_index % len(hf_keys)]
        current_hf_index += 1
        try:
            resp = requests.post(
                'https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.3',
                headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
                json={'inputs': prompt, 'parameters': {'max_new_tokens': 500}},
                timeout=30
            )
            if resp.status_code == 200:
                return resp.json()[0]['generated_text'].strip()
            elif resp.status_code in (401, 429):
                continue
        except:
            continue
    raise Exception("All HF keys exhausted")

# ---------- SerpAPI search tool ----------
@app.route('/search', methods=['POST'])
def search_web():
    """Direct search endpoint (can be used by agents manually)."""
    data = request.json
    query = data.get('query')
    if not query:
        return jsonify({'error': 'Missing "query" parameter'}), 400
    if not SERPAPI_KEY:
        return jsonify({'error': 'SerpAPI key not configured'}), 500

    params = {
        "q": query,
        "api_key": SERPAPI_KEY,
        "engine": "google",
        "location": "United States",
        "hl": "en",
        "num": 5
    }
    try:
        search = GoogleSearch(params)
        results = search.get_dict()
        organic = results.get("organic_results", [])
        # Return top results (title + link + snippet)
        simplified = [
            {"title": r.get("title", ""), "link": r.get("link", ""), "snippet": r.get("snippet", "")}
            for r in organic[:5]
        ]
        return jsonify({"query": query, "results": simplified})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---------- Helper: perform a search and return formatted text ----------
def perform_search(query):
    """Internal function to get search results as a text block."""
    if not SERPAPI_KEY:
        return "[Error: SerpAPI key not set]"
    params = {
        "q": query,
        "api_key": SERPAPI_KEY,
        "engine": "google",
        "num": 3
    }
    try:
        search = GoogleSearch(params)
        results = search.get_dict()
        organic = results.get("organic_results", [])
        if not organic:
            return f"No results found for '{query}'."
        output = f"Search results for '{query}':\n"
        for i, r in enumerate(organic[:3], 1):
            output += f"{i}. {r.get('title', '')}\n   {r.get('snippet', '')}\n   Link: {r.get('link', '')}\n"
        return output
    except Exception as e:
        return f"Search error: {e}"

# ---------- Main chat endpoint with auto‑search ----------
@app.route('/v1/chat/completions', methods=['POST'])
def chat():
    session_id = request.headers.get('X-Session-Id', 'default')
    data = request.json
    user_msg = None
    for m in data.get('messages', []):
        if m.get('role') == 'user':
            user_msg = m.get('content')
            break
    if not user_msg:
        return jsonify({'error': 'No user message'}), 400

    # Get short‑term context (last 5 messages)
    context = get_recent_context(session_id, n=5)
    messages = [{'role': r, 'content': c} for r, c in context]
    messages.append({'role': 'user', 'content': user_msg})

    # Add a system instruction for tool use
    system_prompt = (
        "You have access to a web search tool. If you need current information, "
        "you can output a special command: [SEARCH: your query]. "
        "The system will execute the search and replace that command with the results. "
        "Then you must provide your final answer. Do not output anything else while searching.\n"
        "If you don't need search, answer normally."
    )
    messages.insert(0, {'role': 'system', 'content': system_prompt})

    # Function to call the LLM (with fallback chain)
    def call_llm(messages):
        try:
            return call_groq(messages)
        except Exception:
            try:
                return call_openrouter(messages)
            except Exception:
                try:
                    return call_gemini(messages)
                except Exception:
                    return call_huggingface(messages)

    # Loop to handle search tool calls
    max_iterations = 3
    iteration = 0
    final_reply = None

    while iteration < max_iterations:
        reply = call_llm(messages)
        # Check if the reply contains a search command
        search_match = re.search(r'\[SEARCH:\s*(.+?)\]', reply, re.IGNORECASE)
        if search_match:
            query = search_match.group(1).strip()
            print(f"🔍 Agent requested search: {query}")
            search_results = perform_search(query)
            # Append the search results as a system message
            messages.append({'role': 'assistant', 'content': reply})
            messages.append({'role': 'user', 'content': f"Search results: {search_results}\nNow provide your final answer."})
            iteration += 1
            continue
        else:
            final_reply = reply
            break

    if not final_reply:
        final_reply = "I could not complete the search. Please try again."

    # Store in memory
    add_message(session_id, 'flask_api', 'user', user_msg)
    add_message(session_id, 'flask_api', 'assistant', final_reply)

    return jsonify({'choices': [{'message': {'role': 'assistant', 'content': final_reply}}]})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
