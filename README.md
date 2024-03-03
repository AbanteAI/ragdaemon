# Ragdaemon

Ragdaemon is a visualization tool for Python call graphs using networkx and Three.js.

1. Clone this repo
2. Install locally with pip:
```
pip install -e .
```
3. Run in any git directory:
```
ragdaemon
```
4. Open your browser to localhost:5001

## Optional Flags

- `--refresh` / `-r`: Generate the full graph and database records for the active codebase.
- `--chunk-extensions` / `-c`: Specify file extensions to run Chunker on, e.g. `-c .py .js`. Default (none) = all text files.
