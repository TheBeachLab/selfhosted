# Whisper Web (Protected Upload + GPU Transcription + Diarization)

**Author:** Mr. Watson 🦄
**Date:** 2026-02-07

<!-- vim-markdown-toc GFM -->

- [Goal](#goal)
- [Quick operations](#quick-operations)
- [Nginx config](#nginx-config)
- [Basic auth file](#basic-auth-file)
- [Service app](#service-app)
- [Environment](#environment)
- [systemd unit](#systemd-unit)
- [Setup commands (sanitized)](#setup-commands-sanitized)
- [Operations](#operations)
- [Data lifecycle](#data-lifecycle)

<!-- vim-markdown-toc -->

## Goal

Expose a protected `/whisper` endpoint to upload media and generate transcript artifacts (`txt`, `srt`, `pdf`) with optional diarization.

## Quick operations

**✨ Auto-Loading Service:** Frontend always active at `https://beachlab.org/whisper/`

- GPU model loads automatically when you submit a job
- Auto-unloads after 120 seconds of inactivity (frees VRAM)
- If GPU memory is full, job fails with clear error message

```bash
systemctl status whisper-web
journalctl -u whisper-web -n 80 --no-pager
gpu-service status                    # Check GPU memory usage
```

See [GPU Service Management](gpu-services.md) for troubleshooting.

Implemented:

- Nginx route protection (`/whisper` + basic auth)
- Local service on `127.0.0.1:8060`
- Upload queue (SQLite)
- Faster-Whisper transcription (`cuda/float16` on RTX 2070 Super)
- Pyannote diarization support
- Cleanup on job deletion and post-processing

## Nginx config

Added to `beachlab.org` server block:

```nginx
location = /whisper {
    return 301 /whisper/;
}

location /whisper/ {
    auth_basic "Restricted";
    auth_basic_user_file /etc/nginx/.htpasswd-whisper;
    proxy_pass http://127.0.0.1:8060/;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $remote_addr;
    client_max_body_size 700M;
}
```

## Basic auth file

```bash
sudo htpasswd -bc /etc/nginx/.htpasswd-whisper <USER> '<PASSWORD>'
sudo chown root:www-data /etc/nginx/.htpasswd-whisper
sudo chmod 640 /etc/nginx/.htpasswd-whisper
```

> Keep credentials out of git/docs in real deployments.

## Service app

Path:

- `/opt/whisper-service/app.py`

Main endpoints (served behind `/whisper` via nginx):

- `GET /` → web UI
- `POST /jobs` → upload + create job
- `GET /jobs` → list jobs
- `GET /jobs/{id}` → job details
- `DELETE /jobs/{id}` → delete job + remove source/artifacts
- `GET /jobs/{id}/download/{txt|srt|pdf}` → artifacts

## Environment

`/etc/whisper-service.env`

```bash
# Required for speaker diarization model access
HF_TOKEN=<redacted>

# Run diarization on GPU (RTX 2070 Super, sm_75+)
WHISPER_DIAR_DEVICE=cuda
```

### Important diarization note

Pyannote diarization requires:

1. HuggingFace account + token
2. Acceptance of model terms for `pyannote/speaker-diarization-3.1`
3. `HF_TOKEN` set in `/etc/whisper-service.env`

Without token/terms acceptance, transcription may work but diarization jobs fail.

Compatibility fixes applied on host app:

- pyannote now uses `token=` (with fallback to `use_auth_token`) to match current `pyannote.audio` API.
- pyannote 4 returns `DiarizeOutput`; app now reads `output.speaker_diarization` before iterating tracks.

### GPU enforcement (2026-02-18)

Upgraded eGPU from GTX 1060 3GB (`sm_61`) to **RTX 2070 Super 8GB** (`sm_75`).

Changes applied:

- CPU fallback removed from `Engine.__init__` — if CUDA fails, service errors explicitly rather than silently falling back
- `WHISPER_DIAR_DEVICE=cuda` — diarization now runs on GPU
- Both Whisper transcription (`float16`) and pyannote diarization run fully on GPU end-to-end

## systemd unit

`/etc/systemd/system/whisper-web.service`

```ini
[Unit]
Description=Whisper web (transcription + diarization)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pink
Group=pink
WorkingDirectory=/opt/whisper-service
EnvironmentFile=/etc/whisper-service.env
ExecStart=/opt/whisper-service/.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8060
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

## Setup commands (sanitized)

```bash
sudo mkdir -p /opt/whisper-service/{uploads,outputs,temp}
sudo chown -R pink:pink /opt/whisper-service
python3 -m venv /opt/whisper-service/.venv
/opt/whisper-service/.venv/bin/pip install --upgrade pip
/opt/whisper-service/.venv/bin/pip install fastapi uvicorn[standard] python-multipart jinja2 reportlab faster-whisper
# diarization deps
/opt/whisper-service/.venv/bin/pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121
/opt/whisper-service/.venv/bin/pip install pyannote.audio
```

## Operations

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now whisper-web
sudo systemctl status whisper-web

sudo nginx -t
sudo systemctl reload nginx

# logs
sudo journalctl -u whisper-web -n 200 --no-pager
```

## Data lifecycle

- Uploaded source is stored under `/opt/whisper-service/uploads`
- Successful job deletes source file
- Artifacts are kept in `/opt/whisper-service/outputs`

Recommended next step:
- add retention cleanup timer (e.g., delete artifacts older than 30 days)
