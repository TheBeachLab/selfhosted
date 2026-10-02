# Graphiti: temporal memory

**Author:** Fran
**Checked:** 2026-10-02
**NUC:** instalación e integración pendientes.

Graphiti transforma episodios de texto o datos estructurados en entidades y
relaciones con procedencia y fechas. Puede incorporar información nueva y
revisar la vigencia de relaciones anteriores. Es una biblioteca; el editor y
la aplicación de revisión se construyen alrededor de ella.
[Proyecto oficial](https://github.com/getzep/graphiti), consultado el 2026-10-02.

## Dependencias y proveedor del modelo

El upstream declara Python 3.10+ y Neo4j 5.26 como una de sus bases compatibles.
La propuesta usa Python 3.12 y [Neo4j Community](neo4j.md) aislado por proyecto.
`graphiti-core` publicado al consultar PyPI era `0.30.2`:
[metadatos de la versión](https://pypi.org/project/graphiti-core/0.30.2/).

En un laboratorio nuevo, con uv disponible como en [LangGraph](langgraph.md):

```bash
mkdir -p ~/knowledge-graphs/graphiti-lab
cd ~/knowledge-graphs/graphiti-lab
uv init --python 3.12
uv add 'graphiti-core==0.30.2'
GRAPHITI_TELEMETRY_ENABLED=false uv run python -c \
  'from importlib.metadata import version; print(version("graphiti-core"))'
```

Instalar el paquete no realiza ingesta. Antes de crear el cliente, decidir y
configurar explícitamente tres piezas: LLM para extracción, embeddings para
recuperación y ranking de resultados. Graphiti usa OpenAI por defecto; un modelo
local u otro proveedor necesita sus clientes correspondientes y una prueba de
salida estructurada. [Requisitos y proveedores](https://github.com/getzep/graphiti#installation).

El piloto del Mac contiene `CodexLLM`, `OllamaEmbedder` y `CosineReranker` en
`project-knowledge/src/project_knowledge/providers.py`. `memory.py` los pasa
explícitamente a `Graphiti`; no existe herencia automática de la suscripción
ChatGPT. Ese código está fijado a `graphiti-core==0.30.1` y a la configuración
del Mac. Portarlo y comprobarlo con `0.30.2` sigue pendiente. El ranking por
coseno de ese piloto no es un cross-encoder entrenado.

## Contrato de ingesta

Cada episodio debe conservar:

| Campo | Uso |
| --- | --- |
| ID del evento | Mismo ID para reintentar el mismo contenido; ID nuevo para una corrección o un hecho diferente |
| Proyecto / `group_id` | Filtrar ingesta y consultas en la aplicación |
| Fuente | Archivo, revisión/hash y localización que permitan volver al original |
| Fecha del hecho | Cuándo ocurrió lo que se registra, con zona horaria |
| Fecha de ingesta | Cuándo se incorporó al sistema |
| Contenido original | Recuperar evidencia sin depender del resumen del modelo |
| Recibo | Estado pendiente/completado/fallido, IDs resultantes y diagnóstico |

Este es el contrato propuesto para la integración del NUC. La aplicación debe
comprobar IDs y contenido antes de repetir una ingesta; no asumir que pasar un
UUID hace idempotente toda la operación. En el piloto local esa protección está
en `memory.py`, comprobado por lectura de código el 2026-10-02.

Guardar episodios y recibos en un directorio privado fuera de Git, por ejemplo
`/home/pink/knowledge-graphs/data/lab/events/`. Limitar inicialmente la ingesta
a una operación concurrente y fuentes elegidas. Consultas y exportaciones deben
incluir el `group_id`; proyectos con límites de acceso distintos necesitan
instancias y credenciales separadas.

## Ver y corregir relaciones

Usar Browser para consultar `Entity`, `Episodic` y `RELATES_TO`; comprobar el
esquema real de la versión instalada antes de guardar consultas permanentes.
Las relaciones temporales incluyen datos como `fact`, `valid_at`, `invalid_at`
y referencias a episodios. La fecha de ingesta y la fecha de validez representan
cosas diferentes. [Modelo temporal](https://github.com/getzep/graphiti).

Una corrección debe partir de una fuente corregida y de un episodio nuevo que
explique qué cambió y cuándo. Revisar después el hecho vigente, los episodios y
la relación anterior. La invalidación depende de la extracción y del contexto;
comprobarla con datos de prueba antes de confiar en ella.

Las vistas Obsidian generadas y los grafos técnicos se regeneran desde sus
fuentes. No convertir una edición de la copia en la corrección definitiva.
Las operaciones de fusionar, ocultar o borrar entidades extraídas necesitan una
capa de curación con recibo y recuperación; esa interfaz no está implementada
por este documento.

## Aceptación del primer proyecto

1. Verificar consulta autenticada a Neo4j e índices, y registrar versiones.
2. Ingerir dos episodios sintéticos del mismo proyecto con hechos contradictorios
   y fechas distintas. Inspeccionar fuentes, relación vigente e historial.
3. Reintentar el mismo evento; comprobar que no duplica la ingesta. Rechazar
   reutilizar el ID con otro contenido. Probar interrupción y recuperación.
4. Consultar con y sin un filtro erróneo de proyecto y comprobar el aislamiento
   de la aplicación. No usar datos privados de otro proyecto para esta prueba.
5. Copiar episodios, recibos y base, y restaurar en otra instancia.

Importar el paquete o ver el contenedor sano no demuestra estas capacidades.
La ingesta, la corrección temporal, el proveedor y la restauración del NUC están
pendientes de validar.

El 2026-10-02 se comprobó en un entorno temporal del Mac que `graphiti-core==0.30.2`
se instala e importa en Python 3.12. Se inspeccionaron los modelos `EntityNode`,
`EpisodicNode` y `EntityEdge`, incluidos `group_id`, `fact`, `valid_at`,
`invalid_at` y `episodes`. Esta comprobación no creó un cliente ni realizó ingesta.
