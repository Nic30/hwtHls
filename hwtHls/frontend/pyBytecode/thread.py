from pathlib import Path
from types import FunctionType
from typing import Optional, List, Tuple, Union

from hwt.hwIO import HwIO
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.pyBytecode.fromPython import PyBytecodeToSsa
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.platform.platform import DefaultHlsPlatform, HlsDebugBundle
from hwtHls.scope import HlsThread, HlsScope
from hwtHls.ssa.translation.toLlvm import ToLlvmIrTranslator
from ipCorePackager.constants import DIRECTION


class HlsThreadFromPy(HlsThread):

    def __init__(self, hls: HlsScope, fn: FunctionType, *fnArgs, **fnKwargs):
        super(HlsThreadFromPy, self).__init__(hls, None)
        self.fn = fn
        self.fnName = getattr(fn, "__qualname__", fn.__name__)
        self.toLlvm: Optional[ToLlvmIrTranslator] = None
        self.bytecodeToSsa: Optional[PyBytecodeToSsa] = None
        self.dbgTracer: Optional[DebugTracer] = DebugTracer(None)
        self.fnArgs = fnArgs
        self.fnKwargs = fnKwargs
        self._imports: List[Tuple[Union[RtlSignal, HwIO], DIRECTION]] = []
        self._exports: List[Tuple[Union[RtlSignal, HwIO], DIRECTION]] = []
        self._doCloseTrace = False

    def prepareLlvmTranslator(self):
        self.toLlvm = ToLlvmIrTranslator(self.hls.parentHwModule, None, self.hls.parentHwModule._target_platform._llvmCliArgs)
        self.bytecodeToSsa = PyBytecodeToSsa(self.hls, self.toLlvm, self.dbgTracer, self.getLabel(), self.getNamePrefix())

    def debugCopyConfig(self, p: DefaultHlsPlatform):
        d = p._debug
        debugDir = d.dir
        if debugDir is not None:
            debugBytecode = d.isActivated(HlsDebugBundle.DBG_0_0_pyFrontedBytecode)
            debugCfgBeing = d.isActivated(HlsDebugBundle.DBG_0_0_pyFrontedBeginCfg)
            debugCfgGen = d.isActivated(HlsDebugBundle.DBG_0_0_pyFrontedPreprocCfg)
            debugCfgFinal = d.isActivated(HlsDebugBundle.DBG_0_1_pyFrontedFinalCfg)
            if d.firstRun and (debugBytecode, debugCfgGen, debugCfgFinal):
                if debugDir and not debugDir.exists():
                    debugDir.mkdir()
                d.firstRun = False

            toSsa = self.bytecodeToSsa
            toSsa.toLlvm._dbgRootDir = Path(debugDir)
            toSsa.toLlvm._dbgSubDir = self.getLabel()
            self.dbgTracer, self._doCloseTrace = p._getDebugTracer(
                toSsa.toLlvm._dbgSubDir, HlsDebugBundle.DBG_0_0_pyFrontedBytecodeTrace)
            toSsa.dbgTracer = self.dbgTracer
            toSsa.debugBytecode = debugBytecode
            toSsa.debugCfgBegin = debugCfgBeing
            toSsa.debugCfgGen = debugCfgGen
            toSsa.debugCfgFinal = debugCfgFinal

    def getLabel(self) -> str:
        namePrefix = ""
        if len(self.hls._threads) > 1:
            i = self.hls._threads.index(self)
            namePrefix = f"t{i:d}_"

        return f"{namePrefix:s}{self.fnName:s}"

    def compileToSsa(self):
        self.toLlvm: Optional[ToLlvmIrTranslator] = self.bytecodeToSsa.toLlvm
        try:
            self.bytecodeToSsa.translateFunction(self.fn, *self.fnArgs, **self.fnKwargs)
        finally:
            if self.dbgTracer is not None and self._doCloseTrace:
                self.dbgTracer._out.close()

