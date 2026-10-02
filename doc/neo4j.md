# Neo4j

**Author:** Fran

<!-- vim-markdown-toc GFM -->

- [Install](#install)
- [Open Browser](#open-browser)
- [Query the graph](#query-the-graph)
- [Corrections and backups](#corrections-and-backups)

<!-- vim-markdown-toc -->

Neo4j stores nodes, properties and relationships.
[Browser](https://neo4j.com/docs/browser/) comes with Community and lets me
draw query results and run Cypher.

Community has [one standard database per instance](https://neo4j.com/docs/operations-manual/current/database-administration/),
apart from the system database. Use a separate container and data folder for
each project.

The NUC setup below is WIP. It uses Neo4j 5.26, which
[Graphiti supports](https://github.com/getzep/graphiti#installation).

## Install

As `pink` on the NUC, create the folders and a password:

```bash
umask 077
mkdir -p ~/knowledge-graphs/lab/neo4j
cd ~/knowledge-graphs/lab/neo4j
mkdir -p data logs backups
python3 - <<'PY'
import os
from pathlib import Path
from secrets import token_urlsafe

with Path(".env").open("x") as f:
    f.write(f"KG_UID={os.getuid()}\nKG_GID={os.getgid()}\n")
    f.write("NEO4J_AUTH=neo4j/" + token_urlsafe(32) + "\n")
PY
```

This creates `.env` only if it does not exist. Keep it private and out of Git.

Save this as `compose.yaml`:

```yaml
name: kg-lab
services:
  neo4j:
    image: neo4j:5.26-community@sha256:d9cfe82983d27f5a75b3aaae8f316d04f9a698a3b7f6103a508f7caf8362f255
    user: "${KG_UID:?Create .env}:${KG_GID:?Create .env}"
    restart: "no"
    mem_limit: 1400m
    cpus: 2
    environment:
      NEO4J_AUTH: "${NEO4J_AUTH:?Create .env}"
      NEO4J_server_memory_heap_initial__size: 256m
      NEO4J_server_memory_heap_max__size: 512m
      NEO4J_server_memory_pagecache_size: 256m
      NEO4J_dbms_usage__report_enabled: "false"
    ports:
      - "127.0.0.1:17474:7474"
      - "127.0.0.1:17687:7687"
    volumes:
      - ./data:/data
      - ./logs:/logs
      - ./backups:/backups
    healthcheck:
      test: ["CMD-SHELL", "wget -q -O /dev/null http://localhost:7474 || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 24
      start_period: 30s
```

The image is pinned. Data, logs and backups stay in these
[folders](https://neo4j.com/docs/operations-manual/current/docker/mounting-volumes/).
Start with the memory limit above and adjust it after using the lab.

```bash
sudo docker compose config --quiet
sudo docker compose up -d neo4j
sudo docker compose ps
sudo docker compose logs --tail 50 neo4j
```

Use `config --quiet` so the password does not appear in the output.
Stop it with `sudo docker compose stop neo4j` when finished.

Changing the password in `.env` only affects a new database. It does not
change the password of an existing one. Keep `data/` when troubleshooting.

## Open Browser

On the Mac, make sure these local ports are free. The Strategy pilot also
uses them; stop that pilot with its own tool or choose different local ports.

```bash
ssh -N -o ExitOnForwardFailure=yes \
  -L 127.0.0.1:17474:127.0.0.1:17474 \
  -L 127.0.0.1:17687:127.0.0.1:17687 pink-sudo
```

Open `http://127.0.0.1:17474/browser/`. Connect to
`bolt://127.0.0.1:17687` with user `neo4j` and the password from `.env`.

## Query the graph

Begin with a simple query:

```cypher
RETURN 1 AS ok;
SHOW INDEXES;
MATCH (n) RETURN labels(n) AS labels, count(*) AS total;
MATCH p=(a)-[r]->(b) RETURN p LIMIT 50;
```

For Graphiti, filter the project on both nodes and the relationship:

```cypher
:param project => 'lab'
MATCH p=(a:Entity)-[r:RELATES_TO]->(b:Entity)
WHERE a.group_id = $project AND b.group_id = $project AND r.group_id = $project
RETURN p LIMIT 50;
```

`group_id` is a query filter. Separate credentials and instances are what
keep projects with different access permissions apart.

## Corrections and backups

For generated data, correct the source or add a
[Graphiti correction](graphiti.md#fix-a-fact). Editing the extracted
relationship by hand can get overwritten when the graph is rebuilt.

For manually maintained data, select the exact ID, inspect it, make the
change in a transaction and query it again. Keep it separate from the
indexer's labels.

Community uses an [offline dump](https://neo4j.com/docs/operations-manual/current/docker/dump-load/).
Stop ingestion and any other writers first. Move a previous
`backups/neo4j.dump` to a dated backup before making another:

```bash
sudo docker compose stop neo4j
sudo docker compose run --rm --no-deps neo4j \
  neo4j-admin database dump neo4j --to-path=/backups
sha256sum backups/neo4j.dump
sudo docker compose up -d neo4j
```

If the dump fails, keep the data and read the error before continuing.
Copy the dump, `.env`, Compose file and Graphiti's original episodes to
private storage outside the NUC.

Try `neo4j-admin database load` in another instance with a new data
folder and different ports. Run a query there before trusting the backup.
