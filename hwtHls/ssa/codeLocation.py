

class CodeLocation():
    """
    :class:`dis.Positions` with filename.
    """
    __slots__ = (
        "filename",
        "lineno",
        "end_lineno",
        "col_offset",
        "end_col_offset",
    )

    def __init__(self, filename, lineno: int, end_lineno: int, col_offset: int, end_col_offset: int):
        self.filename = filename
        self.lineno = lineno
        self.end_lineno = end_lineno
        self.col_offset = col_offset
        self.end_col_offset = end_col_offset
