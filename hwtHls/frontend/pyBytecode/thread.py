from types import FunctionType
from typing import Optional, List, Tuple, Union

from hwt.synthesizer.interface import Interface
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.ast.astToSsa import HlsAstToSsa
from hwtHls.frontend.pyBytecode.fromPython import PyBytecodeToSsa
from hwtHls.scope import HlsThread, HlsScope
from ipCorePackager.constants import DIRECTION


class HlsThreadFromPy(HlsThread):

    def __init__(self, hls: HlsScope, fn: FunctionType, *fnArgs, **fnKwargs):
        super(HlsThreadFromPy, self).__init__(hls)
        self.fn = fn
        self.fnName = getattr(fn, "__qualname__", fn.__name__)
        self.bytecodeToSsa = PyBytecodeToSsa(self.hls, self.fnName)
        self.fnArgs = fnArgs
        self.fnKwargs = fnKwargs
        self.code = None
        self._imports: List[Tuple[Union[RtlSignal, Interface], DIRECTION.IN]] = [] 
        self._exports: List[Tuple[Union[RtlSignal, Interface], DIRECTION.IN]] = []

    def getLabel(self) -> str:
        i = self.hls._threads.index(self)
        return f"t{i:d}_{self.fnName:s}"

    def compileToSsa(self):
        self.bytecodeToSsa.translateFunction(self.fn, *self.fnArgs, **self.fnKwargs)
        self.toSsa: Optional[HlsAstToSsa] = self.bytecodeToSsa.toSsa
    
