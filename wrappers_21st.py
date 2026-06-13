import subprocess, json, os

MAGIC_BIN = os.path.expanduser("~/.bun/bin/magic")
CLI_BIN = os.path.expanduser("~/.bun/bin/21st-dev-cli")

def _mcp_call(method, params=None, timeout=60):
    if not os.path.exists(MAGIC_BIN):
        return "[21st] magic binary not found. Run: bun install -g @21st-dev/magic"
    msg_id = 1
    req_init = json.dumps({
        "jsonrpc": "2.0", "id": msg_id,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "ai-gateway", "version": "1.0.0"}
        }
    }) + "\n"
    msg_id += 1
    req_notif = json.dumps({
        "jsonrpc": "2.0", "method": "notifications/initialized"
    }) + "\n"
    if method in ("initialize", "notifications/initialized"):
        payload = req_init + req_notif
        req_id = None
    elif method == "tools/list":
        payload = req_init + req_notif + json.dumps({
            "jsonrpc": "2.0", "id": msg_id, "method": "tools/list"
        }) + "\n"
        req_id = msg_id
    else:
        payload = req_init + req_notif + json.dumps({
            "jsonrpc": "2.0", "id": msg_id, "method": "tools/call",
            "params": {"name": method, "arguments": params or {}}
        }) + "\n"
        req_id = msg_id
    try:
        proc = subprocess.Popen(
            [MAGIC_BIN], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True,
            env={**os.environ, "MAGIC_21ST_DEV_API_KEY": os.environ.get("MAGIC_21ST_DEV_API_KEY", "")}
        )
        out, err = proc.communicate(input=payload, timeout=timeout)
        results = []
        for line in out.strip().split("\n"):
            if not line.strip():
                continue
            try:
                parsed = json.loads(line)
                if "result" in parsed:
                    results.append(parsed["result"])
                elif "error" in parsed:
                    results.append({"error": parsed["error"]})
            except json.JSONDecodeError:
                if "logMessage" in line:
                    try:
                        log = json.loads(line)
                        msg = log.get("params", {}).get("message", line)
                        results.append({"log": msg})
                    except json.JSONDecodeError:
                        pass
        if err:
            results.append({"stderr": err[:1000]})
        return _format_results(results)
    except FileNotFoundError:
        return "[21st] magic binary not found"
    except subprocess.TimeoutExpired:
        proc.kill()
        return "[21st] magic mcp call timed out"
    except Exception as e:
        return f"[21st] magic error: {e}"

def _format_results(results):
    lines = []
    for r in results:
        if "log" in r:
            continue
        if "error" in r:
            lines.append(f"Error: {r['error']}")
            continue
        content_list = r.get("content", [])
        for c in content_list:
            if c.get("type") == "text":
                lines.append(c.get("text", ""))
    return "\n".join(lines) if lines else "[21st] No output"

def create_component(message, search_query, file_path, project_path):
    return _mcp_call("21st_magic_component_builder", {
        "message": message,
        "searchQuery": search_query,
        "absolutePathToCurrentFile": file_path,
        "absolutePathToProjectDirectory": project_path,
        "standaloneRequestQuery": message
    }, timeout=120)

def search_components(query):
    return _mcp_call("21st_magic_component_inspiration", {
        "message": query,
        "searchQuery": query
    })

def search_logos(companies, fmt="SVG"):
    queries = companies if isinstance(companies, list) else [companies]
    return _mcp_call("logo_search", {
        "queries": queries,
        "format": fmt
    })

def refine_component(user_message, file_path, context=""):
    return _mcp_call("21st_magic_component_refiner", {
        "userMessage": user_message,
        "absolutePathToRefiningFile": file_path,
        "context": context
    }, timeout=120)

def install_mcp(client="cursor"):
    if not os.path.exists(CLI_BIN):
        return "[21st] 21st-dev-cli not found. Run: bun install -g @21st-dev/cli"
    try:
        proc = subprocess.run(
            [CLI_BIN, "install", client],
            capture_output=True, text=True, timeout=30
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        return out.strip()[:2000]
    except Exception as e:
        return f"[21st] cli error: {e}"

def list_available():
    return (
        "[21st] Available 21st.dev tools:\n"
        "  create_ui: <prompt> | <search> | <file> | <project>  - Build a UI component\n"
        "  search_ui: <query>    - Search 21st.dev for component ideas\n"
        "  logos: <company1>,<company2> | JSX|TSX|SVG  - Get company logos\n"
        "  refine: <msg> | <file> | <context>    - Improve an existing component\n"
        "  install_mcp: <cursor|windsurf|claude|github-copilot>  - Add 21st MCP to IDE"
    )

def handle_command(arg):
    parts = [p.strip() for p in arg.split("|")]
    cmd = parts[0].lower()

    if cmd in ("list", "help", ""):
        return list_available()

    if cmd == "create_ui":
        msg = parts[1] if len(parts) > 1 else "Create a UI component"
        search = parts[2] if len(parts) > 2 else msg
        file_path = parts[3] if len(parts) > 3 else os.getcwd()
        proj_path = parts[4] if len(parts) > 4 else os.getcwd()
        return create_component(msg, search, file_path, proj_path)

    if cmd == "search_ui":
        q = parts[1] if len(parts) > 1 else arg
        return search_components(q)

    if cmd == "logos":
        companies = [c.strip() for c in parts[1].split(",")] if len(parts) > 1 else ["github"]
        fmt = parts[2] if len(parts) > 2 else "SVG"
        return search_logos(companies, fmt)

    if cmd == "refine":
        msg = parts[1] if len(parts) > 1 else "Improve this UI"
        fpath = parts[2] if len(parts) > 2 else ""
        ctx = parts[3] if len(parts) > 3 else ""
        return refine_component(msg, fpath, ctx)

    if cmd == "install_mcp":
        client = parts[1] if len(parts) > 1 else "cursor"
        return install_mcp(client)

    return f"[21st] Unknown subcommand: {cmd}. Use: list, create_ui, search_ui, logos, refine, install_mcp"
