from ragdaemon.annotators.base_annotator import Annotator  # noqa: F401
from ragdaemon.annotators.chunker import Chunker
from ragdaemon.annotators.diff import Diff
from ragdaemon.annotators.hierarchy import Hierarchy
from ragdaemon.annotators.layout_hierarchy import LayoutHierarchy

annotators_map = {
    "hierarchy": Hierarchy,
    "chunker": Chunker,
    "diff": Diff,
    "layout_hierarchy": LayoutHierarchy,
}
