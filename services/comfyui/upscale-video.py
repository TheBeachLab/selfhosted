#!/usr/bin/env python3
"""Run the NUC SeedVR2 profile in bounded chunks and restore the source audio."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path, help="New MP4 file; never overwritten")
    parser.add_argument("--comfyui", type=Path, default=Path("/opt/comfyui"))
    args = parser.parse_args()
    source = args.input.resolve(strict=True)
    output = args.output.resolve()
    if output.exists():
        parser.error(f"Output already exists: {output}")
    if output.suffix.lower() != ".mp4":
        parser.error("Output must be an MP4 file")
    output.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(output.parent).free < 5 * 1024**3:
        parser.error("Keep at least 5 GiB free before starting a video job")
    metadata = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_streams", "-of", "json", str(source)
    ]))
    video = next(s for s in metadata["streams"] if s["codec_type"] == "video")
    if video["r_frame_rate"] != video["avg_frame_rate"]:
        parser.error("The upstream CLI uses constant FPS; normalize this variable-FPS source first")
    audio = [s for s in metadata["streams"] if s["codec_type"] == "audio"]
    copy_audio = all(s["codec_name"] in ("aac", "mp3", "alac") for s in audio)
    node = args.comfyui / "custom_nodes/ComfyUI-SeedVR2_VideoUpscaler"
    env = os.environ.copy()
    cuda_lib = args.comfyui / ".venv/lib/python3.10/site-packages/nvidia/cu13/lib"
    env["LD_LIBRARY_PATH"] = str(cuda_lib) + ":" + env.get("LD_LIBRARY_PATH", "")
    with tempfile.TemporaryDirectory(prefix="seedvr2-", dir=output.parent) as tmp:
        silent = Path(tmp) / "upscaled.mp4"
        final = Path(tmp) / "final.mp4"
        subprocess.run([
            str(args.comfyui / ".venv/bin/python"), str(node / "inference_cli.py"),
            str(source), "--output", str(silent), "--model_dir",
            str(args.comfyui / "models/SEEDVR2"),
            "--dit_model", "seedvr2_ema_3b-Q4_K_M.gguf", "--resolution", "1080",
            "--max_resolution", "0", "--batch_size", "5", "--uniform_batch_size",
            "--chunk_size", "5", "--temporal_overlap", "1", "--blocks_to_swap", "32",
            "--swap_io_components", "--dit_offload_device", "cpu",
            "--vae_offload_device", "cpu", "--tensor_offload_device", "cpu",
            "--vae_encode_tiled", "--vae_encode_tile_size", "256",
            "--vae_encode_tile_overlap", "64", "--vae_decode_tiled",
            "--vae_decode_tile_size", "256", "--vae_decode_tile_overlap", "64",
            "--attention_mode", "sdpa", "--video_backend", "ffmpeg",
        ], cwd=node, env=env, check=True)
        command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-n",
                   "-i", str(silent), "-i", str(source), "-map", "0:v:0",
                   "-map", "1:a?", "-map_metadata", "1", "-c:v", "copy",
                   "-c:a", "copy" if copy_audio else "aac"]
        if not copy_audio:
            command += ["-b:a", "192k"]
        command += ["-movflags", "+faststart", str(final)]
        subprocess.run(command, check=True)
        # Publish without replacing a file another job may have created meanwhile.
        os.link(final, output)
    print(output)


if __name__ == "__main__":
    main()
