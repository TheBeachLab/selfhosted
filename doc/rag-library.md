# eBook RAG (SFTP Inbox)

<!-- vim-markdown-toc GFM -->

- [Quick operations](#quick-operations)
- [Ingest folders (SFTP)](#ingest-folders-sftp)
- [Supported formats](#supported-formats)
- [Pipeline service](#pipeline-service)
- [Precision setup (high)](#precision-setup-high)
- [GPU](#gpu-2026-02-18)
- [Environment config](#environment-config)
- [Operations](#operations)

<!-- vim-markdown-toc -->

Upload documents through SFTP to index them in the local RAG library.

## Quick operations

RAG does not start at boot. Start and stop it with `gpu-service`:

```bash
gpu-service status                    # Check if running
gpu-service start rag                 # Start when needed (e.g., before uploading docs)
gpu-service stop rag                  # Stop when inbox is empty
```

See [GPU Service Management](gpu-services.md) for details.

Status check (when running):

```bash
systemctl status rag-library-ingest
journalctl -u rag-library-ingest -n 120 --no-pager
ls -lah /home/sftpuser/library_inbox /home/sftpuser/library_done /home/sftpuser/library_failed
```

## Ingest folders (SFTP)

Upload new files to:

- `/home/sftpuser/library_inbox`

Pipeline moves files to:

- `/home/sftpuser/library_done` (indexed OK)
- `/home/sftpuser/library_failed` (parse/index errors)

## Supported formats

- `.pdf`
- `.epub`
- `.txt`
- `.md`

## Pipeline service

Systemd service:

- `rag-library-ingest.service`

Script:

- `/opt/rag-library/rag_pipeline.py`

Virtual env:

- `/opt/rag-library/.venv`

Data:

- Chroma vectors: `/opt/rag-library/data/chroma`
- File registry (SQLite): `/opt/rag-library/data/registry.db`

## Precision setup (high)

- Embeddings model: `intfloat/multilingual-e5-base`
- Semantic chunking with overlap
- Metadata per chunk (source hash, title, chunk index)
- Cross-encoder reranker: `cross-encoder/ms-marco-MiniLM-L-6-v2`
- Dedup by SHA-256
- Incremental ingest (new/changed files only)

## GPU (2026-02-18)

Upgraded eGPU to **RTX 2070 Super 8GB** (`sm_75`). All inference now runs on CUDA:

- Embedding model (`multilingual-e5-base`): `device='cuda'` — ingest and query
- Cross-encoder reranker (`ms-marco-MiniLM-L-6-v2`): `device='cuda'`

No CPU inference paths remain in `rag_pipeline.py`.

## Environment config

`/etc/rag-library.env`

```bash
RAG_EMBED_MODEL=intfloat/multilingual-e5-base
RAG_RERANK_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
```

## Operations

```bash
# Service status
systemctl status rag-library-ingest

# Logs
journalctl -u rag-library-ingest -n 200 --no-pager

# Check indexed/failed counts
sqlite3 /opt/rag-library/data/registry.db "select status,count(*) from files group by status;"

# One-shot manual query
/opt/rag-library/.venv/bin/python /opt/rag-library/rag_pipeline.py query "tu pregunta"
```
