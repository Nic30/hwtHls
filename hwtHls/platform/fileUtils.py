from io import StringIO
from pathlib import Path
from typing import Union, Callable, Tuple


# :note: bool in return type of OutputStreamGetter specifies if the stream should be closed or not
OutputStreamGetter = Callable[[str], Tuple[StringIO, bool]]


def outputFileGetter(rootDir: Union[Path, str], fileName: str) -> OutputStreamGetter:
    if not isinstance(rootDir, Path):
        rootDir = Path(rootDir)
        rootDir.stat()  # raise OSError if path does not exists
        
    def getter(folderName:str):
        d = rootDir / folderName
        d.mkdir(exist_ok=True)
        return open(d / fileName, "w"), True

    return getter
