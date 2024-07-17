from typing import Union

from ragdaemon.io.docker_io import DockerIO
from ragdaemon.io.local_io import LocalIO


IO = Union[LocalIO, DockerIO]
