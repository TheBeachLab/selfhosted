# ComfyUI

> Author: Watson

ComfyUI node-based Stable Diffusion GUI, served at `https://comfyui.beachlab.org` with basic auth.

## Stack

- **Service:** `comfyui.service` — port `8188` (127.0.0.1 only)
- **Frontend:** ComfyUI frontend v1.39.14 (bundled via pip, auto-updated)
- **Proxy:** Nginx → `comfyui.beachlab.org` with basic auth + HTTPS
- **GPU:** RTX 2070 Super 8GB, CUDA 12.4, PyTorch 2.6.0
- **Auth:** `/etc/nginx/.htpasswd-comfyui` (user: `fran`)

## Install paths

| Path | Purpose |
|---|---|
| `/opt/comfyui/` | App root |
| `/opt/comfyui/.venv/` | Python venv |
| `/opt/comfyui/models/` | Models (checkpoints, loras, VAE, etc.) |
| `/opt/comfyui/output/` | Generated images |
| `/opt/comfyui/input/` | Input images |
| `/opt/comfyui/custom_nodes/` | Extensions |

## Service

```bash
sudo systemctl status comfyui
sudo systemctl restart comfyui
journalctl -u comfyui -f
```

## Nginx

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

Drop checkpoint files into `/opt/comfyui/models/checkpoints/`.  
Refresh model list in ComfyUI UI: Manager → Refresh.

## Custom nodes (ComfyUI Manager)

Install ComfyUI Manager for easy node/extension management:

```bash
cd /opt/comfyui/custom_nodes
git clone https://github.com/Comfy-Org/ComfyUI-Manager.git
sudo systemctl restart comfyui
```

## Update ComfyUI

```bash
cd /opt/comfyui
git pull
.venv/bin/pip install -r requirements.txt
sudo systemctl restart comfyui
```

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
