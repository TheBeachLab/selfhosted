#!/usr/bin/env python3
"""Small authenticated URL downloader, intended to run behind Nginx."""

from __future__ import annotations

import concurrent.futures
import ipaddress
import json
import mimetypes
import os
import re
import secrets
import shutil
import socket
import socketserver
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from email.message import Message
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any


APP_NAME = "Drop"
SOCKET_PATH = Path(os.environ.get("DROP_SOCKET", "/run/url-drop/url-drop.sock"))
FILES_DIR = Path(os.environ.get("DROP_DIR", "/var/lib/url-drop/files"))
MAX_BYTES = int(os.environ.get("DROP_MAX_BYTES", str(20 * 1024**3)))
RESERVE_BYTES = int(os.environ.get("DROP_RESERVE_BYTES", str(5 * 1024**3)))
MAX_REDIRECTS = 5
MAX_BODY = 16 * 1024
CHUNK_SIZE = 1024 * 1024
FILE_RE = re.compile(r"^[A-Za-z0-9_-]{16,32}(?:\.[A-Za-z0-9]{1,10})?$")

JOBS: dict[str, dict[str, Any]] = {}
LOCK = threading.RLock()
EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=2, thread_name_prefix="drop"
)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


OPENER = urllib.request.build_opener(NoRedirect)


def now() -> int:
    return int(time.time())


def format_bytes(value: int | None) -> str:
    if value is None:
        return "—"
    size = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} TB"


def public_url(url: str) -> tuple[str, str]:
    """Validate a URL and resolve every address before urllib connects."""
    url = url.strip()
    if not url or len(url) > 4096:
        raise ValueError("URL vacía o demasiado larga")

    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Solo se permiten URLs HTTP o HTTPS")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("La URL no puede incluir credenciales")
    if not parsed.hostname:
        raise ValueError("La URL no contiene un host válido")

    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise ValueError("Puerto inválido") from exc

    if port not in {80, 443}:
        raise ValueError("Solo se permiten los puertos 80 y 443")

    try:
        addresses = {
            item[4][0]
            for item in socket.getaddrinfo(
                parsed.hostname, port, type=socket.SOCK_STREAM
            )
        }
    except socket.gaierror as exc:
        raise ValueError("No se pudo resolver el host") from exc

    if not addresses:
        raise ValueError("El host no tiene direcciones")

    for address in addresses:
        try:
            if not ipaddress.ip_address(address).is_global:
                raise ValueError("No se permiten destinos privados o reservados")
        except ValueError as exc:
            if str(exc) == "No se permiten destinos privados o reservados":
                raise
            raise ValueError("El host resolvió a una dirección inválida") from exc

    host = parsed.hostname.lower().rstrip(".")
    return urllib.parse.urlunsplit(parsed), host


def extension_for(url: str, headers: Any) -> str:
    names: list[str] = []
    disposition = headers.get("Content-Disposition", "")
    if disposition:
        message = Message()
        message["Content-Disposition"] = disposition
        filename = message.get_filename()
        if filename:
            names.append(Path(filename).name)

    path_name = Path(urllib.parse.unquote(urllib.parse.urlsplit(url).path)).name
    if path_name:
        names.append(path_name)

    for name in names:
        suffix = Path(name).suffix
        if re.fullmatch(r"\.[A-Za-z0-9]{1,10}", suffix):
            return suffix

    content_type = headers.get_content_type() if hasattr(headers, "get_content_type") else ""
    suffix = mimetypes.guess_extension(content_type or "", strict=False) or ""
    if re.fullmatch(r"\.[A-Za-z0-9]{1,10}", suffix):
        return suffix
    return ".bin"


def set_job(job_id: str, **changes: Any) -> None:
    with LOCK:
        job = JOBS.get(job_id)
        if job is not None:
            job.update(changes)
            job["updated"] = now()


def safe_error(exc: Exception) -> str:
    if isinstance(exc, ValueError):
        return str(exc)
    if isinstance(exc, urllib.error.HTTPError):
        return f"El servidor remoto respondió HTTP {exc.code}"
    if isinstance(exc, urllib.error.URLError):
        return f"No se pudo conectar al servidor remoto: {exc.reason}"
    if isinstance(exc, TimeoutError):
        return "El servidor remoto agotó el tiempo de espera"
    return "La descarga falló"


def open_remote(start_url: str):
    current = start_url
    host = ""
    for redirect_count in range(MAX_REDIRECTS + 1):
        current, host = public_url(current)
        request = urllib.request.Request(
            current,
            headers={
                "Accept": "*/*",
                "Accept-Encoding": "identity",
                "User-Agent": "BeachLab-Drop/1.0",
            },
            method="GET",
        )
        try:
            response = OPENER.open(request, timeout=30)
        except urllib.error.HTTPError as exc:
            if exc.code in {301, 302, 303, 307, 308}:
                location = exc.headers.get("Location")
                exc.close()
                if not location:
                    raise ValueError("Redirección remota sin destino")
                if redirect_count >= MAX_REDIRECTS:
                    raise ValueError("Demasiadas redirecciones")
                current = urllib.parse.urljoin(current, location)
                continue
            raise
        return response, current, host
    raise ValueError("Demasiadas redirecciones")


def download(job_id: str, source_url: str) -> None:
    temp_path = FILES_DIR / f".{job_id}.part"
    response = None
    try:
        set_job(job_id, status="connecting")
        response, final_url, host = open_remote(source_url)
        total_header = response.headers.get("Content-Length")
        total = int(total_header) if total_header and total_header.isdigit() else None
        if total is not None and total > MAX_BYTES:
            raise ValueError(f"El archivo supera el límite de {format_bytes(MAX_BYTES)}")

        free = shutil.disk_usage(FILES_DIR).free
        if total is not None and total > max(0, free - RESERVE_BYTES):
            raise ValueError("No hay espacio suficiente en el servidor")

        extension = extension_for(final_url, response.headers)
        filename = f"{secrets.token_urlsafe(15)}{extension}"
        final_path = FILES_DIR / filename
        downloaded = 0
        set_job(
            job_id,
            status="downloading",
            host=host,
            total=total,
            name=filename,
        )

        with temp_path.open("xb") as target:
            while True:
                chunk = response.read(CHUNK_SIZE)
                if not chunk:
                    break
                downloaded += len(chunk)
                if downloaded > MAX_BYTES:
                    raise ValueError(
                        f"El archivo supera el límite de {format_bytes(MAX_BYTES)}"
                    )
                if downloaded % (16 * CHUNK_SIZE) < CHUNK_SIZE:
                    if shutil.disk_usage(FILES_DIR).free < RESERVE_BYTES:
                        raise ValueError("La descarga se detuvo para reservar espacio")
                target.write(chunk)
                set_job(job_id, bytes=downloaded)
            target.flush()
            os.fsync(target.fileno())

        if total is not None and downloaded != total:
            raise ValueError("La descarga terminó incompleta")

        temp_path.replace(final_path)
        set_job(
            job_id,
            status="complete",
            bytes=downloaded,
            total=downloaded,
            name=filename,
            host=host,
        )
    except Exception as exc:
        set_job(job_id, status="error", error=safe_error(exc))
    finally:
        if response is not None:
            response.close()
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass


def serialized_jobs() -> list[dict[str, Any]]:
    with LOCK:
        items = [dict(job) for job in JOBS.values()]
    items.sort(key=lambda item: item["created"], reverse=True)
    for item in items:
        item.pop("url", None)
    return items


def bootstrap_files() -> None:
    FILES_DIR.mkdir(parents=True, exist_ok=True)
    for path in FILES_DIR.iterdir():
        if path.is_file() and FILE_RE.fullmatch(path.name):
            job_id = f"file-{path.name}"
            stat = path.stat()
            JOBS[job_id] = {
                "id": job_id,
                "status": "complete",
                "created": int(stat.st_mtime),
                "updated": int(stat.st_mtime),
                "bytes": stat.st_size,
                "total": stat.st_size,
                "name": path.name,
                "host": "recuperado",
                "error": None,
            }


HTML = r"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Drop</title>
  <style>
    :root{color-scheme:dark;--bg:#0a0c10;--panel:#12161d;--line:#29313d;--text:#edf2f7;--muted:#929dad;--accent:#77e0ad;--danger:#ff7f8a}
    *{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 25% 0,#15231f 0,transparent 34%),var(--bg);color:var(--text);font:15px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace}
    main{width:min(760px,calc(100% - 32px));margin:9vh auto}h1{margin:0 0 8px;font-size:clamp(32px,7vw,54px);letter-spacing:-.06em}p{color:var(--muted)}
    form,.job{background:color-mix(in srgb,var(--panel) 92%,transparent);border:1px solid var(--line);border-radius:16px;padding:16px;box-shadow:0 18px 60px #0006}
    form{display:flex;gap:10px;margin:28px 0}input{min-width:0;flex:1;background:#090c10;border:1px solid #354152;border-radius:10px;color:var(--text);padding:13px;font:inherit;outline:none}input:focus{border-color:var(--accent)}
    button,.link{border:0;border-radius:10px;background:var(--accent);color:#07120d;padding:12px 15px;font:700 14px inherit;cursor:pointer;text-decoration:none;display:inline-flex;align-items:center;justify-content:center}
    button:disabled{opacity:.5;cursor:wait}.jobs{display:grid;gap:12px}.job{padding:14px 16px}.row{display:flex;align-items:center;justify-content:space-between;gap:12px}.name{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:700}.meta{font-size:12px;color:var(--muted);margin-top:6px}.actions{display:flex;gap:8px;margin-top:12px}.actions button,.actions .link{padding:8px 11px;font-size:12px}.delete{background:#301a20;color:var(--danger);border:1px solid #6b2a35}
    progress{width:100%;height:7px;margin-top:12px;accent-color:var(--accent)}.error{color:var(--danger)}.empty{text-align:center;padding:32px;color:var(--muted)}
    @media(max-width:600px){form{flex-direction:column}.row{align-items:flex-start;flex-direction:column}}
  </style>
</head>
<body>
<main>
  <h1>Drop.</h1>
  <p>Pega una URL pública. El archivo se guarda con un nombre aleatorio y conserva su extensión.</p>
  <form id="form">
    <input id="url" type="url" placeholder="https://…" required autocomplete="off">
    <button id="submit">Descargar</button>
  </form>
  <section class="jobs" id="jobs"><div class="empty">Sin archivos.</div></section>
</main>
<script>
const $=s=>document.querySelector(s), jobs=$("#jobs"), form=$("#form"), submit=$("#submit");
const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const size=n=>{if(n==null)return "—";let i=0,u=["B","KB","MB","GB","TB"];while(n>=1024&&i<u.length-1){n/=1024;i++}return `${n.toFixed(i?1:0)} ${u[i]}`};
function draw(items){
  if(!items.length){jobs.innerHTML='<div class="empty">Sin archivos.</div>';return}
  jobs.innerHTML=items.map(j=>{
    const active=["queued","connecting","downloading"].includes(j.status);
    const pct=j.total?Math.min(100,j.bytes/j.total*100):null;
    const state={queued:"En cola",connecting:"Conectando",downloading:"Descargando",complete:"Listo",error:"Error"}[j.status]||j.status;
    const file=j.name?esc(j.name):"Preparando…";
    const href=j.name?`files/${encodeURIComponent(j.name)}`:"";
    return `<article class="job">
      <div class="row"><span class="name">${file}</span><span class="${j.status==="error"?"error":""}">${state}</span></div>
      <div class="meta">${esc(j.host||"")} · ${size(j.bytes)}${j.total&&active?` / ${size(j.total)}`:""}</div>
      ${j.error?`<div class="meta error">${esc(j.error)}</div>`:""}
      ${active?`<progress ${pct==null?"":`value="${pct}" max="100"`}></progress>`:""}
      ${j.status==="complete"?`<div class="actions"><a class="link" href="${href}">Descargar</a><button data-copy="${href}">Copiar enlace</button><button class="delete" data-delete="${esc(j.name)}">Borrar</button></div>`:""}
    </article>`
  }).join("");
}
async function refresh(){
  try{const r=await fetch("api/jobs",{cache:"no-store"});draw((await r.json()).jobs)}catch{}
}
form.addEventListener("submit",async e=>{
  e.preventDefault();submit.disabled=true;
  try{
    const r=await fetch("api/download",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({url:$("#url").value})});
    const data=await r.json();if(!r.ok)throw new Error(data.error||"No se pudo iniciar");
    $("#url").value="";await refresh();
  }catch(e){alert(e.message)}finally{submit.disabled=false}
});
jobs.addEventListener("click",async e=>{
  const del=e.target.dataset.delete, copy=e.target.dataset.copy;
  if(copy){await navigator.clipboard.writeText(new URL(copy,location.href).href);e.target.textContent="Copiado";setTimeout(()=>e.target.textContent="Copiar enlace",1200)}
  if(del&&confirm("¿Borrar este archivo?")){await fetch("api/delete",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name:del})});await refresh()}
});
refresh();setInterval(refresh,1500);
</script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    server_version = "Drop/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"{self.client_address[0] if self.client_address else 'unix'} {fmt % args}")

    def send_bytes(
        self,
        status: int,
        body: bytes,
        content_type: str,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if extra_headers:
            for key, value in extra_headers.items():
                self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_json(self, status: int, data: dict[str, Any]) -> None:
        self.send_bytes(
            status,
            json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode(),
            "application/json; charset=utf-8",
        )

    def read_json(self) -> dict[str, Any]:
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip()
        if content_type != "application/json":
            raise ValueError("Se requiere JSON")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("Tamaño de petición inválido") from exc
        if length < 2 or length > MAX_BODY:
            raise ValueError("Petición vacía o demasiado grande")
        try:
            payload = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError("JSON inválido") from exc
        if not isinstance(payload, dict):
            raise ValueError("JSON inválido")
        return payload

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_GET(self) -> None:
        path = urllib.parse.urlsplit(self.path).path
        if path == "/":
            self.send_bytes(
                200,
                HTML.encode(),
                "text/html; charset=utf-8",
                {
                    "Content-Security-Policy": (
                        "default-src 'self'; style-src 'unsafe-inline'; "
                        "script-src 'unsafe-inline'; object-src 'none'; base-uri 'none'"
                    )
                },
            )
            return
        if path == "/api/jobs":
            self.send_json(200, {"jobs": serialized_jobs()})
            return
        if path.startswith("/files/"):
            name = urllib.parse.unquote(path.removeprefix("/files/"))
            if not FILE_RE.fullmatch(name):
                self.send_json(404, {"error": "Archivo no encontrado"})
                return
            file_path = FILES_DIR / name
            if not file_path.is_file():
                self.send_json(404, {"error": "Archivo no encontrado"})
                return
            content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Disposition", f'attachment; filename="{name}"')
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Accel-Redirect", f"/drop-internal/{name}")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_json(404, {"error": "Ruta no encontrada"})

    def do_POST(self) -> None:
        path = urllib.parse.urlsplit(self.path).path
        try:
            payload = self.read_json()
            if path == "/api/download":
                source_url = payload.get("url")
                if not isinstance(source_url, str):
                    raise ValueError("Falta la URL")
                normalized, host = public_url(source_url)
                job_id = secrets.token_urlsafe(12)
                job = {
                    "id": job_id,
                    "url": normalized,
                    "status": "queued",
                    "created": now(),
                    "updated": now(),
                    "bytes": 0,
                    "total": None,
                    "name": None,
                    "host": host,
                    "error": None,
                }
                with LOCK:
                    JOBS[job_id] = job
                EXECUTOR.submit(download, job_id, normalized)
                self.send_json(202, {"id": job_id})
                return

            if path == "/api/delete":
                name = payload.get("name")
                if not isinstance(name, str) or not FILE_RE.fullmatch(name):
                    raise ValueError("Nombre de archivo inválido")
                file_path = FILES_DIR / name
                try:
                    file_path.unlink()
                except FileNotFoundError:
                    pass
                with LOCK:
                    for job_id in [
                        key for key, value in JOBS.items() if value.get("name") == name
                    ]:
                        JOBS.pop(job_id, None)
                self.send_json(200, {"deleted": True})
                return

            self.send_json(404, {"error": "Ruta no encontrada"})
        except ValueError as exc:
            self.send_json(400, {"error": str(exc)})


class ThreadingUnixHTTPServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    allow_reuse_address = True

    def server_bind(self) -> None:
        try:
            os.unlink(self.server_address)
        except FileNotFoundError:
            pass
        super().server_bind()
        os.chmod(self.server_address, 0o660)


def main() -> None:
    bootstrap_files()
    SOCKET_PATH.parent.mkdir(parents=True, exist_ok=True)
    with ThreadingUnixHTTPServer(str(SOCKET_PATH), Handler) as server:
        print(f"{APP_NAME} listening on {SOCKET_PATH}", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
