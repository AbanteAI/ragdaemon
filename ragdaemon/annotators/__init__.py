from ragdaemon.annotators.base_annotator import Annotator  # noqa: F401
from ragdaemon.annotators.chunker import Chunker
from ragdaemon.annotators.chunker_line import ChunkerLine
from ragdaemon.annotators.chunker_llm import ChunkerLLM
from ragdaemon.annotators.diff import Diff
from ragdaemon.annotators.hierarchy import Hierarchy
from ragdaemon.annotators.layout_hierarchy import LayoutHierarchy
from ragdaemon.annotators.summarizer import Summarizer

annotators_map = {
    "hierarchy": Hierarchy,
    "chunker": Chunker,
    "chunker_llm": ChunkerLLM,
    "chunker_line": ChunkerLine,
    "diff": Diff,
    "layout_hierarchy": LayoutHierarchy,
    "summarizer": Summarizer,
}
