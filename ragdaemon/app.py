import argparse
import asyncio
import socket
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

from ragdaemon.daemon import Daemon
from ragdaemon.utils import mentat_dir_path

# Load daemon with command line arguments and visualization annotators
parser = argparse.ArgumentParser(description="Start the ragdaemon server.")
parser.add_argument(
    "--refresh", "-r", action="store_true", help="Refresh active records."
)
parser.add_argument(
    "--code-extensions",
    "-c",
    nargs="*",
    help="List of file extensions to process as code, e.g., .py .js",
)
parser.add_argument(
    "--diff",
    "-d",
    default="",
    help="Annotate graph with 'git diff <target>'",
)
args = parser.parse_args()
refresh = args.refresh
verbose = 2  # Always verbose in server mode
code_extensions = None if args.code_extensions is None else set(args.code_extensions)
diff = args.diff
annotators = {
    "hierarchy": {},
    "chunker": {"use_llm": True},
    # "summarizer": {},
    # "clusterer_binary": {},
    # "call_graph": {"call_extensions": code_extensions},
    "diff": {"diff": diff},
    "layout_hierarchy": {},
}
logging_dir = mentat_dir_path / "ragdaemon" / "spice_logs"
daemon = Daemon(
    Path.cwd(), annotators=annotators, logging_dir=logging_dir, verbose=verbose
)


# Start/run daemon in the background
@asynccontextmanager
async def lifespan(app: FastAPI):
    if refresh:
        await daemon.update(refresh=True)
    watch_task = asyncio.create_task(daemon.watch())
    yield
    watch_task.cancel()
    try:
        await watch_task
    except asyncio.CancelledError:
        pass


# Load FastAPI server
app = FastAPI(lifespan=lifespan)
app_dir = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=app_dir / "static"), name="static")
templates = Jinja2Templates(directory=app_dir / "templates")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    # Serialize graph and send to frontend
    nodes = [
        {"id": node, **data} for node, data in daemon.graph.nodes(data=True) if data
    ]
    edges = list[dict[str, Any]]()
    for edge in daemon.graph.edges():
        source = edge[0]
        target = edge[1]
        data = daemon.graph.get_edge_data(*edge)
        if data:
            edges.append({"source": source, "target": target, **data[0]})
    metadata = dict(daemon.graph.graph)
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "nodes": nodes, "edges": edges, "metadata": metadata},
    )


@app.get("/search", response_class=HTMLResponse)
async def search(request: Request, q: str):
    """Search the knowledge graph and return results as HTML."""
    results = daemon.search(q)
    return templates.TemplateResponse(
        "search_results.html", {"request": request, "results": results}
    )


async def main():
    """Starts the uvicorn server programmatically on first available port >5000."""
    port = 5001
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("localhost", port)) != 0:
                break  # The port is available
            port += 1  # Try the next port
    config = uvicorn.Config(
        app="ragdaemon.app:app", host="localhost", port=port, log_level="info"
    )
    if verbose:
        print(f"Starting server on port {port}...")
    server = uvicorn.Server(config)

    async def _wait_1s_then_open_browser():
        await asyncio.sleep(1)
        webbrowser.open(f"http://localhost:{port}")

    asyncio.create_task(_wait_1s_then_open_browser())
    await server.serve()
