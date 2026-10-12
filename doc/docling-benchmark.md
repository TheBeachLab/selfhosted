# Docling GPU smoke test on the NUC

Measured on 2026-10-13 Europe/Madrid (2026-10-12 22:27 UTC), on
`thebeachlab`. This was a temporary SDK test, not a Docling service deployment
or a Msgvault integration.

## What passed

The input was an 88,483-byte, two-page synthetic PDF: one page with native
text and a table, and one 200-DPI raster page requiring OCR, also with a table.
The raster page had no PDF text layer. Its SHA-256 was
`db6e78d03d9a7b29b5241f40e2918ec37d373d8b3d3346e8bb226df4fd34d502`.

All three conversions returned two pages and two tables, with the expected
references and totals on both pages. Parameter inspection confirmed that the
EasyOCR detector and recognizer, layout model, and TableFormer model ran on
`cuda:0`; the benchmark rejects unavailable CUDA and a silent CPU fallback.

| Conversion | Time for both pages | Peak process RAM (RSS) | Peak total GPU memory |
|---|---:|---:|---:|
| First successful run, loading models | 5.899 s | 2.146 GiB | 1.847 GiB |
| Models already loaded, run 2 | 1.197 s | 2.216 GiB | 1.847 GiB |
| Models already loaded, run 3 | 1.096 s | 2.205 GiB | 1.847 GiB |

Imports added 2.593 seconds before these conversion timings. Temporary
environment preparation took 82.767 seconds and model downloads took 15.560
seconds; neither is included in conversion time. Warm runs reused the same
converter and input, so these timings do not establish throughput for a large
mail archive, complex documents, or a fresh process for every document.

The highest sampled GPU utilization was 32%, with a maximum temperature of
64 C. At least 5.816 GiB of host memory remained available during the successful
runs. RSS includes mapped/shared library pages; it is not a measurement of
incremental system-wide private memory. GPU totals include the CUDA context
and the small pre-existing Xorg allocation.

## Environment and isolation

- Intel i3-1115G4, two cores / four threads, 16 GB RAM.
- NVIDIA RTX 2070 SUPER 8 GB, driver 595.99.02, compute capability 7.5.
- Ubuntu 22.04, kernel 6.8.0-138, Python 3.10.12.
- Docling 2.138.0, docling-core 2.101.1, docling-ibm-models 4.0.3,
  EasyOCR 1.7.2, PyTorch 2.11.0+cu130, torchvision 0.26.0+cu130.
- Standard PDF pipeline, table structure enabled, OCR languages en/es/de,
  two Torch CPU threads. PDF parsing still runs on the CPU.
- A private temporary venv, model directory, caches, inputs, and outputs under
  `/var/tmp/docling-gpu-dc949f25.uzhqcek3`. Torch, torchvision, Triton, and NVIDIA
  dependencies were independent copies of installed packages, including all
  top-level Torch components named in its wheel RECORD. Source environments
  were not modified.
- Dependencies were pinned into that venv; `pip check` passed. No NVIDIA
  Container Toolkit installation, Docker configuration, system package update,
  or persistent service was needed for this SDK test.
- Conversion used a transient systemd scope with MemoryMax=4G,
  MemorySwapMax=0, CPUQuota=200%, and TasksMax=256. Downloads were completed
  separately; Hugging Face access was offline during the timed conversions.

An initial attempt failed because NVRTC could not locate
`libnvrtc-builtins.so.13.0` in the copied environment. Supplying only the private
venv's `nvidia/cu13/lib` through `LD_LIBRARY_PATH` corrected the loader path.
No installed CUDA library or Docling source was patched. The three successful
runs above followed that correction.

The measurement script is
[services/docling/gpu-smoke.py](../services/docling/gpu-smoke.py). It expects an
already prepared temporary environment and synthetic input; it does not install
packages or access any archive. The tested upstream interfaces are in
[Docling's pinned model downloader](https://github.com/docling-project/docling/blob/v2.138.0/docling/utils/model_downloader.py)
and [EasyOCR adapter](https://github.com/docling-project/docling/blob/v2.138.0/docling/models/stages/ocr/easyocr_model.py).

The independent local evidence is under
`/Users/Papi/Documents/Codex/Docling-GPU-2026-10-13/`, including
`results/metrics.json`, extracted Markdown, the synthetic PDF, rendered previews,
fixture validation, observed requirements, and before/after receipts.

## Cleanup and protected application

The temporary venv, downloaded models, caches, and input copies were removed
from the NUC after exporting evidence. Both transient scopes finished inactive;
the GPU returned to 11 MiB with no CUDA process.

The Msgvault binary and config checksums, service PIDs, and service activation
timestamps were identical before and after the test. Msgvault remained the
official v0.21.0 binary. No archive, Msgvault setting, provider credential, or
Msgvault scheduled job was used or changed.

## Host observations before the test

Process PSS, which divides shared memory between processes, attributed about
2.04 GiB to OpenClaw, 1.61 GiB to Minecraft, 0.52 GiB to openHAB, and 0.20 GiB
to Msgvault plus its MCP service. All readable process PSS summed to about
6.34 GiB. Linux also held file and reclaimable slab caches, so a displayed
"used RAM" total is not solely application allocations.

During a 50-sample idle observation, GPU utilization stayed at 0%, temperature
rose from 56 to 58 C, power was 44.65-44.76 W, and fan readings briefly rose
from 0% to 36% and 41%. Xorg was the only listed graphics process; there was no
CUDA job. The active headless Xorg config explicitly selects high performance,
and `nvidia-settings -c :99 -q '[gpu:0]/GPUPowerMizerMode'` returned 1.
[NVIDIA defines 1 as prefer maximum performance](https://github.com/NVIDIA/nvidia-settings/blob/main/src/libXNVCtrl/NVCtrl.h),
and [P0 as maximum performance](https://docs.nvidia.com/deploy/nvidia-smi/index.html#performance-state).
These observations explain the heat and intermittent fan activity, but no
power-policy A/B test was performed. The GPU policy and Xorg were left unchanged.
