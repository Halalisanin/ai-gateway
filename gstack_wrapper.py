import subprocess, json, os

GSTACK_DIR = os.path.expanduser("~/Documents/job/Additional_intergrations/gstack")
BIN_DIR = os.path.join(GSTACK_DIR, "bin")

def _run_tool(tool_name, args=None):
    tool_path = os.path.join(BIN_DIR, tool_name)
    if not os.path.exists(tool_path):
        return f"[GSTACK] Tool '{tool_name}' not found."
    cmd = ["bash", tool_path]
    if args:
        cmd.extend(args if isinstance(args, list) else [args])
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60,
                              cwd=GSTACK_DIR)
        output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
        return output.strip()[:2000] or f"[GSTACK] {tool_name} completed (no output)."
    except FileNotFoundError:
        return f"[GSTACK] gstack not found at {GSTACK_DIR}"
    except subprocess.TimeoutExpired:
        return f"[GSTACK] {tool_name} timed out"

def run_review(path):
    if not os.path.exists(path):
        return f"[GSTACK] Path not found: {path}"
    return _run_tool("gstack-review-log", [path])

def run_spec(description):
    return _run_tool("gstack-question-log", [description])

def run_qa(scope=None):
    args = [scope] if scope else []
    return _run_tool("gstack-specialist-stats", args)

def run_health():
    return _run_tool("gstack-platform-detect")

def run_codex_probe(path=None):
    args = [path] if path else []
    return _run_tool("gstack-codex-probe", args)

def available_tools():
    if not os.path.isdir(BIN_DIR):
        return "[GSTACK] No tools found."
    tools = [f for f in os.listdir(BIN_DIR) if f.startswith("gstack-")]
    return f"[GSTACK] Available tools ({len(tools)}):\n" + "\n".join(sorted(tools)[:20])
