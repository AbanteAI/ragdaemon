# Ragdaemon

Ragdaemon is a visualization tool for Python call graphs using networkx and Three.js.

1. Clone this repo
2. Install locally with pip:
```
pip install -e .
```

### Live server


1. Set the `OPENAI_API_KEY` environmental variable
2. Run `ragdaemon` in any git repo to update ragdaemon and launch the frontend on port 5001.
3. Optional flags:
- `--refresh` / `-r`: Generate the full graph and database records for the active codebase.
- `--chunk-extensions` / `-c`: Specify file extensions to run Chunker on, e.g. `-c .py .js`. Default (none) = all text files.

### Python module
```
import asyncio
from pathlib import Path
from ragdaemon.daemon import Daemon

cwd = Path.cwd()
daemon = Daemon(cwd)
asyncio.run(daemon.update())

# Search
results = daemon.search("javascript")
for result in results:
    print(f"{result["distance"]} | {result["id"]})

# RAG Context Selection
query = "How do I run the tests?"
context_builder = daemon.get_context(
    query, 
    include=["package.json"], 
    auto_tokens=5000
)
context = context_builder.render()
query += f"\nCODE CONTEXT\n{context}"
...
```
