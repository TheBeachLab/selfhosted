# Qwen3-TTS Voice Cloning Service

**Author:** Mr. Watson 🦄
**Date:** 2026-02-19

<!-- vim-markdown-toc GFM -->

- [Goal](#goal)
- [Quick operations](#quick-operations)
- [Nginx config](#nginx-config)
- [Basic auth](#basic-auth)
- [Service app](#service-app)
- [Environment](#environment)
- [systemd unit](#systemd-unit)
- [Setup commands](#setup-commands)
- [Operations](#operations)
- [Usage](#usage)

<!-- vim-markdown-toc -->

## Goal

Self-hosted voice cloning and multilingual TTS with Qwen3-TTS 1.7B. Clone any voice with 3+ seconds of audio, generate speech in 10 languages.

## Quick operations

**⚠️ On-Demand Service:** Qwen3-TTS does NOT auto-start on boot. Use `gpu-service` to manage it:

```bash
gpu-service status                    # Check if running
gpu-service start tts                 # Start when needed
gpu-service stop tts                  # Stop when done
```

See [GPU Service Management](gpu-services.md) for details.

Status check (when running):

```bash
systemctl status qwen3-tts
curl -I https://beachlab.org/tts/
journalctl -u qwen3-tts -n 80 --no-pager
```

Implemented:

- Nginx route protection (`/tts` + basic auth)
- Local service on `127.0.0.1:8070`
- Upload queue (SQLite)
- Voice cloning from reference audio (3-60s)
- Multilingual generation (Chinese, English, Japanese, Korean, German, French, Russian, Portuguese, Spanish, Italian)
- Natural language voice control ("excited", "calm and soothing", etc.)

## Nginx config

Added to `beachlab.org` server block:

```nginx
location = /tts {
    return 301 /tts/;
}

location /tts/ {
    auth_basic "Restricted";
    auth_basic_user_file /etc/nginx/.htpasswd-qwen3tts;
    proxy_pass http://127.0.0.1:8070/;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $remote_addr;
    client_max_body_size 200M;
}
```

## Basic auth

```bash
sudo htpasswd -bc /etc/nginx/.htpasswd-qwen3tts <USER> '<PASSWORD>'
sudo chown root:www-data /etc/nginx/.htpasswd-qwen3tts
sudo chmod 640 /etc/nginx/.htpasswd-qwen3tts
```

## Service app

Path:

- `/opt/qwen3-tts/app.py`

Main endpoints (served behind `/tts` via nginx):

- `GET /` → web UI
- `POST /jobs` → create voice cloning job
- `GET /jobs` → list jobs
- `GET /jobs/{id}` → job details
- `DELETE /jobs/{id}` → delete job + remove audio
- `GET /jobs/{id}/download` → download generated wav

## Environment

`/etc/qwen3-tts.env`

```bash
# Qwen3-TTS model (1.7B for best quality with 8GB VRAM)
QWEN_MODEL=Qwen/Qwen3-TTS-12Hz-1.7B-Base
```

### GPU (RTX 2070 Super 8GB)

- **Model:** `Qwen3-TTS-12Hz-1.7B-Base` (voice cloning)
- **VRAM:** 6-8GB
- **Inference:** `torch.bfloat16`, CUDA-only
- **Expected performance:** near real-time (RTF ~1.2-1.5)

Lighter alternative for faster inference (4-6GB VRAM):

```bash
QWEN_MODEL=Qwen/Qwen3-TTS-12Hz-0.6B-Base
```

## systemd unit

`/etc/systemd/system/qwen3-tts.service`

```ini
[Unit]
Description=Qwen3-TTS voice cloning service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pink
Group=pink
WorkingDirectory=/opt/qwen3-tts
EnvironmentFile=/etc/qwen3-tts.env
ExecStart=/opt/qwen3-tts/.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8070
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

## Setup commands

```bash
sudo mkdir -p /opt/qwen3-tts/{uploads,outputs,temp}
sudo chown -R pink:pink /opt/qwen3-tts
python3 -m venv /opt/qwen3-tts/.venv
/opt/qwen3-tts/.venv/bin/pip install --upgrade pip setuptools wheel
/opt/qwen3-tts/.venv/bin/pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
/opt/qwen3-tts/.venv/bin/pip install qwen-tts fastapi uvicorn[standard] python-multipart soundfile
```

Optional (2-3x faster inference, requires CUDA + build tools):

```bash
/opt/qwen3-tts/.venv/bin/pip install -U flash-attn --no-build-isolation
```

If low RAM (<96GB) + many CPU cores:

```bash
MAX_JOBS=4 /opt/qwen3-tts/.venv/bin/pip install -U flash-attn --no-build-isolation
```

## Operations

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now qwen3-tts
sudo systemctl status qwen3-tts

sudo nginx -t
sudo systemctl reload nginx

# logs
sudo journalctl -u qwen3-tts -n 200 --no-pager
```

## Usage

1. Navigate to `https://beachlab.org/tts/` (requires basic auth)
2. Upload reference audio (3-60s, clear speech, wav/mp3/ogg/etc.)
3. Provide exact transcription of reference audio
4. Write text to generate
5. Select language (or leave Auto)
6. Optional: add voice instructions ("excited", "whisper", "slow and dramatic", etc.)
7. Click "Generate Speech"
8. Download generated wav when status = done

### Language support

- Chinese
- English
- Japanese
- Korean
- German
- French
- Russian
- Portuguese
- Spanish
- Italian

### Voice instructions examples

- "Speak with excitement and enthusiasm"
- "Sad and tearful voice"
- "Angry and frustrated tone"
- "Calm, soothing, and reassuring"
- "Whisper"
- "Slow, deliberate pace with dramatic pauses"

### Performance notes

- First job triggers model download (~3.4GB for 1.7B model)
- Warm-up inference can take 10-20s
- Subsequent generations: ~1.2-1.5x real-time on RTX 2070 Super
- Longer text (>200 words) may take several minutes

### Data lifecycle

- Reference audio stored in `/opt/qwen3-tts/uploads`
- Successful job deletes reference audio
- Generated wav kept in `/opt/qwen3-tts/outputs`

Recommended: add retention cleanup timer (e.g., delete outputs older than 7 days).
