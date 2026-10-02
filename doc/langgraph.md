# LangGraph

<!-- vim-markdown-toc GFM -->

- [Install](#install)
- [A simple loop](#a-simple-loop)
- [Open it in Studio](#open-it-in-studio)
- [Save and correct the state](#save-and-correct-the-state)

<!-- vim-markdown-toc -->

[LangGraph](https://docs.langchain.com/oss/python/langgraph/overview) runs
functions as nodes in a graph. Each node reads the state and returns changes.
A condition decides where to go next. This is what I need for a loop that
generates something, checks it and tries again.

The NUC setup is WIP.

## Install

Use a separate environment. If Python's venv module is missing, install it
with `sudo apt install python3-venv`.

As `pink` on the NUC:

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

Keep `uv.lock` with the code so the environment can be reproduced.

## A simple loop

Save this as `loop.py`. The first attempt fails, the second passes and the
graph pauses for review. This is a toy example: the check only looks for the
word `source`. There are no model calls.

```python
from typing import Literal, TypedDict
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt


class State(TypedDict):
    text: str
    attempt: int
    limit: int
    valid: bool
    approved: bool


def generate(state: State):
    attempt = state["attempt"] + 1
    text = "answer" if attempt == 1 else "answer with source"
    return {"text": text, "attempt": attempt, "approved": False}


def validate(state: State):
    return {"valid": "source" in state["text"]}


def next_step(state: State) -> Literal["generate", "review", "__end__"]:
    if state["valid"]:
        return "review"
    return "generate" if state["attempt"] < state["limit"] else END


def review(state: State):
    decision = interrupt({"text": state["text"], "attempt": state["attempt"]})
    text = decision.get("text", state["text"])
    if not isinstance(text, str):
        raise ValueError("The correction must be text")
    valid = "source" in text
    return {"text": text, "valid": valid,
            "approved": decision.get("approve") is True and valid}


def build():
    builder = StateGraph(State)
    builder.add_node("generate", generate)
    builder.add_node("validate", validate)
    builder.add_node("review", review)
    builder.add_edge(START, "generate")
    builder.add_edge("generate", "validate")
    builder.add_conditional_edges("validate", next_step)
    builder.add_edge("review", END)
    return builder


graph = build().compile()  # The dev server supplies the checkpointer.

if __name__ == "__main__":
    app = build().compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": str(uuid4())}, "recursion_limit": 12}
    initial = {"text": "", "attempt": 0, "limit": 3,
               "valid": False, "approved": False}
    for update in app.stream(initial, config, stream_mode="updates"):
        print(update)
    print(app.invoke(Command(resume={"approve": True}), config))
    print(app.get_graph().draw_mermaid())
```

Run it:

```bash
LANGSMITH_TRACING=false uv run python loop.py
```

The last call approves the demo automatically. In a real application, send
`Command(resume=...)` after the user makes the decision.

Try `{"approve": False}` to reject it, or
`{"approve": True, "text": "corrected answer with source"}` to edit it.
A correction without `source` cannot be approved. With `limit` set to 1,
the first attempt ends without reaching review.

The attempt counter stops retries. `recursion_limit` is an extra limit on
graph steps. If I hit `GraphRecursionError`, I need to look at the exit
condition before raising that number.

## Open it in Studio

Save `langgraph.json` next to `loop.py`:

```json
{
  "dependencies": ["."],
  "graphs": {"loop": "./loop.py:graph"}
}
```

Start the development server on the NUC:

```bash
LANGSMITH_TRACING=false uv run langgraph dev \
  --host 127.0.0.1 --port 2024 --no-browser
```

From the Mac:

```bash
ssh -N -o ExitOnForwardFailure=yes \
  -L 127.0.0.1:2024:127.0.0.1:2024 pink-sudo
```

Open `http://127.0.0.1:2024/docs` for the API, or
[Studio](https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024)
to see the graph and run it with the initial state above. Inspect the paused
state, correct it and resume. Edit `loop.py` to change the nodes or conditions.

Studio's interface comes from LangSmith, even when the server runs locally.
`LANGSMITH_TRACING=false` disables trace uploads. See the
[Studio setup](https://docs.langchain.com/langsmith/quick-start-studio) for
account requirements. If Safari blocks the local connection, try Chromium.

`langgraph dev` is for development. Deploying
[Agent Server](https://docs.langchain.com/langsmith/deploy-standalone-server)
has separate license, key and infrastructure requirements.

## Save and correct the state

`InMemorySaver` loses the checkpoints when the process closes. Use
[SqliteSaver](https://docs.langchain.com/oss/python/langgraph/persistence)
for a persistent local file, outside Git.

Use `get_state_history` to find a checkpoint, `update_state` to correct it,
then `invoke(None, new_config)` to continue from that branch. The
[time travel guide](https://docs.langchain.com/oss/python/langgraph/use-time-travel)
has examples.

Replaying a checkpoint does not undo an email or a database write. An
[interrupted node](https://docs.langchain.com/oss/python/langgraph/interrupts)
starts again when resumed, so give external operations stable IDs and make
retries safe.
