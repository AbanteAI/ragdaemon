import json
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import networkx as nx
from starlette.templating import Jinja2Templates
import uvicorn

from ragdaemon.generate_graph import generate_pseudo_call_graph
from ragdaemon.position_nodes import add_coordiantes_to_graph


app = FastAPI()
app_dir = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=app_dir / "static"), name="static")
templates = Jinja2Templates(directory=app_dir / "templates")


# Generate when the server starts
graph = None
@app.on_event("startup")
async def startup_event():
    global graph
    graph = await generate_pseudo_call_graph(Path.cwd())
    graph = add_coordiantes_to_graph(graph)
    
    graph_path = Path.cwd() / ".ragdaemon" / "graph.json"
    graph_path.parent.mkdir(exist_ok=True)
    data = nx.readwrite.json_graph.node_link_data(graph)
    with open(graph_path, "w") as f:
        json.dump(data, f, indent=4)


@app.get('/', response_class=HTMLResponse)
async def home(request: Request):

    # Serialize and send to frontend
    nodes = [{'id': node, **data} for node, data in graph.nodes(data=True)]
    edges = [{'source': source, 'target': target, **data} for source, target, data in graph.edges(data=True)]
    metadata = {
        'num_nodes': len(nodes),
        'num_edges': len(edges)
    }
    return templates.TemplateResponse(
        "index.html", 
        {"request": request, "nodes": nodes, "edges": edges, "metadata": metadata}
    )


async def main():
    """Starts the uvicorn server programmatically."""
    config = uvicorn.Config(app="ragdaemon.app:app", host="localhost", port=5001, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()
