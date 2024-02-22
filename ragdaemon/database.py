import json
from pathlib import Path


db_path = Path.cwd() / ".ragdaemon" / "graph_cache.json"
class Database:
    # Schema: {file_checksum: {nodes: [], edges: []}}
    global db_path
    def __init__(self):
        if db_path.exists():
            with open(db_path, "r") as f:
                content = f.read()
                self._db = json.loads(content) if content else {}
        else:
            self._db = {}
    
    def exists(self, file_checksum):
        return file_checksum in self._db
    
    def get(self, file_checksum):
        return self._db.get(file_checksum)
    
    def set(self, file_checksum, nodes_and_edges):
        self._db[file_checksum] = nodes_and_edges


_database = Database()
def get_db():
    global _database
    if not _database:
        _database = Database()
    return _database


def save_db():
    global _database
    db_path.parent.mkdir(exist_ok=True)
    with open(db_path, "w") as f:
        f.write(json.dumps(_database._db, indent=4))
