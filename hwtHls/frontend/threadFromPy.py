from pathlib import Path
from types import FunctionType
from typing import Optional, List, Tuple, Union

from hdlConvertorAst.translate.common.name_scope import NameScope
from hwt.hObjList import HObjList
from hwt.hwIO import HwIO
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.mainBases import HwIOBase
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.fromPython import PyBytecodeToSsa
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.platform.platform import DefaultHlsPlatform, HlsDebugBundle
from hwtHls.scope import HlsThread, HlsScope
from hwtHls.ssa.translation.toLlvm import ToLlvmIrTranslator
from ipCorePackager.constants import DIRECTION


def _getFullHierarchyPath(tmp) -> str:
    """get all name hierarchy separated by '/' """
    name = ""
    while isinstance(tmp, (HwModule, HwIOBase, HObjList)):
        n = tmp._name
        if name == '':
            if n is not None:
                assert isinstance(n, str), (name, n)
                name = n
        else:
            if n is None:
                n = "<unnamed>"
            name = f"{n:s}/{name:s}"

        tmp = getattr(tmp, "_parent", None)

    return name


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
            debugHierarchyPath = d.isActivated(HlsDebugBundle.DBG_0_0_hierachyPath)
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
            toSsa.toLlvm._dbgSubDir = self.hls.parentHwModule._getDefaultName() + "_" + self.getLabel()
            self.dbgTracer, self._doCloseTrace = p._getDebugTracer(
                toSsa.toLlvm._dbgSubDir, HlsDebugBundle.DBG_0_0_pyFrontedBytecodeTrace)
            toSsa.dbgTracer = self.dbgTracer
            toSsa.debugBytecode = debugBytecode
            toSsa.debugCfgBegin = debugCfgBeing
            toSsa.debugCfgGen = debugCfgGen
            toSsa.debugCfgFinal = debugCfgFinal

            if debugHierarchyPath:
                parentHwMod = self.hls.parentHwModule
                dbgDir = toSsa.toLlvm._dbgRootDir / toSsa.toLlvm._dbgSubDir
                dbgDir.mkdir(exist_ok=True)
                path = _getFullHierarchyPath(parentHwMod)
                with open(dbgDir / HlsDebugBundle.DBG_0_0_hierachyPath[1], "w") as f:
                    f.write(path)
                    f.write("/")
                    f.write(self.getLabel())
                    f.write("\n")
                    for par in parentHwMod._hwParams:
                        par: HwParam 
                        f.write(par._name)
                        f.write(" = ")
                        f.write(str(par.get_value()))
                        f.write("\n")
                    
                    


    def getLabel(self) -> str:
        if self._label is not None:
            return self._label

        namePrefix = ""
        if len(self.hls._threads) > 1:
            i = self.hls._threads.index(self)
            namePrefix = f"t{i:d}_"

        label = f"{namePrefix:s}{self.fnName:s}"
        ns: NameScope = self.hls.parentHwModule._target_platform._debug.nameScope
        self._label = ns.checked_name(label, self)
        return self._label

    def compileToSsa(self):
        self.toLlvm: Optional[ToLlvmIrTranslator] = self.bytecodeToSsa.toLlvm
        try:
            self.bytecodeToSsa.translateFunction(self.fn, *self.fnArgs, **self.fnKwargs)
        finally:
            if self.dbgTracer is not None and self._doCloseTrace:
                self.dbgTracer._out.close()

