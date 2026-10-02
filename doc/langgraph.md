# LangGraph: bounded loops and debugging

**Author:** Fran
**Checked:** 2026-10-02
**NUC:** instalación pendiente.

LangGraph define un estado, nodos y transiciones. Puedo generar algo, verificarlo
y volver a intentarlo con un límite. Los nodos pueden usar funciones normales o
un modelo. [Overview](https://docs.langchain.com/oss/python/langgraph/overview)
y [Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api),
consultados el 2026-10-02.

## Entorno de laboratorio

Usar un entorno propio. El NUC tiene entornos de Hailo, RAG, Whisper y TTS;
sus dependencias no deben convertirse en las del laboratorio.

Propuesta en el NUC, como `pink`. Si falta el módulo `venv`, instalar previamente
el paquete Ubuntu `python3-venv`. El primer entorno solo instala uv:

```bash
mkdir -p ~/venvs ~/knowledge-graphs/langgraph-lab
python3 -m venv ~/venvs/uv-bootstrap
~/venvs/uv-bootstrap/bin/python -m pip install 'uv==0.10.0'
export PATH="$HOME/venvs/uv-bootstrap/bin:$PATH"
cd ~/knowledge-graphs/langgraph-lab
uv init --python 3.12
uv add 'langgraph==1.2.12' 'langgraph-cli[inmem]==0.4.32' \
  'langgraph-checkpoint-sqlite==3.1.1'
```

Versiones consultadas en los metadatos de
[LangGraph](https://pypi.org/project/langgraph/1.2.12/),
[CLI](https://pypi.org/project/langgraph-cli/0.4.32/) y
[SQLite checkpointer](https://pypi.org/project/langgraph-checkpoint-sqlite/3.1.1/)
el 2026-10-02. `uv.lock` guarda la resolución completa; conservarlo con el código.
[Proyectos uv](https://docs.astral.sh/uv/guides/projects/).

## Un loop que puedo comprobar sin pagar llamadas a un modelo

Guardar como `loop.py` en el laboratorio. La primera respuesta carece de
`fuente`; la segunda la añade. Es una comprobación sintética para aprender el
flujo, no una validación de la verdad de una respuesta.

```python
from typing import Literal, TypedDict
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt


class State(TypedDict):
    texto: str
    intento: int
    limite: int
    valido: bool
    aprobado: bool


def generar(state: State):
    intento = state["intento"] + 1
    texto = "respuesta" if intento == 1 else "respuesta con fuente"
    return {"texto": texto, "intento": intento, "aprobado": False}


def validar(state: State):
    return {"valido": "fuente" in state["texto"]}


def siguiente(state: State) -> Literal["generar", "revisar", "__end__"]:
    if state["valido"]:
        return "revisar"
    return "generar" if state["intento"] < state["limite"] else END


def revisar(state: State):
    decision = interrupt({"texto": state["texto"], "intento": state["intento"]})
    texto = decision.get("texto", state["texto"])
    if not isinstance(texto, str):
        raise ValueError("La corrección debe ser texto")
    valido = "fuente" in texto
    return {"texto": texto, "valido": valido,
            "aprobado": decision.get("aprobar") is True and valido}


def build():
    builder = StateGraph(State)
    builder.add_node("generar", generar)
    builder.add_node("validar", validar)
    builder.add_node("revisar", revisar)
    builder.add_edge(START, "generar")
    builder.add_edge("generar", "validar")
    builder.add_conditional_edges("validar", siguiente)
    builder.add_edge("revisar", END)
    return builder


graph = build().compile()  # El servidor de desarrollo gestiona su persistencia.

if __name__ == "__main__":
    app = build().compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": str(uuid4())}, "recursion_limit": 12}
    initial = {"texto": "", "intento": 0, "limite": 3,
               "valido": False, "aprobado": False}
    for update in app.stream(initial, config, stream_mode="updates"):
        print(update)
    print(app.invoke(Command(resume={"aprobar": True}), config))
    print(app.get_graph().draw_mermaid())
```

```bash
LANGSMITH_TRACING=false uv run python loop.py
```

La reanudación del ejemplo aprueba automáticamente **el resultado sintético**.
En una aplicación real, `Command(resume=...)` debe llegar de la decisión humana
en la interfaz. Cambiar `limite` a 1 debe terminar sin aprobación; reanudar con
`{"aprobar": false}` debe rechazarlo. Una corrección sin `fuente` tampoco queda
aprobada. El ejemplo no escribe en servicios ni llama a un LLM.

El contador limita intentos de generación. `recursion_limit` limita pasos del
grafo y es una protección adicional; no sustituye una condición de salida.
[Graph API, recursion limit](https://docs.langchain.com/oss/python/langgraph/graph-api#recursion-limit).

## Verlo y corregirlo en Studio

Guardar `langgraph.json` junto a `loop.py`:

```json
{
  "dependencies": ["."],
  "graphs": {"loop": "./loop.py:graph"}
}
```

En el laboratorio del NUC:

```bash
LANGSMITH_TRACING=false uv run langgraph dev \
  --host 127.0.0.1 --port 2024 --no-browser
```

Desde el Mac:

```bash
ssh -N -o ExitOnForwardFailure=yes \
  -L 127.0.0.1:2024:127.0.0.1:2024 pink-sudo
```

Abrir la API local en `http://127.0.0.1:2024/docs` y
[Studio](https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024).
Enviar el estado inicial, inspeccionar cada nodo y el estado de la pausa.
Corregir texto/estado o el código y ejecutar de nuevo el tramo afectado.

Studio carga su interfaz desde LangSmith. Configurar `LANGSMITH_TRACING=false`
desactiva el envío de trazas según la guía oficial; la interfaz sigue siendo
externa y cualquier nodo que llame a un proveedor envía a ese proveedor su
entrada. Comprobar los requisitos de cuenta al usar Studio. Safari puede bloquear
la conexión local: probar Chromium antes de abrir un túnel de un tercero.
[Studio quickstart](https://docs.langchain.com/langsmith/quick-start-studio),
consultado el 2026-10-02.

`langgraph dev` es el servidor de desarrollo. El
[Agent Server standalone](https://docs.langchain.com/langsmith/deploy-standalone-server)
tiene requisitos propios de licencia, claves e infraestructura. La biblioteca
y el ejemplo local no implican tener esa plataforma instalada.

## Checkpoints y errores

`InMemorySaver` conserva el estado dentro del proceso del ejemplo. Para conservarlo
tras cerrar el proceso, usar `SqliteSaver` con una ruta privada, por ejemplo
`/home/pink/knowledge-graphs/data/langgraph/lab.sqlite3`. Conservar también la
revisión del código usada por cada ejecución.
[Persistence](https://docs.langchain.com/oss/python/langgraph/persistence).

`get_state_history` permite encontrar un checkpoint; `update_state` crea una
rama con la corrección, y `invoke(None, nueva_config)` continúa desde ella.
No deshace operaciones externas ya realizadas. Al reanudar un `interrupt`,
el nodo empieza de nuevo: las escrituras y llamadas con efectos necesitan ser
idempotentes, también ante replay o reintentos.
[Time travel](https://docs.langchain.com/oss/python/langgraph/use-time-travel) y
[Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts).

Si aparece `GraphRecursionError`, revisar condición de salida, contador y
transiciones. Registrar el fallo de verificación y corregirlo antes de ampliar
el límite. Si una reanudación repite una acción, revisar la separación entre
revisión, efectos externos y sus IDs de operación.

## Verificación de esta guía

El 2026-10-02 se ejecutó el ejemplo en un directorio temporal del Mac con
Python 3.12.11 y las versiones fijadas arriba. Se comprobó aprobación, rechazo,
corrección válida/inválida, salida con un intento, error al limitar la recursión
y reanudación SQLite después de cerrar y abrir la conexión. El servidor `dev`
arrancó en loopback, registró `loop`, respondió `{"ok": true}` en `/ok` y sirvió
`/docs` con HTTP 200. Se detuvo al terminar. No se probó Studio con una cuenta
LangSmith ni el despliegue o la interfaz de este servicio en el NUC.
