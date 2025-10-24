from pathlib import Path
from typing import Optional, List, Tuple, Union, Callable, Self

from hwt.hwIO import HwIO
from hwt.pyUtils.typingFuture import override
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.threadFromPy import HlsThreadFromPy, _dumpModuleParams
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.platform.platform import DefaultHlsPlatform, HlsDebugBundle
from hwtHls.scope import HlsThread, HlsScope
from hwtHls.ssa.translation.toLlvm import ToLlvmIrTranslator
from ipCorePackager.constants import DIRECTION


class HlsThreadFromLlvmIr(HlsThread):
    """
    Construct LLVM thread function direcly using self.toLlvm which provides llvm::IRBuilder
    and all other object required for LLVM IR constructions.
    
    :attention: the user provided construct function must also prefill toLlvm.ioToArgIndex, toLlvm.ioSorted
    """

    def __init__(self, hls: HlsScope, fn: Callable[[Self, ...], None], *fnArgs, **fnKwargs):
        super(HlsThreadFromLlvmIr, self).__init__(hls, None)
        self.fn = fn
        self.fnName = getattr(fn, "__qualname__", fn.__name__)
        self.toLlvm: Optional[ToLlvmIrTranslator] = None
        self.dbgTracer: Optional[DebugTracer] = DebugTracer(None)
        self.fnArgs = fnArgs
        self.fnKwargs = fnKwargs
        self._imports: List[Tuple[Union[RtlSignal, HwIO], DIRECTION]] = []
        self._exports: List[Tuple[Union[RtlSignal, HwIO], DIRECTION]] = []
        self._doCloseTrace = False

    @override
    def prepareLlvmTranslator(self):
        self.toLlvm = ToLlvmIrTranslator(self.hls.parentHwModule, None, self.hls.parentHwModule._target_platform._llvmCliArgs)

    @override
    def debugCopyConfig(self, p: DefaultHlsPlatform):
        d = p._debug
        debugDir = d.dir
        if debugDir is not None:
            debugHierarchyPath = d.isActivated(HlsDebugBundle.DBG_0_0_hierachyPath)
            self.toLlvm._dbgRootDir = Path(debugDir)
            self.toLlvm._dbgSubDir = self.getDbgSubdir()
            self.dbgTracer, self._doCloseTrace = p._getDebugTracer(
                self.toLlvm._dbgSubDir, HlsDebugBundle.DBG_0_0_pyFrontedBytecodeTrace)

            if debugHierarchyPath:
                dbgDir = self.toLlvm._dbgRootDir / self.toLlvm._dbgSubDir
                _dumpModuleParams(dbgDir, self.getLabel(), self.hls.parentHwModule)

    @override
    def getLabel(self) -> str:
        return HlsThreadFromPy.getLabel(self)

    @override
    def compileToSsa(self):
        try:
            self.fn(self, *self.fnArgs, **self.fnKwargs)
        finally:
            if self.dbgTracer is not None and self._doCloseTrace:
                self.dbgTracer._out.close()

