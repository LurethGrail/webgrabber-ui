#!/usr/bin/env python3
"""
WebGrabber - local YouTube downloader with a simple web UI.
Run: python3 server.py  →  open http://127.0.0.1:5000
"""
import os
import re
import uuid
import threading
from pathlib import Path

from flask import Flask, request, jsonify, render_template

try:
    import yt_dlp
except ImportError:
    raise SystemExit("yt-dlp not installed. Run: pip install yt-dlp flask")

app = Flask(__name__)

DEFAULT_DOWNLOAD_DIR = str(Path.home() / "Downloads" / "WebGrabber")
os.makedirs(DEFAULT_DOWNLOAD_DIR, exist_ok=True)

JOBS = {}
JOBS_LOCK = threading.Lock()

VALID_FORMATS = ("mp4", "mkv", "webm", "mp3")


def sanitize_filename(name: str) -> str:
    name = name.strip()
    name = re.sub(r'[\\/:*?"<>|]', "", name)
    name = re.sub(r"\s+", " ", name)
    return name[:200] if name else ""


def make_progress_hook(job_id):
    def hook(d):
        with JOBS_LOCK:
            job = JOBS.get(job_id)
            if job is None:
                return
            status = d.get("status")
            if status == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                downloaded = d.get("downloaded_bytes", 0)
                pct = (downloaded / total * 100) if total else job.get("progress", 0)
                job["progress"] = round(pct, 1)
                speed = d.get("speed")
                eta = d.get("eta")
                speed_str = f"{speed/1024/1024:.2f} MB/s" if speed else "—"
                eta_str = f"{eta}s" if eta is not None else "—"
                job["message"] = f"Downloading {job['progress']}%  ·  {speed_str}  ·  ETA {eta_str}"
            elif status == "finished":
                job["progress"] = 100
                job["message"] = "Merging / converting…"
            elif status == "error":
                job["status"] = "error"
                job["message"] = "Download error"
    return hook


def build_ydl_opts(fmt, outtmpl, hook):
    common = {
        "outtmpl": outtmpl,
        "progress_hooks": [hook],
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "restrictfilenames": False,
    }

    if fmt == "mp3":
        return {
            **common,
            "format": "bestaudio/best",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "0",
            }],
        }

    if fmt == "mp4":
        # Prefer H.264 video + AAC audio so the MP4 container is natively
        # playable without re-encoding. Falls back to any streams if H.264
        # isn't available, then re-muxes into mp4 via ffmpeg.
        return {
            **common,
            "format": (
                "bestvideo[vcodec^=avc1]+bestaudio[acodec^=mp4a]"
                "/bestvideo[vcodec^=avc1]+bestaudio"
                "/bestvideo[ext=mp4]+bestaudio[ext=m4a]"
                "/bestvideo+bestaudio"
                "/best"
            ),
            "merge_output_format": "mp4",
        }

    if fmt == "mkv":
        # MKV accepts any codec — always gets best quality without codec constraints
        return {
            **common,
            "format": "bestvideo+bestaudio/best",
            "merge_output_format": "mkv",
        }

    if fmt == "webm":
        return {
            **common,
            "format": (
                "bestvideo[ext=webm]+bestaudio[ext=webm]"
                "/bestvideo[vcodec^=vp]+bestaudio"
                "/bestvideo+bestaudio"
                "/best"
            ),
            "merge_output_format": "webm",
        }

    raise ValueError(f"Unknown format: {fmt}")


def run_download(job_id, url, out_dir, fmt, custom_name):
    with JOBS_LOCK:
        JOBS[job_id]["status"] = "running"
        JOBS[job_id]["message"] = "Starting…"

    os.makedirs(out_dir, exist_ok=True)

    if custom_name:
        outtmpl = os.path.join(out_dir, f"{sanitize_filename(custom_name)}.%(ext)s")
    else:
        outtmpl = os.path.join(out_dir, "%(title)s.%(ext)s")

    hook = make_progress_hook(job_id)

    try:
        ydl_opts = build_ydl_opts(fmt, outtmpl, hook)
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            raw_path = ydl.prepare_filename(info)
            final_path = os.path.splitext(raw_path)[0] + f".{fmt}"

        with JOBS_LOCK:
            JOBS[job_id].update({
                "status": "done",
                "progress": 100,
                "message": "Done",
                "filename": os.path.basename(final_path),
                "filepath": final_path,
            })
    except Exception as e:
        with JOBS_LOCK:
            JOBS[job_id]["status"] = "error"
            JOBS[job_id]["message"] = str(e)


@app.route("/")
def index():
    return render_template("index.html", default_dir=DEFAULT_DOWNLOAD_DIR)


@app.route("/api/info", methods=["POST"])
def api_info():
    data = request.get_json(force=True)
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"error": "No URL"}), 400
    try:
        opts = {"quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": True}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        return jsonify({
            "title": info.get("title"),
            "thumbnail": info.get("thumbnail"),
            "uploader": info.get("uploader"),
            "duration": info.get("duration"),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/download", methods=["POST"])
def api_download():
    data = request.get_json(force=True)
    url = (data.get("url") or "").strip()
    out_dir = (data.get("output_dir") or DEFAULT_DOWNLOAD_DIR).strip()
    fmt = (data.get("format") or "mp4").lower()
    custom_name = (data.get("filename") or "").strip()

    if not url:
        return jsonify({"error": "No URL provided"}), 400
    if fmt not in VALID_FORMATS:
        return jsonify({"error": f"Format must be one of: {', '.join(VALID_FORMATS)}"}), 400

    job_id = uuid.uuid4().hex
    with JOBS_LOCK:
        JOBS[job_id] = {"status": "queued", "progress": 0, "message": "Queued",
                        "filename": None, "filepath": None}

    threading.Thread(
        target=run_download,
        args=(job_id, url, out_dir, fmt, custom_name),
        daemon=True,
    ).start()

    return jsonify({"job_id": job_id})


@app.route("/api/status/<job_id>")
def api_status(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is None:
            return jsonify({"error": "Unknown job"}), 404
        return jsonify(job)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5001)
    args = parser.parse_args()
    print(f"WebGrabber → http://localhost:{args.port}")
    print(f"Default save folder: {DEFAULT_DOWNLOAD_DIR}")
    app.run(host="0.0.0.0", port=args.port, debug=False)
