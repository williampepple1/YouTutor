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

## 🚀 Quick Start

### Prerequisites

- **Python 3.10+**
- **A virtual environment** with the following packages installed:

```bash
pip install fastapi uvicorn youtube-transcript-api yt-dlp
```

### Run it

```bash
python backend.py
```

Open **http://localhost:8080** in your browser.

### Or use the included venv

```bash
~/.venv/Scripts/python.exe backend.py
```

## 🧠 How It Works

1. **Search** — the backend uses `yt-dlp` to search YouTube and returns video results with thumbnails
2. **Transcript** — when you click a video, the backend fetches its transcript via `youtube-transcript-api`
3. **Q&A** — your question is matched against transcript chunks using keyword + phrase scoring, and the most relevant sections are returned with timestamps

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
├── backend.py          # FastAPI server
├── static/
│   └── index.html      # Single-page frontend
├── install_deps.py     # Dependency installer
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
