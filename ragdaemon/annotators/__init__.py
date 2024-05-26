from ragdaemon.annotators.base_annotator import Annotator  # noqa: F401
from ragdaemon.annotators.call_graph import CallGraph  # noqa: F401
from ragdaemon.annotators.chunker import Chunker
from ragdaemon.annotators.diff import Diff
from ragdaemon.annotators.hierarchy import Hierarchy
from ragdaemon.annotators.layout_hierarchy import LayoutHierarchy
from ragdaemon.annotators.summarizer import Summarizer

annotators_map = {
    "call_graph": CallGraph,
    "chunker": Chunker,
    "diff": Diff,
    "hierarchy": Hierarchy,
    "layout_hierarchy": LayoutHierarchy,
    "summarizer": Summarizer,
}
