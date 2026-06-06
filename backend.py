"""
YouTutor Backend
FastAPI app that handles YouTube search, transcript fetching, and Q&A.
"""

import json
import re
import subprocess
import sys
import os
from pathlib import Path
from typing import Optional
from collections import Counter

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import urllib.request as http_req
import urllib.error as http_err
import ssl
import tempfile
import base64
import uuid
import certifi

# Force certifi's CA bundle for all HTTPS connections (fixes HF Spaces SSL issue)
os.environ.setdefault("SSL_CERT_FILE", certifi.where())
os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())

import uvicorn

# ── App setup ──────────────────────────────────────────────────────────────

app = FastAPI(title="YouTutor")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Resolve paths
HERE = Path(__file__).parent
STATIC = HERE / "static"
HOME = Path.home()
VENV_PYTHON_candidate = HOME / ".venv" / "Scripts" / "python.exe"
VENV_PYTHON = VENV_PYTHON_candidate if VENV_PYTHON_candidate.exists() else Path(sys.executable)


# ── Helpers ────────────────────────────────────────────────────────────────

def run_ytdlp(*args: str, timeout: int = 60) -> list[dict]:
    """Run yt-dlp and return list of parsed JSON results (one per result)."""
    cmd = [str(VENV_PYTHON), "-m", "yt_dlp", *args]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            raise RuntimeError(f"yt-dlp error: {result.stderr[:500]}")
        lines = result.stdout.strip().split("\n")
        if not lines or not lines[0].strip():
            return []
        return [json.loads(line) for line in lines if line.strip()]
    except subprocess.TimeoutExpired:
        raise RuntimeError("yt-dlp timed out")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse yt-dlp output: {e}")


# ── Cache ──────────────────────────────────────────────────────────────────
_transcript_cache: dict[str, dict] = {}


def get_transcript(video_id: str) -> list[dict]:
    """Fetch transcript segments for a video using yt-dlp (works on HF Spaces)."""
    if video_id in _transcript_cache:
        cached = _transcript_cache[video_id]
        if isinstance(cached, list):
            return cached
        raise RuntimeError(str(cached))

    last_error = None

    # Use yt-dlp to download subtitles (handles SSL with its own HTTP client)
    for attempt in range(2):
        try:
            for f in AUDIO_DIR.glob(f"{video_id}*"):
                f.unlink(missing_ok=True)

            cmd = [
                str(VENV_PYTHON), "-m", "yt_dlp",
                "--write-subs", "--write-auto-sub",
                "--sub-lang", "en",
                "--sub-format", "vtt",
                "--skip-download",
                "-o", str(AUDIO_DIR / "%(id)s"),
                "--no-warnings",
                "--ignore-errors",
                f"https://www.youtube.com/watch?v={video_id}",
            ]
            if attempt == 1:
                # Second attempt: try with --allow-unplayable-formats
                cmd.insert(cmd.index("--skip-download"), "--allow-unplayable-formats")

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)

            sub_files = sorted(AUDIO_DIR.glob(f"{video_id}*"))
            if not sub_files:
                # Try with different sub-lang format
                cmd[cmd.index("--sub-lang") + 1] = "en-US,en-GB,en"
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
                sub_files = sorted(AUDIO_DIR.glob(f"{video_id}*"))

            for f in sub_files:
                text = f.read_text(encoding="utf-8", errors="replace")
                if f.suffix == ".vtt":
                    segments = parse_vtt(text)
                elif f.suffix == ".srt":
                    segments = parse_srt(text)
                elif f.suffix in (".json", ".json3"):
                    segments = parse_json3(text)
                else:
                    continue
                if segments:
                    for f2 in sub_files:
                        f2.unlink(missing_ok=True)
                    _transcript_cache[video_id] = segments
                    return segments

            last_error = "No subtitle files found"
            # Clean up on failure
            for f in sub_files:
                f.unlink(missing_ok=True)

        except subprocess.TimeoutExpired:
            last_error = "yt-dlp timed out (180s)"
        except Exception as e:
            last_error = f"{e}"[:200]

    err_msg = f"Transcript unavailable: {last_error}"
    _transcript_cache[video_id] = err_msg
    raise RuntimeError(err_msg)


def parse_srt(srt_text: str) -> list[dict]:
    """Parse SRT subtitle text into segment list."""
    segments = []
    # SRT format:
    # 1
    # 00:00:01,000 --> 00:00:04,000
    # text line 1
    # text line 2
    #
    block_pattern = re.compile(
        r"\d+\n"
        r"(\d{2}:\d{2}:\d{2}[,\.]\d{3}) --> (\d{2}:\d{2}:\d{2}[,\.]\d{3})\n"
        r"((?:(?!\n\n).)+)",
        re.DOTALL | re.MULTILINE,
    )

    def _ts_to_sec(ts: str) -> float:
        """Convert SRT timestamp (HH:MM:SS,mmm) to seconds."""
        ts = ts.replace(",", ".")
        h, m, s = ts.split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)

    for match in block_pattern.finditer(srt_text):
        start_ts = match.group(1)
        end_ts = match.group(2)
        text = match.group(3).strip()
        # Remove HTML tags like <font> etc.
        text = re.sub(r"<[^>]+>", "", text)
        # Remove multiple newlines
        text = re.sub(r"\n+", " ", text)

        start = _ts_to_sec(start_ts)
        end = _ts_to_sec(end_ts)
        segments.append({
            "text": text,
            "start": start,
            "duration": end - start,
        })

    return segments


def parse_vtt(vtt_text: str) -> list[dict]:
    """Parse WebVTT subtitle text into segment list."""
    segments = []
    block_pattern = re.compile(
        r"(?:.*\n)?"
        r"(\d{2}:\d{2}:\d{2}[,\.]\d{3}) --> (\d{2}:\d{2}:\d{2}[,\.]\d{3})\n"
        r"((?:(?!\n\n).)+)",
        re.DOTALL | re.MULTILINE,
    )

    def _ts_to_sec(ts: str) -> float:
        ts = ts.replace(",", ".")
        h, m, s = ts.split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)

    for match in block_pattern.finditer(vtt_text):
        start_ts = match.group(1)
        end_ts = match.group(2)
        text = match.group(3).strip()
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"\n+", " ", text)
        text = re.sub(r"&amp;", "&", text)
        text = re.sub(r"&lt;", "<", text)
        text = re.sub(r"&gt;", ">", text)
        start = _ts_to_sec(start_ts)
        end = _ts_to_sec(end_ts)
        segments.append({"text": text, "start": start, "duration": end - start})
    return segments


def parse_json3(json_text: str) -> list[dict]:
    """Parse YouTube JSON3 subtitle format into segment list."""
    import json
    data = json.loads(json_text)
    segments = []
    for event in data.get("events", []):
        segs = event.get("segs", [])
        if not segs:
            continue
        text = "".join(s.get("utf8", "") for s in segs).strip()
        if not text:
            continue
        start = event.get("tStartMs", 0) / 1000.0
        dur = event.get("dDurationMs", 0) / 1000.0
        if dur <= 0:
            dur = 2.0
        text = re.sub(r"\s+", " ", text)
        segments.append({"text": text, "start": start, "duration": dur})
    return segments


# ── Debug endpoint ────────────────────────────────────────────────
@app.get("/api/debug")
async def debug_info():
    audio_ok = AUDIO_DIR.exists()
    write_ok = True
    try:
        test_file = AUDIO_DIR / ".write_test"
        test_file.write_text("ok")
        test_file.unlink()
    except Exception:
        write_ok = False
    try:
        ver = subprocess.run(
            [str(VENV_PYTHON), "-m", "yt_dlp", "--version"],
            capture_output=True, text=True, timeout=10,
        )
        ytdlp_ver = ver.stdout.strip() or ver.stderr.strip()
    except Exception as e:
        ytdlp_ver = str(e)
    return {
        "python": sys.version,
        "yt_dlp": ytdlp_ver,
        "audio_dir": str(AUDIO_DIR),
        "audio_dir_exists": audio_ok,
        "audio_dir_writable": write_ok,
    }


def chunk_transcript(segments: list[dict], chunk_size: int = 800) -> list[dict]:
    """Split transcript into overlapping chunks for search."""
    chunks = []
    current_chunk = []
    current_len = 0

    for seg in segments:
        text = seg.get("text", "").strip()
        if not text:
            continue
        word_count = len(text.split())
        if current_len + word_count > chunk_size and current_chunk:
            chunks.append({
                "text": " ".join(s["text"] for s in current_chunk),
                "start": current_chunk[0]["start"],
                "duration": current_chunk[-1]["start"] + current_chunk[-1]["duration"] - current_chunk[0]["start"],
                "segments": current_chunk,
            })
            # overlap: keep last 30% of current chunk
            overlap_idx = max(0, len(current_chunk) - int(len(current_chunk) * 0.3))
            current_chunk = current_chunk[overlap_idx:]
            current_len = sum(len(s["text"].split()) for s in current_chunk)

        current_chunk.append(seg)
        current_len += word_count

    if current_chunk:
        chunks.append({
            "text": " ".join(s["text"] for s in current_chunk),
            "start": current_chunk[0]["start"],
            "duration": current_chunk[-1]["start"] + current_chunk[-1]["duration"] - current_chunk[0]["start"],
            "segments": current_chunk,
        })

    return chunks


def find_relevant_chunks(question: str, chunks: list[dict], top_k: int = 3) -> list[dict]:
    """Find the most relevant transcript chunks for a question using keyword matching."""
    # Extract words from the question, keeping meaningful terms
    q_lower = question.lower()
    words = re.findall(r'\b[a-zA-Z]{2,}\b', q_lower)
    stopwords = {"the", "and", "for", "are", "but", "not", "you", "all", "can",
                 "had", "her", "was", "one", "our", "out", "has", "have", "been",
                 "this", "that", "with", "from", "what", "when", "where", "how",
                 "why", "which", "does", "about", "tell", "explain", "give", "its",
                 "also", "they", "them", "their", "than", "then", "just", "like",
                 "use", "used", "using", "get", "got", "make", "made", "know",
                 "really", "very", "much", "some", "any", "way", "thing", "things"}
    keywords = [w for w in words if w not in stopwords]

    if not keywords:
        return chunks[:top_k]

    # Check for phrases: 2-3 word sequences from the question
    question_phrases = []
    kw_set = set(keywords)
    for i in range(len(keywords) - 1):
        question_phrases.append(keywords[i] + " " + keywords[i + 1])
    for i in range(len(keywords) - 2):
        question_phrases.append(keywords[i] + " " + keywords[i + 1] + " " + keywords[i + 2])

    scored = []
    for i, chunk in enumerate(chunks):
        chunk_lower = chunk["text"].lower()
        chunk_words = set(re.findall(r'\b[a-zA-Z]{2,}\b', chunk_lower))

        # Score: keyword overlap + phrase bonuses + position bonus
        overlap = sum(1 for kw in keywords if kw in chunk_words)
        phrase_bonus = sum(5 for phrase in question_phrases if phrase in chunk_lower)
        # Boost chunks that occur earlier (more likely to cover intro topics)
        position_bonus = max(0, 1.0 - (i / len(chunks)) * 0.3)
        total_score = overlap + phrase_bonus + position_bonus

        if total_score > 0:
            scored.append((total_score, i, chunk))

    scored.sort(key=lambda x: -x[0])
    return [item[2] for item in scored[:top_k]]


def format_timestamp(seconds: float) -> str:
    """Convert seconds to MM:SS or HH:MM:SS."""
    h, r = divmod(int(seconds), 3600)
    m, s = divmod(r, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def ask_llm(question: str, transcript_context: str, config: dict) -> str:
    """Call an OpenAI-compatible LLM API to answer a question from transcript context.

    config expects: {api_key, base_url (optional), model (optional)}
    Defaults to DeepSeek if base_url/model omitted.
    """
    if not config or not config.get("api_key"):
        return None

    base_url = (config.get("base_url") or "https://api.deepseek.com").rstrip("/")
    model = config.get("model") or "deepseek-chat"
    api_key = config["api_key"]

    # Ensure the URL ends with /chat/completions
    if not base_url.endswith("/chat/completions"):
        if not base_url.endswith("/v1"):
            base_url += "/v1"
        base_url += "/chat/completions"

    payload = json.dumps({
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a helpful tutor explaining video content. "
                    "You will be given a transcript excerpt from a video and a "
                    "learner's question about it.\n\n"
                    "1. Use the transcript as your PRIMARY source — answer based "
                    "on what the video says.\n"
                    "2. BUT also feel free to add your own explanation, examples, "
                    "or context to make the answer clearer and more complete. "
                    "You're not limited to only what's in the transcript.\n"
                    "3. When you add something beyond the transcript, mention it "
                    "naturally (e.g. 'The video covers X, and to add some "
                    "context...' or 'Building on that, you should also know...').\n"
                    "4. If the transcript doesn't cover the question at all, say "
                    "so honestly, then share what you know from your own "
                    "knowledge.\n"
                    "5. Reference timestamps where helpful.\n"
                    "6. Be conversational and instructive — like a tutor sitting "
                    "next to the learner."
                ),
            },
            {
                "role": "user",
                "content": f"Transcript excerpt from the video:\n\n{transcript_context}\n\n"
                           f"Question: {question}",
            },
        ],
        "temperature": 0.3,
        "max_tokens": 1024,
    }).encode("utf-8")

    req = http_req.Request(
        base_url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        ctx = ssl.create_default_context()
        resp = http_req.urlopen(req, context=ctx, timeout=30)
        body = json.loads(resp.read().decode("utf-8"))
        choices = body.get("choices", [])
        if choices:
            return choices[0].get("message", {}).get("content", "")
        return None
    except Exception as e:
        # Return the error so the frontend can show it
        raise RuntimeError(f"LLM API error: {e}")


# ── Audio download & transcription ─────────────────────────────────

AUDIO_DIR = HERE / "audio_cache"
AUDIO_DIR.mkdir(exist_ok=True)


def download_audio(video_id: str) -> Path:
    """Download audio from a YouTube video and return the file path."""
    output = AUDIO_DIR / f"{video_id}_{uuid.uuid4().hex[:8]}.mp3"
    cmd = [
        str(VENV_PYTHON), "-m", "yt_dlp",
        "-x", "--audio-format", "mp3",
        "--audio-quality", "0",  # best quality
        "-o", str(output),
        "--no-warnings",
        f"https://www.youtube.com/watch?v={video_id}",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0 or not output.exists():
        raise RuntimeError(f"Audio download failed: {result.stderr[:300]}")
    return output


def transcribe_audio(audio_path: Path, api_key: str) -> list[dict]:
    """Transcribe audio using OpenAI Whisper API."""
    import mimetypes
    mime = mimetypes.guess_type(str(audio_path))[0] or "audio/mpeg"

    boundary = uuid.uuid4().hex
    filename = audio_path.name

    # Build multipart form-data manually
    with open(audio_path, "rb") as f:
        audio_data = f.read()

    body_parts = []
    body_parts.append(f"--{boundary}\r\n"
                      f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
                      f"Content-Type: {mime}\r\n\r\n".encode())
    body_parts.append(audio_data)
    body_parts.append(f"\r\n--{boundary}\r\n"
                      f'Content-Disposition: form-data; name="model"\r\n\r\n'
                      f"whisper-1\r\n".encode())
    body_parts.append(f"--{boundary}\r\n"
                      f'Content-Disposition: form-data; name="response_format"\r\n\r\n'
                      f"verbose_json\r\n".encode())
    body_parts.append(f"\r\n--{boundary}--\r\n".encode())

    body = b"".join(body_parts)

    req = http_req.Request(
        "https://api.openai.com/v1/audio/transcriptions",
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        ctx = ssl.create_default_context()
        resp = http_req.urlopen(req, context=ctx, timeout=120)
        result = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        # Try to read the error body
        error_body = ""
        if hasattr(e, "read"):
            try:
                error_body = e.read().decode("utf-8")
            except Exception:
                pass
        raise RuntimeError(f"Whisper API error: {e} {error_body}")

    segments = result.get("segments", [])
    return [
        {
            "text": s.get("text", "").strip(),
            "start": s.get("start", 0),
            "duration": s.get("end", s.get("start", 0)) - s.get("start", 0),
        }
        for s in segments
    ]


# ── API Routes ─────────────────────────────────────────────────────────────

@app.get("/api/search")
async def search_videos(q: str = Query(..., description="Search query"), max_results: int = 12):
    """Search YouTube for videos."""
    try:
        results = run_ytdlp(
            "ytsearch" + str(max_results) + ":" + q,
            "--dump-json",
            "--no-warnings",
            "--flat-playlist",
            "-s",
            timeout=60,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    videos = []
    for r in results:
        vid = r.get("id", "")
        videos.append({
            "id": vid,
            "title": r.get("title", ""),
            "channel": r.get("channel", ""),
            "duration": r.get("duration", 0),
            "views": r.get("view_count", 0),
            "thumbnail": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
            "description": (r.get("description") or "")[:300],
        })

    return {"videos": videos}


@app.get("/api/transcript/{video_id}")
async def fetch_transcript(video_id: str):
    """Get transcript for a YouTube video."""
    try:
        segments = get_transcript(video_id)
    except RuntimeError as e:
        raise HTTPException(status_code=404, detail=str(e))

    full_text = " ".join(s["text"] for s in segments)

    return {
        "video_id": video_id,
        "segments": [
            {
                "text": s["text"],
                "start": s["start"],
                "duration": s.get("duration", 0),
                "timestamp": format_timestamp(s["start"]),
            }
            for s in segments
        ],
        "full_text": full_text,
        "total_segments": len(segments),
    }


class LlmConfig(BaseModel):
    api_key: str = ""
    base_url: str = ""
    model: str = ""


class AskRequest(BaseModel):
    video_id: str
    question: str
    llm: Optional[LlmConfig] = None


@app.post("/api/ask")
async def ask_question(req: AskRequest):
    """Ask a question about a video and get answer from transcript.

    If llm config is provided, uses the LLM to generate a natural answer.
    Otherwise falls back to keyword matching.
    """
    try:
        segments = get_transcript(req.video_id)
    except RuntimeError as e:
        raise HTTPException(status_code=404, detail=str(e))

    chunks = chunk_transcript(segments)
    relevant = find_relevant_chunks(req.question, chunks)

    if not relevant:
        return {
            "answer": "I couldn't find specific information about that in the video transcript.",
            "sources": [],
            "mode": "keyword",
        }

    # Build context from relevant chunks
    context_parts = []
    sources = []
    for chunk in relevant:
        ts = format_timestamp(chunk["start"])
        context_parts.append(f"[{ts}] {chunk['text']}")
        sources.append({
            "text": chunk["text"][:200] + ("..." if len(chunk["text"]) > 200 else ""),
            "timestamp": ts,
            "start": chunk["start"],
        })

    context = "\n\n".join(context_parts)

    # Try LLM if configured
    if req.llm and req.llm.api_key:
        try:
            llm_answer = ask_llm(
                req.question,
                context,
                {
                    "api_key": req.llm.api_key,
                    "base_url": req.llm.base_url,
                    "model": req.llm.model,
                },
            )
            if llm_answer:
                return {
                    "answer": llm_answer,
                    "sources": sources,
                    "mode": "llm",
                }
        except RuntimeError as e:
            return {
                "answer": f"⚠️ LLM error: {e}",
                "sources": sources,
                "mode": "llm_error",
            }

    # Fallback: return raw context
    return {
        "answer": context,
        "sources": sources,
        "found_chunks": len(relevant),
        "mode": "keyword",
    }


class GenerateTranscriptRequest(BaseModel):
    api_key: str = ""


@app.post("/api/generate-transcript/{video_id}")
async def generate_transcript(video_id: str, req: GenerateTranscriptRequest):
    """Download audio and transcribe using OpenAI Whisper API."""
    if not req.api_key:
        raise HTTPException(status_code=400, detail="OpenAI API key required for audio transcription")

    try:
        audio_path = download_audio(video_id)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    try:
        segments = transcribe_audio(audio_path, req.api_key)
    except RuntimeError as e:
        # Clean up
        if audio_path.exists():
            audio_path.unlink()
        raise HTTPException(status_code=502, detail=str(e))

    # Clean up
    if audio_path.exists():
        audio_path.unlink()

    full_text = " ".join(s["text"] for s in segments)

    return {
        "video_id": video_id,
        "segments": [
            {
                "text": s["text"],
                "start": s["start"],
                "duration": s.get("duration", 0),
                "timestamp": format_timestamp(s["start"]),
            }
            for s in segments
        ],
        "full_text": full_text,
        "total_segments": len(segments),
        "generated": True,
    }


# ── Static files & root ────────────────────────────────────────────────────

if STATIC.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


@app.get("/")
async def index():
    return FileResponse(str(STATIC / "index.html"))


# ── Entrypoint ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"🚀 YouTutor running at http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
