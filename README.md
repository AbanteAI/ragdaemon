# Ragdaemon

Ragdaemon is a Retrieval-Augmented Generation (RAG) system for code. It runs a daemon (background process) to watch your active code, put it in a knowledge graph, and query the knowledge graph to (among other things) generate context for LLM completions.

Three ways to use Ragdaemon:
## 1. **Help me write code** 

Ragdaemon powers the 'auto-context' feature in [Mentat](http://github.com/AbanteAI/mentat), a command-line coding assistant. You can install Mentat using `pip install mentat`. Run with the `--auto-context-tokens <amount>` or `-a` (default=5000) flag, and ragdaemon-selected context will be added to all of your prompts. 

## 2. **Explore the knowledge graph**

Install locally to visualize and query the knowledge graph directly. 
Install using `pip install ragdaemon`, and run in your codebase's directory, e.g. `ragdaemon`. This will start a Daemon on your codebase, and an interface at `localhost:5001`. Options:
- `--chunk-extensions <ext>[..<ext>]`: Which file extensions to chunk. If not specified, defaults to the top 20 most common code file extensions.
- `--chunk-model`: OpenAI's `gpt-4-0215-preview` by default.
- `--embeddings-model`: OpenAI's `text-embedding-ada-002` by default.
- `--diff`: A git diff to include in the knowledge graph. By default, the active diff (if any) is included with each code feature.

## 3. **Use ragdaemon Python API** 

Ragdaemon is released open-source as a standalone RAG system. It includes a library of python classes to generate and query the knowledge graph. The graph itself is a NetworkX MultiDiGraph which saves/loads to a `.json` file.

```python
import asyncio
from pathlib import Path
from ragdaemon.daemon import Daemon

cwd = Path.cwd()
daemon = Daemon(cwd)
asyncio.run(daemon.update())

# Search
results = daemon.search("javascript")
for result in results:
    print(f"{result['distance']} | {result['id']}")

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
