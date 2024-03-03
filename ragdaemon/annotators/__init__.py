from ragdaemon.annotators.base_annotator import Annotator
from ragdaemon.annotators.chunker import Chunker
from ragdaemon.annotators.hierarchy import Hierarchy
from ragdaemon.annotators.layout_hierarchy import LayoutHierarchy

annotators_map = {
    "hierarchy": Hierarchy,
    "chunker": Chunker,
    "layout_hierarchy": LayoutHierarchy,
}
