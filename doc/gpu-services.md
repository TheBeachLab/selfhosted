# GPU Service Management (On-Demand)

**Author:** Mr. Watson 🦄
**Date:** 2026-02-19

<!-- vim-markdown-toc GFM -->

- [Goal](#goal)
- [Hardware context](#hardware-context)
- [Services](#services)
- [Management tool](#management-tool)
- [Usage](#usage)
- [Operations](#operations)
- [Why on-demand](#why-on-demand)

<!-- vim-markdown-toc -->

## Goal

Manage GPU-intensive services (Whisper, RAG, Qwen3-TTS) with on-demand start/stop to avoid VRAM exhaustion.

## Hardware context

- **GPU:** NVIDIA RTX 2070 Super 8GB (via eGPU, USB-C/Thunderbolt)
- **Total VRAM:** 8192 MiB
- **Services can NOT run simultaneously:** Combined VRAM usage exceeds capacity

VRAM usage per service (approximate):

- Whisper (transcription + diarization): ~3.5 GB
- RAG library (embeddings + reranker): ~1.2 GB
- Qwen3-TTS 1.7B (voice cloning): ~4.3 GB

**Combined:** ~9 GB → exceeds 8 GB VRAM

## Services

All three GPU services are configured to **NOT auto-start** on boot:

- `whisper-web.service` (port 8060, `/whisper` endpoint)
- `rag-library-ingest.service` (SFTP inbox watcher)
- `qwen3-tts.service` (port 8070, `/tts` endpoint)

## Management tool

`/usr/local/bin/gpu-service` — CLI tool for start/stop/status

## Usage

### Check status

```bash
gpu-service status
```

Output:
- Service states (active/inactive)
- GPU memory usage per process
- Total VRAM used/available

### Start a service

```bash
gpu-service start whisper
gpu-service start rag
gpu-service start tts
```

**Important:** Only start ONE service at a time.

### Stop a service

```bash
gpu-service stop whisper
gpu-service stop rag
gpu-service stop tts
```

Stop all:

```bash
gpu-service stop all
```

### Switch services

To switch from one GPU service to another:

```bash
gpu-service stop whisper
gpu-service start tts
```

Wait 2-3 seconds between stop and start for VRAM cleanup.

## Operations

### Typical workflows

**Transcription job:**

1. `gpu-service start whisper`
2. Upload audio to `https://beachlab.org/whisper/`
3. Wait for job to complete
4. Download transcript
5. `gpu-service stop whisper` (when done with transcriptions)

**eBook indexing:**

1. `gpu-service start rag`
2. Upload PDFs/EPUBs via SFTP to `/home/sftpuser/library_inbox`
3. Monitor logs: `journalctl -u rag-library-ingest -f`
4. `gpu-service stop rag` (when inbox is empty)

**Voice cloning:**

1. `gpu-service start tts`
2. Navigate to `https://beachlab.org/tts/`
3. Upload reference audio + generate speech
4. Download wav files
5. `gpu-service stop tts` (when done)

### Quick check before starting

```bash
gpu-service status
```

If any service shows `active`, stop it first:

```bash
gpu-service stop all
```

### Emergency: all services stuck

```bash
sudo systemctl stop whisper-web rag-library-ingest qwen3-tts
```

Or kill GPU processes directly (last resort):

```bash
sudo pkill -9 -f "whisper-service|rag-library|qwen3-tts"
```

## Why on-demand

1. **VRAM limit:** 8GB is not enough to run all three services simultaneously
2. **Sporadic use:** Whisper, RAG, and TTS are used infrequently, not 24/7
3. **Resource efficiency:** GPU idle when not needed
4. **Flexibility:** Easy to swap services depending on task

Alternative approaches considered but rejected:

- ❌ **Smaller models:** Qwen3-TTS 0.6B has noticeably lower quality
- ❌ **Auto-stop on idle:** Complex to implement reliably, race conditions
- ❌ **Shared VRAM pool:** Not supported by PyTorch/CUDA without model unloading
- ✅ **Manual on-demand:** Simple, explicit, predictable

Future improvement (if needed): systemd socket activation to auto-start services on first HTTP request.
