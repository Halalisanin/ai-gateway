cat > README.md << 'EOF'
# 🚀 AI Gateway – Unified API for Multi‑Agent Systems

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-ready-blue)](https://www.docker.com/)

**One API to rule all your AI agents** – automatically falls back across Groq, OpenRouter, Gemini, and 10 Hugging Face keys, provides shared conversation memory, and gives agents real‑time tools (weather, stocks, news, web search).

## ✨ Features

- 🔄 **Auto‑failover** – Tries Groq → OpenRouter → Gemini → HF (rotates 10 keys). Zero downtime.
- 🧠 **Shared memory** – SQLite stores last N messages per session. Use `X-Session-Id` header.
- 🛠️ **Built‑in tools** – Weather, stocks, news, web search via `[TOOL: argument]` syntax.
- 🌐 **Real‑time search** – SerpAPI integration.
- 🐳 **Docker ready** – `docker-compose up` runs everything.
- 📦 **Lightweight** – No vector DB required (optional RAG can be added later).

## 🚀 Quick Start

### Using Docker (easiest)

```bash
git clone https://github.com/yourusername/ai-gateway.git
cd ai-gateway
cp .env.example .env   # add your API keys
docker-compose up -d
curl http://localhost:8080/v1/chat/completions -H "Content-Type: application/json" -d '{"messages":[{"role":"user","content":"What is the weather in Paris?"}]}'
