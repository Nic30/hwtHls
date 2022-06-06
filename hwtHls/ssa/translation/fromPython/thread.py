from types import FunctionType
from typing import Optional, List, Tuple, Union

from hwt.synthesizer.interface import Interface
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.hlsStreamProc.streamProc import HlsStreamProcThread, HlsStreamProc
from hwtHls.ssa.translation.fromAst.astToSsa import AstToSsa
from hwtHls.ssa.translation.fromPython.fromPython import PythonBytecodeToSsa
from ipCorePackager.constants import DIRECTION


class HlsStreamProcPyThread(HlsStreamProcThread):

    def __init__(self, hls: HlsStreamProc, fn: FunctionType, *fnArgs, **fnKwargs):
        super(HlsStreamProcPyThread, self).__init__(hls)
        self.bytecodeToAst = PythonBytecodeToSsa(self.hls, self.fn)
        self.fnArgs = fnArgs
        self.fnKwargs = fnKwargs
        self.code = None
        self._imports: List[Tuple[Union[RtlSignal, Interface], DIRECTION.IN]] = [] 
        self._exports: List[Tuple[Union[RtlSignal, Interface], DIRECTION.IN]] = []

    def getLabel(self) -> str:
        i = self.hls._threads.index(self)
        return f"t{i:d}_{self.bytecodeToAst.fn.__name__:s}"

    def compileToSsa(self):
        self.bytecodeToAst.translateFunction(*self.fnArgs, **self.fnKwargs)
        self.toSsa: Optional[AstToSsa] = self.bytecodeToAst.to_ssa
    
