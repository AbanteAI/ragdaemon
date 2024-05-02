"""
Add a 1-sentence text summary to each file or chunk node
"""

import asyncio
from typing import Any, Optional

from spice import SpiceMessage
from spice.models import TextModel
from tqdm.asyncio import tqdm

from ragdaemon.annotators.base_annotator import Annotator
from ragdaemon.database import Database
from ragdaemon.graph import KnowledgeGraph
from ragdaemon.errors import RagdaemonError
from ragdaemon.utils import DEFAULT_COMPLETION_MODEL, semaphore

summarizer_prompt = """\
Generate a 1-sentence summary of the provided code. Follow conventions of docstrings: 
write in the imerative voice and start with a verb. Do not include any preamble or 
asides.

It may be useful to name specific fucntions from the target repository (not built-in
Python functions) which are integral to the functioning of the target code. Include a
maximum of two (2) such named functions, but err on the side of brevity.
"""


class Summarizer(Annotator):
    name = "summarizer"

    def __init__(
        self,
        *args,
        model: Optional[TextModel | str] = DEFAULT_COMPLETION_MODEL,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.model = model

    def is_complete(self, graph: KnowledgeGraph, db: Database) -> bool:
        return all(
            data.get("summary") is not None
            for _, data in graph.nodes(data=True)
            if data is not None and data.get("checksum") is not None
        )

    async def get_llm_response(self, document: str) -> str:
        if self.spice_client is None:
            raise RagdaemonError("Spice client is not initialized.")
        messages: list[SpiceMessage] = [
            {"role": "system", "content": summarizer_prompt},
            {"role": "user", "content": document},
        ]
        async with semaphore:
            response = await self.spice_client.get_response(
                messages=messages,
                model=self.model,
            )
        return response.text

    async def get_summary(self, data: dict[str, Any], db: Database):
        """Asynchronously generate summary and update graph and db"""
        record = db.get(data["checksum"])
        document = record["documents"][0]
        metadatas = record["metadatas"][0]
        summary = await self.get_llm_response(document)
        metadatas["summary"] = summary
        db.update(data["checksum"], metadatas=metadatas)
        data["summary"] = summary

    async def annotate(
        self, graph: KnowledgeGraph, db: Database, refresh: bool = False
    ) -> KnowledgeGraph:
        # Generate/add summaries to nodes with checksums (file, chunk, diff)
        tasks = []
        for _, data in graph.nodes(data=True):
            if data is None or data.get("checksum") is None:
                continue
            if data.get("summary") is not None and not refresh:
                continue
            tasks.append(self.get_summary(data, db))
        if len(tasks) > 0:
            if self.verbose:
                await tqdm.gather(*tasks, desc="Summarizing code...")
            else:
                await asyncio.gather(*tasks)
        return graph
