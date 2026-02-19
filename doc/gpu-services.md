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

Monitor and manage GPU-intensive services (Whisper, RAG, Qwen3-TTS) with automatic lazy-loading and manual control to avoid VRAM exhaustion.

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

GPU service behavior:

- **`whisper-web.service`** (port 8060, `/whisper` endpoint)
  - ✨ **Auto-loading:** Frontend always active, GPU model loads on first job
  - Auto-unloads after 120 seconds of inactivity
  - Auto-starts on boot

- **`qwen3-tts.service`** (port 8070, `/tts` endpoint)
  - ✨ **Auto-loading:** Frontend always active, GPU model loads on first job
  - Auto-unloads after 120 seconds of inactivity
  - Auto-starts on boot

- **`rag-library-ingest.service`** (SFTP inbox watcher)
  - ⚠️ **Manual control:** Must be started/stopped manually with `gpu-service`
  - Does NOT auto-start on boot
  - Runs continuously when active (no auto-unload)

## Auto-Loading Behavior (Whisper/TTS)

**How it works:**

1. **Service always running:** FastAPI frontend available 24/7
2. **GPU model lazy-loads:** Only loaded when first job arrives in queue
3. **Auto-unload on idle:** After 120 seconds with no jobs, model is unloaded and VRAM freed
4. **Failsafe:** If GPU OOM during load, job fails with clear error message

**Example timeline:**

```
00:00 - User visits https://beachlab.org/whisper/
00:01 - User uploads audio and clicks "Transcribe"
00:02 - Worker thread detects queued job
00:03 - GPU model begins loading (~10-20s first time)
00:22 - Model loaded, transcription starts
00:45 - Job completes, marked as 'done'
02:45 - No new jobs for 120s → model unloads, VRAM freed
```

**Benefits:**

- No 502 errors (frontend always available)
- No manual service management needed
- Efficient VRAM usage (only allocated when needed)
- Multiple users can queue jobs (processed sequentially)

## Management tool

`/usr/local/bin/gpu-service` — CLI tool for monitoring and manual control

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

**Transcription job (automatic):**

1. Navigate to `https://beachlab.org/whisper/`
2. Upload audio and submit job
3. GPU model loads automatically (first job may take 10-20s)
4. Wait for job to complete
5. Download transcript
6. Model auto-unloads after 2 minutes of inactivity

**Voice cloning (automatic):**

1. Navigate to `https://beachlab.org/tts/`
2. Upload reference audio + enter text
3. GPU model loads automatically (first job may take 10-20s)
4. Wait for generation to complete
5. Download wav file
6. Model auto-unloads after 2 minutes of inactivity

**eBook indexing (manual):**

1. Check GPU status: `gpu-service status`
2. If Whisper/TTS are idle, proceed. If not, wait or use `gpu-service stop all`
3. `gpu-service start rag`
4. Upload PDFs/EPUBs via SFTP to `/home/sftpuser/library_inbox`
5. Monitor logs: `journalctl -u rag-library-ingest -f`
6. `gpu-service stop rag` (when inbox is empty)

### VRAM conflict handling

**Automatic (Whisper/TTS):**

If you submit a job and GPU memory is full:
- Job will be marked as `failed`
- Error message: "GPU memory full. Please stop other GPU services (gpu-service stop all) and try again."
- Check `gpu-service status` to see what's using VRAM
- Stop conflicting service or wait for auto-unload (120s idle)

**Manual (RAG):**

Before starting RAG, check for conflicts:

```bash
gpu-service status
```

If Whisper or TTS are using GPU:
- Wait for auto-unload (check logs for "unloading model" message)
- Or force stop: `gpu-service stop all`

Then start RAG:

```bash
gpu-service start rag
```

### Emergency: all services stuck

```bash
sudo systemctl stop whisper-web rag-library-ingest qwen3-tts
```

Or kill GPU processes directly (last resort):

```bash
sudo pkill -9 -f "whisper-service|rag-library|qwen3-tts"
```

## Why lazy-loading + manual control

1. **VRAM limit:** 8GB is not enough to run all three services simultaneously
2. **Sporadic use:** Whisper, RAG, and TTS are used infrequently, not 24/7
3. **Resource efficiency:** GPU idle when not needed
4. **User experience:** Frontends always accessible, no manual service management needed

**Design decisions:**

- ✅ **Auto-loading (Whisper/TTS):** Frontend always available, GPU loads on demand
  - No CUDA OOM on startup (model loads when first job arrives)
  - Auto-unload after idle timeout (frees VRAM for other services)
  - Failsafe: if GPU memory full, job fails with clear message
- ⚠️ **Manual control (RAG):** Continuous processing when active
  - No auto-unload (watcher runs continuously until stopped)
  - Requires explicit `gpu-service start rag` before use
  - Prevents unexpected VRAM usage when uploading large batches

**Alternative approaches considered but rejected:**

- ❌ **Smaller models:** Qwen3-TTS 0.6B has noticeably lower quality
- ❌ **Shared VRAM pool:** Not supported by PyTorch/CUDA without full model unloading
- ❌ **Always-on all services:** Exceeds 8GB VRAM capacity
