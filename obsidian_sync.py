import os, re, time, json, threading, subprocess
from pathlib import Path

OBSIDIAN_VAULT = os.path.expanduser("~/Documents/job/jobs_obsidian/Obsidian Vault")

g_kb = None
g_gbrain_client = None
_index_log = []
_GBRAIN_BIN = (
    os.environ.get("GBRAIN_PATH")
    or os.path.expanduser("~/.bun/bin/gbrain")
)
OBSIDIAN_SYNC_DELAY = 0.5

def _init():
    global g_kb, g_gbrain_client
    if g_kb is None:
        import sys
        sys.path.append(os.path.expanduser("~/Documents/job/ai-gateway"))
        from knowledge_base import kb
        g_kb = kb
    if g_gbrain_client is None:
        import sys
        if os.path.expanduser("~/Documents/job/ai-gateway") not in sys.path:
            sys.path.append(os.path.expanduser("~/Documents/job/ai-gateway"))
        import gbrain_client
        g_gbrain_client = gbrain_client

def _gbrain_put(slug, text):
    try:
        subprocess.run(
            [_GBRAIN_BIN, "put", slug],
            input=text.encode("utf-8"),
            capture_output=True, timeout=15
        )
    except Exception as e:
        print(f"[ObsidianSync] gbrain put error: {e}", flush=True)

def _sync_note(filepath):
    _init()
    path = Path(filepath)
    if not path.exists() or path.suffix != ".md":
        return
    slug = path.stem.lower().replace(" ", "-").replace("_", "-")
    slug = re.sub(r'[^a-z0-9-]', '', slug)
    text = path.read_text(encoding="utf-8", errors="ignore").strip()
    if not text:
        return
    ts = time.strftime("%Y-%m-%d %H:%M:%S")

    g_kb.index_text(text, str(path))
    _gbrain_put(slug, text)

    entry = f"[{ts}] Synced: {path.name}"
    _index_log.append(entry)
    _index_log[:] = _index_log[-100:]
    print(f"[ObsidianSync] {entry}", flush=True)

def sync_all():
    _init()
    vault = Path(OBSIDIAN_VAULT)
    if not vault.exists():
        return f"[ObsidianSync] Vault not found: {OBSIDIAN_VAULT}"
    count = 0
    for f in sorted(vault.glob("*.md")):
        _sync_note(str(f))
        count += 1
    import time as _t
    ts = _t.strftime("%Y-%m-%d %H:%M:%S")
    msg = f"[ObsidianSync] {ts} — Synced {count} notes to KB + Memory"
    _index_log.append(msg)
    return msg

def start_watcher():
    _init()
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
    except ImportError:
        _index_log.append("[ObsidianSync] watchdog not installed. Run: pip install watchdog")
        return

    class ObsidianHandler(FileSystemEventHandler):
        def on_modified(self, event):
            if event.is_directory:
                return
            if event.src_path.endswith(".md"):
                time.sleep(0.3)
                _sync_note(event.src_path)

        def on_created(self, event):
            if event.is_directory:
                return
            if event.src_path.endswith(".md"):
                time.sleep(0.3)
                _sync_note(event.src_path)

    observer = Observer()
    observer.schedule(ObsidianHandler(), OBSIDIAN_VAULT, recursive=False)
    observer.daemon = True
    observer.start()
    _index_log.append(f"[ObsidianSync] Watcher started on {OBSIDIAN_VAULT}")
    return observer

def get_log(n=10):
    return "\n".join(_index_log[-n:])

def stats():
    _init()
    kb_count = g_kb.stats() if g_kb else "N/A"
    return f"[ObsidianSync] Vault: {OBSIDIAN_VAULT}\nKB: {kb_count}\nRecent: {len(_index_log)} sync events"

def handle_command(arg):
    parts = [p.strip() for p in arg.split("|")]
    cmd = parts[0].lower()
    if cmd in ("sync", "sync_all"):
        return sync_all()
    if cmd in ("log", "recent"):
        n = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 10
        return get_log(n)
    if cmd in ("stats", "status"):
        return stats()
    if cmd in ("start", "watch", "watcher"):
        start_watcher()
        return get_log(3)
    if cmd == "help":
        return (
            "[ObsidianSync] Commands:\n"
            "  sync          — Index all vault notes into KB + Memory\n"
            "  log [n]       — Show recent sync history\n"
            "  stats         — Show sync statistics\n"
            "  start         — Start background file watcher\n"
            "  help          — This message"
        )
    return f"[ObsidianSync] Unknown: {cmd}"
