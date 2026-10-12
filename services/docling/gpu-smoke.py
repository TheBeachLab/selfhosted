#!/usr/bin/env python3
"""Measure a CUDA-only Docling conversion in an operator-created temporary venv.

Never installs packages, starts a service, or opens a Msgvault archive. Run
--download-only first to keep downloads outside conversion timings.
"""

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import resource
import threading
import time


def memory():
    values = {}
    for line in Path('/proc/self/status').read_text().splitlines():
        if line.startswith(('VmRSS:', 'VmHWM:')):
            key, value = line.split(':', 1)
            values[key] = int(value.split()[0]) * 1024
    return values


def available_memory():
    for line in Path('/proc/meminfo').read_text().splitlines():
        if line.startswith('MemAvailable:'):
            return int(line.split()[1]) * 1024
    raise RuntimeError('Cannot read available host memory')


def model_devices(converter, torch):
    """Inspect loaded model parameters, without performing extra inference."""
    found = {}
    seen = set()

    def visit(value, path, depth):
        if depth > 9 or id(value) in seen:
            return
        seen.add(id(value))
        if isinstance(value, torch.nn.Module):
            devices = sorted({str(p.device) for p in value.parameters()})
            if devices:
                found[path] = devices
            return
        if isinstance(value, dict):
            for i, child in enumerate(value.values()):
                visit(child, f'{path}[{i}]', depth + 1)
        elif isinstance(value, (list, tuple)):
            for i, child in enumerate(value):
                visit(child, f'{path}[{i}]', depth + 1)
        elif type(value).__module__.startswith(('docling', 'easyocr')):
            for key, child in vars(value).items():
                if not key.startswith('__'):
                    visit(child, f'{path}.{key}', depth + 1)

    visit(converter.initialized_pipelines, 'pipelines', 0)
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--models', type=Path, required=True)
    parser.add_argument('--input', type=Path)
    parser.add_argument('--expected', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--runs', type=int, default=3)
    parser.add_argument('--download-only', action='store_true')
    args = parser.parse_args()
    if not args.download_only and not all([args.input, args.expected, args.output]):
        parser.error('--input, --expected and --output are required for conversion')
    if not 1 <= args.runs <= 5:
        parser.error('--runs must be between 1 and 5')

    import_started = time.perf_counter()
    import torch
    from docling.datamodel.accelerator_options import AcceleratorOptions
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import EasyOcrOptions, PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    imports_seconds = time.perf_counter() - import_started
    if args.download_only:
        from docling.utils.model_downloader import download_models

        started = time.perf_counter()
        download_models(
            output_dir=args.models,
            with_layout=True,
            with_tableformer=True,
            with_code_formula=False,
            with_picture_classifier=False,
            with_rapidocr=False,
            with_easyocr=True,
            easyocr_languages=['en', 'es', 'de'],
        )
        print(json.dumps({'prefetch_seconds': time.perf_counter() - started}), flush=True)
        return

    if not torch.cuda.is_available():
        raise RuntimeError('CUDA is unavailable; refusing a silent CPU fallback')
    if available_memory() < 2 * 1024**3:
        raise RuntimeError('Less than 2 GiB of host memory available before conversion')
    torch.set_num_threads(2)
    torch.set_num_interop_threads(2)
    device = torch.cuda.get_device_name(0)
    torch.cuda.synchronize()

    import pynvml

    pynvml.nvmlInit()
    handle = pynvml.nvmlDeviceGetHandleByIndex(0)
    foreign = pynvml.nvmlDeviceGetComputeRunningProcesses(handle)
    if any(p.pid != os.getpid() for p in foreign):
        raise RuntimeError('Another CUDA process is active; refusing concurrent GPU work')
    baseline_gpu = pynvml.nvmlDeviceGetMemoryInfo(handle).used

    options = PdfPipelineOptions(
        artifacts_path=args.models,
        accelerator_options=AcceleratorOptions(device='cuda', num_threads=2),
        do_ocr=True,
        do_table_structure=True,
        ocr_options=EasyOcrOptions(lang=['en', 'es', 'de'], download_enabled=False),
        generate_page_images=False,
        generate_picture_images=False,
    )
    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )
    expected = json.loads(args.expected.read_text())
    args.output.mkdir(mode=0o700, parents=True, exist_ok=True)
    report = {
        'input_sha256': hashlib.sha256(args.input.read_bytes()).hexdigest(),
        'input_bytes': args.input.stat().st_size,
        'imports_seconds': imports_seconds,
        'device': device,
        'torch_version': torch.__version__,
        'cuda_version': torch.version.cuda,
        'versions': {name: importlib.metadata.version(name) for name in
                     ['docling', 'docling-core', 'docling-ibm-models', 'easyocr']},
        'num_cpu_threads': 2,
        'ocr_languages': ['en', 'es', 'de'],
        'gpu_baseline_bytes': baseline_gpu,
        'baseline_rss_bytes': memory()['VmRSS'],
        'runs': [],
    }

    for run in range(args.runs):
        samples = []
        stop = threading.Event()

        def monitor():
            while not stop.is_set():
                samples.append({
                    'rss': memory()['VmRSS'],
                    'available': available_memory(),
                    'gpu_bytes': pynvml.nvmlDeviceGetMemoryInfo(handle).used,
                    'gpu_utilization': pynvml.nvmlDeviceGetUtilizationRates(handle).gpu,
                    'gpu_temperature': pynvml.nvmlDeviceGetTemperature(handle, 0),
                })
                stop.wait(0.1)

        monitor_thread = threading.Thread(target=monitor, daemon=True)
        monitor_thread.start()
        torch.cuda.reset_peak_memory_stats()
        started = time.perf_counter()
        try:
            result = converter.convert(args.input, raises_on_error=True)
            torch.cuda.synchronize()
            elapsed = time.perf_counter() - started
        except Exception as exc:
            report['status'] = 'failed'
            report['failure'] = {
                'run': run + 1,
                'seconds': time.perf_counter() - started,
                'error_tail': str(exc).splitlines()[-8:],
                'rss_peak_sampled_bytes': max((s['rss'] for s in samples), default=0),
                'gpu_peak_total_bytes': max((s['gpu_bytes'] for s in samples), default=0),
            }
            (args.output / 'metrics.json').write_text(json.dumps(report, indent=2) + '\n')
            raise
        finally:
            stop.set()
            monitor_thread.join()

        markdown = result.document.export_to_markdown()
        (args.output / f'conversion-{run + 1}.md').write_text(markdown)
        compact = re.sub(r'[^a-z0-9]', '', markdown.lower())
        checks = {
            token: re.sub(r'[^a-z0-9]', '', token.lower()) in compact
            for token in expected['native'] + expected['ocr']
        }
        pages = len(result.document.pages)
        tables = len(result.document.tables)
        devices = model_devices(converter, torch)
        cuda_models = {k: v for k, v in devices.items()
                       if any(d.startswith('cuda') for d in v)}
        values = {
            'run': run + 1,
            'cold_models': run == 0,
            'seconds': elapsed,
            'pages': pages,
            'tables': tables,
            'checks': checks,
            'loaded_model_devices': devices,
            'rss_peak_sampled_bytes': max(s['rss'] for s in samples),
            'rss_after_bytes': memory()['VmRSS'],
            'process_rss_high_water_bytes': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
            'host_memory_available_min_bytes': min(s['available'] for s in samples),
            'gpu_peak_total_bytes': max(s['gpu_bytes'] for s in samples),
            'gpu_peak_utilization_percent': max(s['gpu_utilization'] for s in samples),
            'gpu_peak_temperature_c': max(s['gpu_temperature'] for s in samples),
            'torch_gpu_peak_allocated_bytes': torch.cuda.max_memory_allocated(),
            'torch_gpu_peak_reserved_bytes': torch.cuda.max_memory_reserved(),
        }
        report['runs'].append(values)
        (args.output / 'metrics.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(values), flush=True)
        if not (all(checks.values()) and pages == expected['pages'] and tables >= 2):
            raise RuntimeError('Synthetic text/OCR/table checks did not pass')
        if not cuda_models or not values['torch_gpu_peak_allocated_bytes']:
            raise RuntimeError('No loaded model parameters found on CUDA')
        if min(s['available'] for s in samples) < 1024**3:
            raise RuntimeError('Host memory headroom dropped below 1 GiB; stopping repetitions')

    report['status'] = 'passed'
    (args.output / 'metrics.json').write_text(json.dumps(report, indent=2) + '\n')
    pynvml.nvmlShutdown()


if __name__ == '__main__':
    main()
