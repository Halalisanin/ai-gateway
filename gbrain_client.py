import subprocess, json, os, time, shutil

BRAIN_DIR = os.path.expanduser("~/.gbrain")

_GBRAIN_PATH = (
    shutil.which("gbrain")
    or os.path.expanduser("~/.bun/bin/gbrain")
    or os.path.expanduser("~/.local/bin/gbrain")
    or "/usr/local/bin/gbrain"
)

gbrain_ready = False

def _run(args, input_data=None, timeout=30):
    try:
        env = os.environ.copy()
        nv_key = env.get("NVIDIA_API_KEY", "")
        if nv_key:
            env["OPENAI_API_KEY"] = nv_key
        proc = subprocess.run(
            [_GBRAIN_PATH] + args,
            capture_output=True, text=True, timeout=timeout,
            input=input_data, env=env
        )
        err = proc.stderr.strip()
        if "NOT FOUND" in err and "embed" in err.lower():
            pass
        elif proc.returncode != 0:
            return {"error": err or proc.stdout.strip()}
        out = proc.stdout.strip()
        if err and "NOT FOUND" not in err:
            out = out + "\n[gbrain warn] " + err[:200] if out else "[gbrain warn] " + err[:200]
        return {"result": out}
    except FileNotFoundError:
        return {"error": "gbrain not found. Install with: bun install -g gbrain"}
    except subprocess.TimeoutExpired:
        return {"error": "gbrain command timed out"}

def ensure_initialized():
    global gbrain_ready
    if gbrain_ready:
        return True
    doctor = _run(["doctor", "--json", "--fast"])
    if isinstance(doctor, dict) and doctor.get("error"):
        if "not initialized" in doctor["error"].lower() or "no brain" in doctor["error"].lower():
            init = _run(["init", "--pglite"])
            if isinstance(init, dict) and init.get("error"):
                return False
            time.sleep(1)
        else:
            return False
    gbrain_ready = True
    return True

def search(query, limit=10):
    ok = ensure_initialized()
    if not ok:
        _run(["init", "--pglite"])
        time.sleep(1)
    result = _run(["search", query])
    if isinstance(result, dict) and "error" in result:
        return f"[MEMORY] Error: {result['error']}"
    text = result.get("result", "")
    if not text or text == "[]":
        return "[MEMORY] No results found."
    try:
        items = json.loads(text)
        lines = []
        for i, item in enumerate(items[:limit], 1):
            slug = item.get("slug", "?")
            snippet = item.get("chunk_text", "")[:200]
            score = item.get("score", 0)
            lines.append(f"{i}. [{score:.3f}] {slug}\n   {snippet}")
        return "=== MEMORY SEARCH RESULTS ===\n" + "\n\n".join(lines)
    except json.JSONDecodeError:
        return f"[MEMORY] {text[:1000]}"

def query(question):
    ok = ensure_initialized()
    if not ok:
        return "[MEMORY] Brain not initialized. Run: gbrain init --pglite"
    result = _run(["query", question])
    if isinstance(result, dict) and "error" in result:
        return f"[MEMORY] Error: {result['error']}"
    text = result.get("result", "")
    return f"=== MEMORY QUERY ===\n{text[:2000]}"

def save_page(slug, content):
    ok = ensure_initialized()
    if not ok:
        return "[MEMORY] Brain not initialized."
    result = _run(["put", slug], input_data=content)
    if isinstance(result, dict) and "error" in result:
        return f"[MEMORY] Error saving: {result['error']}"
    return f"[MEMORY] Saved page '{slug}' successfully."

def stats():
    ok = ensure_initialized()
    if not ok:
        return "[MEMORY] Not initialized."
    result = _run(["list", "-n", "1000"])
    count = 0
    if isinstance(result, dict) and "result" in result:
        try:
            items = json.loads(result["result"])
            count = len(items) if isinstance(items, list) else 0
        except:
            pass
    return f"[MEMORY] Brain active. {count} pages indexed."
