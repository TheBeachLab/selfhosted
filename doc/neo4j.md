# Neo4j Community and Browser

**Author:** Fran
**Checked:** 2026-10-02
**NUC:** instalación pendiente.

Neo4j guarda nodos, propiedades y relaciones. Browser viene con Community y
permite visualizar resultados y ejecutar lecturas/escrituras Cypher.
[Browser](https://neo4j.com/docs/browser/), consultado el 2026-10-02.

Community admite una base estándar por instancia, además de `system`.
Para proyectos aislados, usar contenedores y datos distintos; arrancar el
proyecto activo. Un `group_id` no constituye una separación de permisos entre
usuarios. [Administración de bases](https://neo4j.com/docs/operations-manual/current/database-administration/).

## Laboratorio propuesto

Usar Neo4j 5.26 Community para la compatibilidad declarada por
[Graphiti](https://github.com/getzep/graphiti#installation).
El digest de `5.26-community` se consultó en el
[registro oficial Docker](https://hub.docker.com/v2/namespaces/library/repositories/neo4j/tags/5.26-community)
el 2026-10-02. La configuración siguiente está fijada a ese digest; el arranque
en este NUC todavía no se ha validado.

Como `pink` en el NUC, crear un laboratorio nuevo. La creación exclusiva de
`.env` evita sobrescribir credenciales existentes:

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

Guardar como `compose.yaml` en ese directorio:

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

La plantilla sigue el aislamiento y los límites del piloto local
`project-knowledge/compose.yaml`; `user` corresponde al dueño de los montajes.
Los límites son iniciales, pendientes de medir en el NUC. Fuentes de las opciones:
[Docker](https://neo4j.com/docs/operations-manual/current/docker/introduction/)
y [volúmenes](https://neo4j.com/docs/operations-manual/current/docker/mounting-volumes/).

```bash
sudo docker compose config --quiet
sudo docker compose up -d neo4j
sudo docker compose ps
sudo docker compose logs --tail 50 neo4j
sudo docker compose stop neo4j
```

Usar `config --quiet`: la salida completa puede mostrar el secreto. Conservar
`.env` en modo 0600 y el directorio privado. La contraseña inicial solo configura
una base nueva; editar `.env` no cambia la contraseña de una base existente.
Parar conserva los montajes; no usar `down -v` ni borrar `data` para corregir
un fallo de arranque.

## Acceso desde el Mac

Después de arrancar, y comprobando que los puertos locales estén libres:

```bash
ssh -N -o ExitOnForwardFailure=yes \
  -L 127.0.0.1:17474:127.0.0.1:17474 \
  -L 127.0.0.1:17687:127.0.0.1:17687 pink-sudo
```

Browser: `http://127.0.0.1:17474/browser/`. Conexión: `bolt://127.0.0.1:17687`,
usuario `neo4j` y contraseña privada del laboratorio. Estos puertos también
se usan en el piloto Strategy del Mac: pararlo mediante su herramienta propia
o elegir otros puertos **locales** y ajustar la conexión Browser.

El healthcheck solo comprueba HTTP. Completar la aceptación con una consulta
autenticada:

```cypher
RETURN 1 AS ok;
SHOW INDEXES;
MATCH (n) RETURN labels(n) AS etiquetas, count(*) AS total;
MATCH p=(a)-[r]->(b) RETURN p LIMIT 50;
```

En Graphiti, filtrar el proyecto de prueba en ambos extremos y en la relación:

```cypher
:param proyecto => 'lab'
MATCH p=(a:Entity)-[r:RELATES_TO]->(b:Entity)
WHERE a.group_id = $proyecto AND b.group_id = $proyecto AND r.group_id = $proyecto
RETURN p LIMIT 50;
```

## Correcciones y copias

En datos generados, corregir la fuente o ingerir un episodio de corrección según
[Graphiti](graphiti.md). Una edición directa puede desaparecer en la siguiente
reconstrucción y dejar una procedencia incoherente. Para datos manuales, separar
etiquetas/propiedad de dueño, seleccionar un ID único, revisar el antes y aplicar
la escritura en una transacción con recibo y consulta posterior.

Para una copia de Community, detener primero ingestas y clientes escritores.
El dump es offline. Desde el directorio del laboratorio:

```bash
sudo docker compose stop neo4j
sudo docker compose run --rm --no-deps neo4j \
  neo4j-admin database dump neo4j --to-path=/backups
sha256sum backups/neo4j.dump
sudo docker compose up -d neo4j
```

El archivo `backups/neo4j.dump` debe estar ausente antes del dump: archivar una
copia anterior con su fecha sin sobrescribirla. Copiar el dump, `.env`, Compose,
episodios y recibos a una copia privada externa al NUC. Si el dump falla,
conservar datos y diagnóstico; comprobar el resultado antes de seguir.

Probar `neo4j-admin database load` con el mismo digest, otro directorio `/data`
y puertos diferentes, sin tocar la instancia original. Comprobar una consulta
autenticada y la procedencia de los datos restaurados.
[Dump/load Docker](https://neo4j.com/docs/operations-manual/current/docker/dump-load/),
consultado el 2026-10-02. Esta guía no acredita una copia ni una restauración
realizadas.

## Verificación de esta guía

La plantilla se validó el 2026-10-02 con `docker compose config --quiet` en el
NUC, pasando la configuración por stdin y credenciales sintéticas. No se creó
un contenedor, un montaje ni una base. La aceptación pendiente incluye arranque,
consulta autenticada, límites efectivos, persistencia y dump/restauración.
