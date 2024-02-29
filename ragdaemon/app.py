import json
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import networkx as nx
from starlette.templating import Jinja2Templates
import uvicorn

from ragdaemon.daemon import Daemon


app = FastAPI()
app_dir = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=app_dir / "static"), name="static")
templates = Jinja2Templates(directory=app_dir / "templates")


# Generate when the server starts
daemon = Daemon(Path.cwd())
@app.on_event("startup")
async def startup_event():
    global daemon
    await daemon.refresh()


@app.get('/', response_class=HTMLResponse)
async def home(request: Request):

    # Serialize and send to frontend
    nodes = [{'id': node, **data} for node, data in daemon.graph.nodes(data=True)]
    edges = [{'source': source, 'target': target, **data} for source, target, data in daemon.graph.edges(data=True)]
    metadata = {
        'num_nodes': len(nodes),
        'num_edges': len(edges)
    }
    return templates.TemplateResponse(
        "index.html", 
        {"request": request, "nodes": nodes, "edges": edges, "metadata": metadata}
    )


@app.get('/search', response_class=JSONResponse)
async def search(request: Request, q: str):
    """Search the knowledge graph and return results."""
    results = daemon.search(q)
    return [data["id"] for data in results["metadatas"][0]]


async def main():
    """Starts the uvicorn server programmatically."""
    config = uvicorn.Config(app="ragdaemon.app:app", host="localhost", port=5001, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()
