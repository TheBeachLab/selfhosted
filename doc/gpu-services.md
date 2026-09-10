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
- [Thunderbolt Hot-Unplug Caveat](#thunderbolt-hot-unplug-caveat)

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

## eGPU session model (required for host stability)

**Recovered internal notes from 2026-08-04/05; not externally verified.**
The original logs supporting the historical rows below were not recovered in
this review; these rows must not be treated as a newly verified root cause.

| Evidence | What it shows |
|---|---|
| Heartbeat gaps with `bolt=authorized` ending in unclean reboot | Hard hang / forced restart, not `systemctl reboot` |
| 2026-08-04 ~19:00 UTC → boot ~20:13 | ~12 h continuous attach, then silence (~73 min journal gap) |
| 2026-08-05 ~19:33 UTC → boot ~20:30 | ~22 h continuous attach, then silence (~57 min journal gap); load/RAM healthy minutes before |
| Weekly ~05:00 reboots with Core X off | Clean multi-day uptime without eGPU |
| No `systemctl reboot` in `auth.log` on those hang days | Not intentional software reboot |

**Inference (not externally verified as root cause):** long-lived Thunderbolt/PCIe
attachment of the Core X on this NUC+Linux stack is unsafe. Failures are not
limited to heavy CUDA jobs; idle attach for half a day has been enough. Full
“always-on eGPU” on this host is not a reliable goal with the current
NUC11TNKi3 + Razer Core X + Ubuntu 22.04 HWE 6.8 path. Industry reports of
similar TB3 eGPU `Xid 79` / bus-loss failures on Linux are common; see
[NVIDIA forum Core X Xid 79](https://forums.developer.nvidia.com/t/driver-crash-xid-79-gpu-has-fallen-off-the-bus-with-egpu-razer-core-x/347658).

### How to use the eGPU for jobs (stable pattern)

1. **Cold start with Core X on** (preferred): power off NUC → power Core X →
   TB cable seated → wait a few seconds → power on NUC.
2. Confirm GPU: `egpu-session status` or `nvidia-smi`.
3. Open a session: `egpu-session start "whisper batch"`.
4. Run jobs (Whisper / TTS / ComfyUI / RAG). Prefer finishing within **~6 hours**.
5. End cleanly:
   ```bash
   egpu-session end
   # power OFF Core X (do not hot-unplug TB while NUC is up)
   sudo systemctl reboot
   ```
   Or: `egpu-session end --reboot` after powering the enclosure off first if you
   accept an immediate reboot.

### Tools (deployment checked 2026-09-10)

| Path | Role |
|---|---|
| `/usr/local/bin/egpu-session` | status / start / end / doctor |
| `/usr/local/bin/egpu-watchdog.sh` | loss recovery + **max-age iGotify** (warn 6 h, critical 10 h) |
| `/etc/egpu-watchdog.env` | `EGPU_WARN_S=21600`, `EGPU_CRITICAL_S=36000` |
| Repo copies | `scripts/egpu/egpu-session.sh`, `scripts/egpu/egpu-watchdog.sh` |

On 2026-09-10, SHA-256 comparison over SSH confirmed both repository scripts
match those paths on `pink-sudo`; `/etc/egpu-watchdog.env` contains the thresholds
above. This checks installed content, not runtime recovery behavior.
The recovered `egpu-session` script sources its state as shell code and does not
quote notes containing spaces when saving them; treat this as a known limitation
of the deployed snapshot, not a validated state-file interface.

Watchdog still skips auto-recovery when `boltctl` says `disconnected` (Core X
intentionally off). It cannot prevent a hard freeze once the kernel stops
scheduling; max-age alerts exist so you tear down **before** that window.

### Thunderbolt hot-unplug caveat

**Observed on `thebeachlab` (NUC11TNKi3 + Razer Core X + RTX 2070 SUPER, June 2026):**

- Normal boot with eGPU attached works
- `boltctl` shows `Razer Core X` as `authorized`
- `nvidia-smi` works
- GPU services (`comfyui`, `qwen3-tts`, `whisper-web`) can use the card normally

**What breaks it reliably:**

- Unplugging the Thunderbolt cable while the eGPU is live
- Reconnecting the cable in the same runtime session
- Leaving the Core X authorized for many hours (including idle)

**What Linux reports when it breaks (when logs flush):**

```text
thunderbolt 0-3: device disconnected
pcieport 0000:00:07.0: pciehp: Slot(0): Link Down
NVRM: Xid (PCI:0000:04:00): 79, GPU has fallen off the bus.
NVRM: Xid (PCI:0000:04:00): 154, GPU recovery action changed ... GPU Reset Required
```

Hard freezes often leave **no** final Xid line because the journal never flushes.

**Typical broken-state symptoms after reconnect:**

- Core X light comes back on
- `boltctl` may return to `authorized`
- `lspci` may still list the NVIDIA device, sometimes as `rev ff`
- `nvidia-smi` fails with `No devices were found`
- Server fan can ramp hard during the failure window

**Operational rules:**

- Do **not** hot-unplug or hot-replug the Thunderbolt cable while the NUC is up
- Treat the eGPU cable as effectively non-hot-swappable for production use
- Do **not** leave Core X powered for multi-day always-on; use sessions

**Recovery:**

1. Stop touching the Thunderbolt cable
2. Reboot the host (hard power if frozen)
3. Re-check:

```bash
boltctl list
lspci | grep -i nvidia
nvidia-smi
egpu-session status
```

If the reboot path does not recover cleanly, escalate to full power-off / power-on
of NUC **and** Core X (see Razer power-cycle notes in [gpu.md](gpu.md)).

**Notes from local testing:**

- Updating BIOS from `0073` to `0078` improved overall stability but did **not** make hot-unplug safe
- `pcie_port_pm=off` is kept as part of the stable baseline
- On 2026-07-18, `pcie_aspm=off` was added alongside it after confirming that
  both Thunderbolt root ports still had ASPM L1 enabled. GRUB was regenerated
  and validated; a cold boot with the Core X connected is required to activate
  and verify the change
- Pre-change GRUB backup: `/etc/default/grub.pre-aspm-20260718`
- GSP firmware disabled via `/etc/modprobe.d/nvidia-no-gsp.conf` (`NVreg_EnableGpuFirmware=0`)
- The issue matches known Linux/NVIDIA/Thunderbolt reports around `Xid 79` and "fallen off the bus"

### Still-open experiments (when you next need a long GPU day)

These are planned A/B tests from [gpu.md](gpu.md#current-research-and-runtime-stability-test-2026-08-04), not done yet:

1. Same workload on kernel `6.8.0-134-generic` vs default `6.8.0-136` (NVIDIA held at 595.84).
2. Only if kernels both hang: controlled NVIDIA `595.71.05` rollback with matched packages.
3. Physical: alternate TB port + known-good short certified cable (≤60 cm).

Do not expect a pure software patch to make always-on Core X safe until an A/B
test proves a regression and a rollback holds under continuous attach.

## Recovery after dead PSU/GPU

**Historical context:** The Razer Core X PSU died on 2026-03-04, so GPU services were disabled for a while to avoid continuous errors and freezes.

### Current state (restored on 2026-06-10)

| Service | State |
|---|---|
| `whisper-web` | enabled + active |
| `qwen3-tts` | enabled + active |
| `comfyui` | enabled + active |
| `nvidia-persistenced` | enabled + active |
| `egpu-watchdog.timer` | enabled + active |
| Telegraf `inputs.nvidia_smi` | enabled |

Current runtime after restore:

- eGPU: `Razer Core X` authorized via Thunderbolt
- GPU: `NVIDIA GeForce RTX 2070 SUPER`
- Driver: `595.71.05`
- `nvidia-smi`: OK
- Persistence mode: ON

### Restore procedure (if the eGPU disappears again)

**1. Prefer cold boot, not hot-plug:**

1. Power off host
2. Connect/power the Razer Core X
3. Wait 5-10 seconds
4. Boot host

**2. Verify the GPU is visible:**

```bash
boltctl
lspci | grep -i nvidia
nvidia-smi
```

If `nvidia-smi` fails, try:

```bash
sudo modprobe nvidia
nvidia-smi
```

**3. Re-enable GPU services if they were disabled:**

```bash
sudo systemctl enable --now nvidia-persistenced
sudo systemctl enable --now whisper-web
sudo systemctl enable --now qwen3-tts
sudo systemctl enable --now comfyui
sudo systemctl enable --now egpu-watchdog.timer
```

**4. Re-enable Telegraf monitoring if needed:**

Ensure `/etc/telegraf/telegraf.d/nuc-timescale.conf` contains:

```toml
[[inputs.nvidia_smi]]
  bin_path = "/usr/local/bin/nvidia-smi-safe.sh"
  timeout = "5s"
```

Then:

```bash
sudo systemctl restart telegraf
sudo journalctl -u telegraf -n 10 --no-pager | grep -E "Error|nvidia"
```

**5. Verify watchdog + heartbeat instrumentation:**

```bash
systemctl status egpu-watchdog.timer host-heartbeat-log.timer --no-pager
tail -n 20 /var/log/host-heartbeat.log
```

Expected behavior:

- one alert when the eGPU is lost
- one alert when it recovers
- no repeating half-hour alerts while it remains missing
- heartbeat log includes explicit transition lines such as:

```text
event=egpu_lost last_ok=2026-06-15T05:03:29Z detected_at=2026-06-15T05:04:33Z
event=egpu_recovered missing_since=2026-06-15T05:04:33Z detected_at=2026-06-15T05:18:12Z
```

**6. Verify telemetry:**

```bash
DRY_RUN=true bash /home/pink/.openclaw/workspace/scripts/publish_telemetry.sh | python3 -m json.tool | grep gpu
```

The `gpu` field should show real temp/util values instead of `null`.

**7. Quick service test:**

```bash
curl -I http://localhost:8060/      # whisper-web
curl -I http://localhost:8070/      # qwen3-tts
curl -I http://localhost:8188/      # comfyui
curl http://localhost:8060/openapi.json | jq '.info'
curl http://localhost:8070/openapi.json | jq '.info'
```

Note: `whisper-web` and `qwen3-tts` do not expose `/health`; use `/`, `/docs`, or `/openapi.json` instead.

### Log checks

```bash
journalctl -k -b | grep -iE 'NVRM|Xid|nvidia|thunderbolt|bolt'
```

On the 2026-06-10 restore there were no `Xid` errors after boot. Only one benign-looking line appeared during bring-up:

```text
nvidia-gpu 0000:04:00.3: i2c timeout error e0000000
```
