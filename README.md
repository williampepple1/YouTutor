# 🎓 YouTutor

**An interactive YouTube learning agent** — search, watch, and learn from YouTube videos with AI-powered transcript Q&A.

Inspired by Scrimba's interactive screencasts: watch a video, follow along with the transcript, and ask questions that get answered directly from the video's content.

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🔍 **Search** | Find YouTube videos on any topic |
| ▶️ **Watch** | Embedded YouTube player with autoplay |
| 📝 **Transcript** | Full transcript with clickable timestamps — click any timestamp to jump the video to that point |
| 💬 **Q&A** | Ask questions about the current video and get answers sourced from the transcript |
| 🔑 **BYOK** | Bring Your Own Key — plug in DeepSeek, OpenAI, or any OpenAI-compatible LLM for AI-powered answers |

## 🚀 Quick Start

### Option A: Docker (recommended)

```bash
docker compose up -d
```

Open **http://localhost:8080** in your browser.

### Option B: Local Python

**Prerequisites:** Python 3.10+ and a virtual environment.

```bash
pip install -r requirements.txt
python backend.py
```

Open **http://localhost:8080** in your browser.

> **Windows users** with the included venv:
> ```bash
> ~/.venv/Scripts/python.exe backend.py
> ```

## 🧠 How It Works

1. **Search** — the backend uses `yt-dlp` to search YouTube and returns video results with thumbnails
2. **Transcript** — when you click a video, the backend fetches its transcript via `youtube-transcript-api`
3. **Q&A** — two modes:
   - **🔑 LLM mode** (with API key configured): your question + the relevant transcript sections are sent to your chosen LLM (DeepSeek, OpenAI, etc.) for intelligent, contextual answers
   - **📖 Keyword mode** (no key): your question is matched against transcript chunks using keyword + phrase scoring, and the most relevant sections are returned with timestamps

### Bring Your Own Key (BYOK)

Click the ⚙️ gear icon in the header to configure your LLM:

| Field | Default | Notes |
|-------|---------|-------|
| API Key | — | Your provider key (stored in localStorage, never on the server) |
| API Base URL | `https://api.deepseek.com` | Any OpenAI-compatible endpoint |
| Model | `deepseek-chat` | e.g. `gpt-4o-mini`, `claude-sonnet-4`, `gemini-2.0-flash` |

Hit **🔌 Test** to verify your connection, then ask away — answers will show a **🤖 LLM** badge.

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/search?q=<query>&max_results=12` | Search YouTube |
| `GET` | `/api/transcript/<video_id>` | Fetch transcript |
| `POST` | `/api/ask` | Ask a question about a video |

## 🏗️ Tech Stack

- **Backend**: Python, FastAPI, Uvicorn
- **YouTube**: yt-dlp, youtube-transcript-api
- **Frontend**: Vanilla HTML/CSS/JS (no frameworks)
- **Styling**: Dark theme, responsive layout

## 📂 Project Structure

```
YouTutor/
├── backend.py           # FastAPI server
├── Dockerfile           # Docker image
├── docker-compose.yml   # Docker orchestration
├── requirements.txt     # Python dependencies
├── static/
│   └── index.html       # Single-page frontend
├── .gitignore
└── README.md
```

## 📸 Screenshots

> *(Add a screenshot of the app here!)*

## 🤝 Contributing

PRs welcome! Ideas for improvements:

- **Semantic search** — replace keyword matching with embeddings for smarter Q&A
- **Chat history** — persist conversations across sessions
- **Video chapters** — display and navigate by chapter
- **Speed controls** — adjustable playback speed
- **Bookmarks** — save timestamps and notes

## 📄 License

MIT
