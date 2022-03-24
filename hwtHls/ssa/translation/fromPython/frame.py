import inspect
from types import FunctionType
from typing import Dict, Set


class PythonBytecodeFrame():

    def __init__(self, locals_: list, cellVarI: Dict[int, int], stack: list):
        self.locals = locals_
        self.stack = stack
        self.cellVarI = cellVarI
        self.preprocVars: Set[int] = set() 

    @classmethod
    def fromFunction(cls, fn: FunctionType, fnArgs: tuple, fnKwargs: dict):
        co = fn.__code__
        localVars = [None for _ in range(fn.__code__.co_nlocals)]
        if inspect.ismethod(fn):
            fnArgs = tuple((fn.__self__, *fnArgs))

        assert len(fnArgs) == co.co_argcount, ("Must have the correct number of arguments",
                                               len(fnArgs), co.co_argcount)
        for i, v in enumerate(fnArgs):
            localVars[i] = v
        if fnKwargs:
            raise NotImplementedError()

        varNameToI = {n: i for i, n in enumerate(fn.__code__.co_varnames)}
        cellVarI = {}
        for i, name in enumerate(fn.__code__.co_cellvars):
            cellVarI[i] = varNameToI[name]

        return PythonBytecodeFrame(localVars, cellVarI, [])

