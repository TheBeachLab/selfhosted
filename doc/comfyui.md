# ComfyUI

ComfyUI node-based image/video GUI, served at `https://comfyui.beachlab.org`
through [Authentik with a passkey](authentik.md).

- [Stack](#stack)
- [Install paths](#install-paths)
- [Service](#service)
- [Nginx](#nginx)
- [Change auth password](#change-auth-password)
- [Add/update models](#addupdate-models)
- [Noct Q V4 / Qwen Image 2.1](#noct-q-v4--qwen-image-21)
- [Krea Noct V4 / Krea2](#krea-noct-v4--krea2)
- [Custom nodes (ComfyUI Manager)](#custom-nodes-comfyui-manager)
- [Update ComfyUI](#update-comfyui)
- [DNS + SSL setup (one-time, after DNS propagation)](#dns--ssl-setup-one-time-after-dns-propagation)
- [Troubleshooting](#troubleshooting)

## Stack

- **Service:** `comfyui.service` — port `8188` (127.0.0.1 only)
- **Backend:** ComfyUI v0.38.0, commit `6b747c04`.
- **Frontend:** v1.53.6; workflow templates v0.11.70.
- **Proxy:** Nginx → `comfyui.beachlab.org` with Authentik + HTTPS.
- **GPU:** RTX 2070 Super 8GB, PyTorch 2.11.0+cu130, CUDA runtime 13.0.
- **Driver:** NVIDIA 595.91.07, observed on 2026-10-02.
- **Memory:** `MemoryHigh=8G`, `MemoryMax=10G`, disk-backed dynamic loading
  (`--fast-disk`) and pinned memory disabled, to fit this 16 GiB host.

This setup uses [v0.38.0](https://github.com/Comfy-Org/ComfyUI/releases/tag/v0.38.0).
ComfyUI stays disabled at boot and is started for eGPU sessions; see
[GPU service management](gpu-services.md).

## Install paths

| Path | Purpose |
|---|---|
| `/opt/comfyui/` | App root |
| `/opt/comfyui/.venv/` | Active Python venv symlink |
| `/opt/comfyui/venvs/noctq-62607250/` | Validated PyTorch/CUDA 13 runtime |
| `/opt/comfyui/.venv.pre-noctq-62607250/` | Previous PyTorch 2.6/CUDA 12.4 runtime |
| `/opt/comfyui/models/` | Models (checkpoints, loras, VAE, etc.) |
| `/opt/comfyui/output/` | Generated images |
| `/opt/comfyui/input/` | Input images |
| `/opt/comfyui/custom_nodes/` | Extensions |
| `/opt/comfyui/user/default/workflows/` | Workflows visible in the UI |

## Service

```bash
sudo systemctl status comfyui
sudo systemctl restart comfyui
journalctl -u comfyui -f
```

## Nginx

The HTTP Basic settings below are kept for recovery; the site uses Authentik.

```bash
sudo nginx -t && sudo nginx -s reload
cat /etc/nginx/sites-available/comfyui.beachlab.org
```

## Change auth password

```bash
sudo htpasswd -b /etc/nginx/.htpasswd-comfyui fran NEW_PASSWORD
sudo nginx -s reload
```

## Add/update models

Use the folder specified by the model publisher. Single-file diffusion models,
text encoders and VAEs belong in `models/diffusion_models`,
`models/text_encoders` and `models/vae`, respectively. Older combined
checkpoints use `models/checkpoints`. Refresh the model list after downloading.

## Noct Q V4 / Qwen Image 2.1

Installed on 2026-10-02 from
[Noctaluna's model card](https://huggingface.co/Noctaluna/Noct-Q-Uncensored-Qwen-Image-2.1/blob/a81b9af51120a78e285e57906f2250a2a02080e9/README.md)
and [Comfy-Org's repackaged dependencies](https://huggingface.co/Comfy-Org/Qwen-Image-2.1/blob/cb504a4090723e43f17ad01cec0359490e2de613/README.md).
The three files total 17,283,092,416 bytes:

| File | Folder | Size |
|---|---|---|
| `NoctQ_V4_int8_convrot.safetensors` | `diffusion_models` | 7,256,784,368 bytes |
| `qwen3vl_8b_int8_convrot.safetensors` | `text_encoders` | 9,350,798,360 bytes |
| `qwen_image_2.1_vae_bf16.safetensors` | `vae` | 675,509,688 bytes |

[The model manifest](../services/comfyui/noctq-models.json) fixes repository
revisions, paths, sizes and upstream LFS SHA-256 values. All three hashes were
verified before installation. To reproduce the download from this repository:

```bash
/opt/comfyui/.venv/bin/python services/comfyui/install-noctq.py \
  --hf /opt/comfyui/.venv/bin/hf --comfyui /opt/comfyui
```

The installer stages downloads on the model filesystem, checks size and
SHA-256, and refuses to replace an existing file with a different hash. License,
attribution and manifest copies live in
`user/default/model-info/NoctQ-V4/`.

Open **Workflows → NoctQ → NoctQ_V4_NUC_8GB**. The source is
[NoctQ_V4_NUC_8GB.json](../services/comfyui/workflows/NoctQ_V4_NUC_8GB.json);
[the API export](../services/comfyui/workflows/NoctQ_V4_NUC_8GB.api.json) is
also included. The UI workflow is installed at
`/opt/comfyui/user/default/workflows/NoctQ/NoctQ_V4_NUC_8GB.json`.

Settings: 768 × 1024, batch 1, 25 steps, Euler, simple scheduler, CFG 3,
tiled VAE decoding with 512 px tiles and 64 px overlap. The text encoder's
`resolution` controls reference-image resizing; output dimensions come from
`Empty Latent Image`. The example prompt is a cat in a coastal workshop.
CFG 1 is the publisher's quicker draft option and ignores the negative prompt.
The publisher's 1024 × 1536 setting has not been benchmarked on this host.

Two 768 × 1024 runs took 137.86 and 123.59 seconds on this host. Outputs are
under `output/NoctQ_V4/`. Unload models after a job to free the GPU.
The update retained the 16 UniRig/MIA nodes; older workflows still need trying
on the new runtime.

Built with Qwen. The publisher's
[Qwen Research License](https://huggingface.co/Noctaluna/Noct-Q-Uncensored-Qwen-Image-2.1/blob/a81b9af51120a78e285e57906f2250a2a02080e9/LICENSE)
limits use to non-commercial research/evaluation. Copies of
[LICENSE](../services/comfyui/NoctQ-LICENSE.txt) and
[NOTICE](../services/comfyui/NoctQ-NOTICE.txt) accompany the modified workflow.

## Krea Noct V4 / Krea2

Installed and SHA-256 verified on 2026-10-02. The NUC profile uses the public
INT8 convrot V4 weights from
[Noctaluna's pinned repository](https://huggingface.co/Noctaluna/Krea2-Noct-Uncensored/tree/d93fbcb45e6f6995f2ecdd4edfdb1ef12db6e6e4),
with dependencies from
[Comfy-Org/Krea-2](https://huggingface.co/Comfy-Org/Krea-2/tree/eb1eddd3983a54678545a9b2c178c5853b30f7be).
The publisher recommends 12 GB or more for INT8, and INT4 from Civitai for
8 GB cards. This local INT8 profile uses the existing NVMe dynamic loading;
it does not keep the whole diffusion model in VRAM.

| File | Folder | Size |
|---|---|---|
| `KreaNoct_V4_int8_convrot.safetensors` | `diffusion_models` | 13,492,706,520 bytes |
| `qwen3vl_4b_fp8_scaled.safetensors` | `text_encoders` | 5,242,467,968 bytes |
| `qwen_image_vae.safetensors` | `vae` | 253,806,246 bytes |

Total weights: 18,988,980,734 bytes. The
[manifest](../services/comfyui/krea2-models.json) pins revisions, sizes and
upstream SHA-256 values. The
[installer](../services/comfyui/install-krea2.py) verifies every file before
publishing it without replacing a different existing file:

```bash
/opt/comfyui/.venv/bin/python services/comfyui/install-krea2.py \
  --hf /opt/comfyui/.venv/bin/hf --comfyui /opt/comfyui
```

Open **Workflows → KreaNoct → KreaNoct_V4_NUC_8GB**. The
[UI workflow](../services/comfyui/workflows/KreaNoct_V4_NUC_8GB.json) and
[API export](../services/comfyui/workflows/KreaNoct_V4_NUC_8GB.api.json)
use core nodes from the installed official `image_krea2_turbo_t2i_int8.json`
template in workflow templates 0.11.70. The template SHA-256 is in the manifest.
The workflow has been flattened and adapted with no prompt enhancer or LoRA.

Settings: 768 × 1024, batch 1, 8 steps, Euler, simple scheduler, CFG 1,
`CLIPLoader` type `krea2`, and 512 px tiled VAE decoding with 64 px overlap.
`ConditioningZeroOut` supplies the unused negative conditioning at CFG 1.
Change the green prompt node to describe the desired image. Use one GPU job
at a time and unload models after a session. The publisher's 1024 × 1536
setting has not been benchmarked on this host.

Validation on the installed 0.38.0 backend and RTX 2070 Super:
a 512 × 512 / 2-step smoke test took 17.34 seconds. The saved workflow was
opened and run through the UI at 768 × 1024 / 8 steps in 32.81 seconds. A
second full run, after clearing both model and node caches, completed in
40.25 seconds with no cached nodes. Its sampled GPU usage reached 7,455 MiB
and the ComfyUI cgroup reached 6,265,049,088 bytes (about 5.84 GiB), below the
10 GiB service limit. These figures apply to this profile, prompt and stack.
The two full outputs are `output/KreaNoct_V4/NUC_00001_.png` and
`NUC_00002_.png`. Validation prompt IDs: `d8c18bdf-737d-4a5e-8181-2e7598347cd1`
(UI) and `86868376-4630-4b74-ab42-a0e7f5be99d4` (empty caches).

The [Krea 2 Community License](../services/comfyui/Krea2-LICENSE.pdf) and
[attribution](../services/comfyui/Krea2-NOTICE.txt) are retained beside the
manifest in `user/default/model-info/KreaNoct-V4/`. The weights are unmodified.

## Custom nodes (ComfyUI Manager)

Install ComfyUI Manager for easy node/extension management:

```bash
cd /opt/comfyui/custom_nodes
git clone https://github.com/Comfy-Org/ComfyUI-Manager.git
sudo systemctl restart comfyui
```

## Update ComfyUI

Prepare a stable upstream release in this conversation's linked worktree on a
`codex/<task-slug>-<conversation-fingerprint>` branch. Keep pre-existing
untracked scripts and workflows in the installed checkout. Release patch tags
can diverge from later releases, so do not assume a fast-forward update.

Prepare dependencies in a separate runtime, preserve the old environment and
back up `user/` before starting the new backend. Current ComfyUI requires
PyTorch >= 2.7 and CUDA 13.0 wheels for NVIDIA 20-series cards; see the
[v0.38.0 NVIDIA install instructions](https://github.com/Comfy-Org/ComfyUI/blob/v0.38.0/README.md#nvidia).
[runtime-constraints.txt](../services/comfyui/runtime-constraints.txt) pins the
matching trio tested on this host. Install that trio from
`https://download.pytorch.org/whl/cu130`, then install the release requirements
with the constraints file.

Validate the release on a separate loopback port with
`--base-directory /opt/comfyui`. With both queues empty and the validation
process stopped, integrate the tested release into the installed detached
checkout, activate the validated environment and check the normal service.
Remove the temporary worktree and branch after verifying the installed target
contains its tip and it has no remaining work or active process.

For the 2026-10-02 update, the previous backend was `ba9ffa0a` (v0.24.1).
The original runtime remains at `.venv.pre-noctq-62607250`. User data was
copied to `/var/tmp/comfyui-noctq-62607250/user-before/`; ComfyUI also retained
the pre-migration SQLite database at `user/comfyui.db.bkp`. Restore the matching
backend, runtime and database together if rollback is necessary. The added
memory limits are tracked in
[noctq-memory.conf](../services/comfyui/noctq-memory.conf).

## DNS + SSL setup (one-time, after DNS propagation)

1. Add DNS A record: `comfyui.beachlab.org` → `85.49.212.28`
2. Wait for propagation, then run:

```bash
sudo /opt/comfyui/finish-ssl.sh
```

## Troubleshooting

**CUDA out of memory:** Other GPU services (Whisper, TTS) share the 8GB VRAM.  
Stop them before running heavy models:

```bash
sudo systemctl stop whisper-web qwen3-tts
# ... run ComfyUI generation ...
sudo systemctl start whisper-web qwen3-tts
```

**No models available:** Download a checkpoint and place in `models/checkpoints/`.  
Free options: [SDXL Turbo](https://huggingface.co/stabilityai/sdxl-turbo), [SD 1.5](https://huggingface.co/stable-diffusion-v1-5/stable-diffusion-v1-5).

**Port conflict on 8188:** `ss -tlnp | grep 8188`
