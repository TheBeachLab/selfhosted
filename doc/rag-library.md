# High-Precision eBook RAG (SFTP Inbox)

**Author:** Mr. Watson 🦄
**Date:** 2026-02-08

<!-- vim-markdown-toc GFM -->

- [Goal](#goal)
- [Quick operations](#quick-operations)
- [Ingest folders (SFTP)](#ingest-folders-sftp)
- [Supported formats](#supported-formats)
- [Pipeline service](#pipeline-service)
- [Precision setup (high)](#precision-setup-high)
- [Important GPU note for this host (GTX 1060 3GB)](#important-gpu-note-for-this-host-gtx-1060-3gb)
- [Environment config](#environment-config)
- [Operations](#operations)
- [Current status snapshot (2026-02-08)](#current-status-snapshot-2026-02-08)

<!-- vim-markdown-toc -->

## Goal

Run a local high-precision RAG pipeline where documents are dropped via SFTP and indexed automatically.

## Quick operations

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

## Current status snapshot (2026-02-08)

- service: active
- indexed files: 2
- failed files: 0
- inbox watcher: active

(Use SQL command above for live numbers.)
