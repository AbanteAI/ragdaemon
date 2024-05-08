from ragdaemon.annotators.base_annotator import Annotator  # noqa: F401
from ragdaemon.annotators.call_graph import CallGraph  # noqa: F401
from ragdaemon.annotators.chunker import Chunker
from ragdaemon.annotators.chunker_line import ChunkerLine
from ragdaemon.annotators.chunker_llm import ChunkerLLM
from ragdaemon.annotators.diff import Diff
from ragdaemon.annotators.hierarchy import Hierarchy
from ragdaemon.annotators.layout_hierarchy import LayoutHierarchy
from ragdaemon.annotators.summarizer import Summarizer
from ragdaemon.annotators.clusterer_binary import ClustererBinary

annotators_map = {
    "call_graph": CallGraph,
    "chunker": Chunker,
    "chunker_line": ChunkerLine,
    "chunker_llm": ChunkerLLM,
    "clusterer_binary": ClustererBinary,
    "diff": Diff,
    "hierarchy": Hierarchy,
    "layout_hierarchy": LayoutHierarchy,
    "summarizer": Summarizer,
}
