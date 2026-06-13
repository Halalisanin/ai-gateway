def scan_folder(path):
    """Return file contents (up to 10 files, 30KB total, depth 2)."""
    import os
    if not os.path.exists(path):
        return f"Error: Path '{path}' does not exist."
    if not os.path.isdir(path):
        return f"Error: '{path}' is not a directory."
    summary = []
    max_bytes = 30000
    current = 0
    file_count = 0
    for root, dirs, files in os.walk(path):
        depth = root[len(path):].count(os.sep)
        if depth > 2:
            continue
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('node_modules', '__pycache__', 'venv', 'env')]
        for file in files:
            if file_count >= 10:
                summary.append("\n... (more files, limit reached)")
                break
            if file.endswith(('.py', '.js', '.ts', '.json', '.md', '.txt', '.html', '.css', '.yaml', '.yml')):
                full = os.path.join(root, file)
                rel = os.path.relpath(full, path)
                try:
                    with open(full, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read(2000)  # first 2000 chars
                    entry = f"\n--- {rel} ---\n{content}\n"
                    if current + len(entry) > max_bytes:
                        summary.append("\n... (truncated, too large)")
                        break
                    summary.append(entry)
                    current += len(entry)
                    file_count += 1
                except:
                    summary.append(f"\n--- {rel} --- [unreadable]\n")
        if current >= max_bytes or file_count >= 10:
            break
    result = "".join(summary) if summary else "No readable files found."
    return f"Folder analysis for {path}:\n{result}"
