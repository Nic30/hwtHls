from io import StringIO
from types import FunctionType
from typing import Optional, Union

from hwtHls.netlist.nodes.node import HlsNetNode


class DebugTracer():
    """
    A wraper arround output stream for messages about optimization pass actions. Functionality similar to standard python module called logging.
    """
    INDENT = "  "

    def __init__(self, out: Optional[StringIO]):
        self._out = out
        self._scope = []
        self._labelPrinted = []
        self._curIndent = ""

    def scoped(self, nameOrObj: Union[str, FunctionType], node: Optional[HlsNetNode]):
        """
        Used to mark scope in output, automatically handles indenting and does not print scope promt if nothing was logged in this or nested scope.
        """
        self._scope.append((nameOrObj, node))
        self._labelPrinted.append(False)
        return self

    def _writeScopeLabel(self):
        out = self._out
        for i, ((obj, node), printed) in enumerate(zip(self._scope, self._labelPrinted)):
            if printed:
                continue

            if isinstance(obj, str):
                objStr = obj
            elif isinstance(obj, (FunctionType, type)):  # :note: type is a base type of class objects
                objStr = getattr(obj, "__qualname__", obj.__name__)
            else:
                objStr = repr(obj)

            for _ in range(i):
                out.write(self.INDENT)

            out.write(objStr)
            if node is not None:
                out.write(f"<{node._id}>")
            out.write(":\n")
            self._labelPrinted[i] = True
            
    def __enter__(self):
        out = self._out
        if out is not None:
            self._curIndent = self._curIndent + self.INDENT
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            if not self._labelPrinted[-1]:
                # print error into trace
                self.log(("raised", exc_type, exc_val))

        if self._out is not None:
            self._curIndent = self._curIndent[0:-len(self.INDENT)]
        self._scope.pop()
        self._labelPrinted.pop()

    def log(self, msg, formater=lambda x: x, ending="\n"):
        out = self._out
        if out is not None:
            _msg = formater(msg)
            if not isinstance(_msg, str):
                _msg = repr(_msg)
            if not self._labelPrinted[-1]:
                self._writeScopeLabel()
            out.write(self._curIndent)
            out.write(_msg)
            out.write(ending)
