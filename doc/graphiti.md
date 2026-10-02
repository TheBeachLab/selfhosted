# Graphiti

<!-- vim-markdown-toc GFM -->

- [Install](#install)
- [Choose the model](#choose-the-model)
- [Add knowledge](#add-knowledge)
- [Fix a fact](#fix-a-fact)

<!-- vim-markdown-toc -->

[Graphiti](https://github.com/getzep/graphiti) turns text or structured data
into entities and relationships. It keeps references to the original episodes
and dates, so new information can replace an older fact without losing its
history.

It is a Python library. [Neo4j Browser](neo4j.md) is where I can inspect the
stored graph. A single editor for notes, loops and memory still needs building.

The NUC setup is WIP.

## Install

Use Python 3.12 and the [Neo4j lab](neo4j.md). With uv installed as in the
[LangGraph page](langgraph.md):

```bash
mkdir -p ~/knowledge-graphs/graphiti-lab
cd ~/knowledge-graphs/graphiti-lab
uv init --python 3.12
uv add 'graphiti-core==0.30.2'
GRAPHITI_TELEMETRY_ENABLED=false uv run python -c \
  'from importlib.metadata import version; print(version("graphiti-core"))'
```

This installs the library. It does not import any project yet.

## Choose the model

Graphiti needs a model to extract facts, an embedding model to find them and
a reranker to sort results. It uses OpenAI clients by default. For another
provider, pass the corresponding clients explicitly and try structured output
before feeding it real documents. The [project README](https://github.com/getzep/graphiti#installation)
explains the requirements.

The Mac pilot has `CodexLLM`, `OllamaEmbedder` and `CosineReranker` in:

```text
/Users/Papi/Repositories/project-knowledge/src/project_knowledge/providers.py
```

Its `memory.py` passes these clients to Graphiti. The ChatGPT subscription
does not get picked up automatically. That pilot uses `graphiti-core==0.30.1`
and Mac-specific configuration; port and try it before using it on the NUC.

## Add knowledge

Begin with one project and a few sources. Keep the original text, file path,
revision and date alongside each episode. The date of the event and the date
it was imported are different things.

Give every event an ID. Reuse that ID only when retrying the same content.
A correction gets a new ID. The application must check this before ingesting;
an ID alone does not make all writes safe to repeat. The Mac pilot does this
in `memory.py`.

Store episodes and ingestion receipts outside Git, for example in
`/home/pink/knowledge-graphs/data/lab/events/`. Start with one ingestion at a
time. Include the project's `group_id` in queries and exports.

## Fix a fact

Suppose a source says the server is in room A, then a later source says it was
moved to room B. Add the later event with its date and source. In Browser,
look at the current relationship, its episodes and the older relationship's
`valid_at` and `invalid_at` fields.

If an extracted fact is wrong, correct the source and add a new episode
explaining the correction. Inspect the result afterwards. The model can get
the extraction wrong, so follow the reference back to the original text.

Try this with two small made-up episodes before importing a project. Retry
one event and make sure it is not duplicated. Keep the episodes and receipts
with the [database backup](neo4j.md#corrections-and-backups).
