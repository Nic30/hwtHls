from types import FunctionType
from typing import Optional, List, Tuple, Union

from hwt.synthesizer.interface import Interface
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.ast.astToSsa import HlsAstToSsa
from hwtHls.frontend.pyBytecode.fromPython import PyBytecodeToSsa
from hwtHls.scope import HlsThread, HlsScope
from ipCorePackager.constants import DIRECTION
from hwtHls.platform.platform import DefaultHlsPlatform, HlsDebugBundle


class HlsThreadFromPy(HlsThread):

    def __init__(self, hls: HlsScope, fn: FunctionType, *fnArgs, **fnKwargs):
        super(HlsThreadFromPy, self).__init__(hls)
        self.fn = fn
        self.fnName = getattr(fn, "__qualname__", fn.__name__)
        self.bytecodeToSsa = PyBytecodeToSsa(self.hls, self.fnName)
        self.fnArgs = fnArgs
        self.fnKwargs = fnKwargs
        self._imports: List[Tuple[Union[RtlSignal, Interface], DIRECTION]] = [] 
        self._exports: List[Tuple[Union[RtlSignal, Interface], DIRECTION]] = []

    def debugCopyConfig(self, p: DefaultHlsPlatform):
        d = p._debug
        debugDir = d.dir
        if debugDir is not None:
            debugBytecode = d.isActivated(HlsDebugBundle.DBG_0_pyFrontedBytecode)
            debugCfgBeing = d.isActivated(HlsDebugBundle.DBG_0_pyFrontedBeginCfg)
            debugCfgGen = d.isActivated(HlsDebugBundle.DBG_0_pyFrontedPreprocCfg)
            debugCfgFinal = d.isActivated(HlsDebugBundle.DBG_0_pyFrontedFinalCfg)
            if d.firstRun and (debugBytecode, debugCfgGen, debugCfgFinal):
                if debugDir and not debugDir.exists():
                    debugDir.mkdir()
                d.firstRun = False
 
            toSsa = self.bytecodeToSsa
            toSsa.debugDirectory = debugDir
            toSsa.debugBytecode = debugBytecode
            toSsa.debugCfgBegin = debugCfgBeing
            toSsa.debugCfgGen = debugCfgGen
            toSsa.debugCfgFinal = debugCfgFinal

    def getLabel(self) -> str:
        i = self.hls._threads.index(self)
        return f"t{i:d}_{self.fnName:s}"

    def compileToSsa(self):
        self.bytecodeToSsa.translateFunction(self.fn, *self.fnArgs, **self.fnKwargs)
        self.toSsa: Optional[HlsAstToSsa] = self.bytecodeToSsa.toSsa
    
