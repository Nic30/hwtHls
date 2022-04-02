from pathlib import Path
from typing import Union, Callable, Tuple
from io import StringIO

# :note: bool in return type of OutputStreamGetter specifies if the stream should be closed or not
OutputStreamGetter = Callable[[str], Tuple[StringIO, bool]]


def outputFileGetter(rootDir: Union[Path, str], fileSuffix: str) -> OutputStreamGetter:
    if not isinstance(rootDir, Path):
        rootDir = Path(rootDir)
    
    def getter(fileNameStem:str):
        return open(rootDir / (fileNameStem + fileSuffix), "w"), True

    return getter
