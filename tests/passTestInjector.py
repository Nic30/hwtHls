from datetime import datetime, timedelta
from enum import Enum, auto
from pathlib import Path
from types import MethodType
from typing import Optional, Union, Callable, Self

from hwt.hwModule import HwModule
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.architecture.transformation.hlsAndRtlNetlistPass import HlsAndRtlNetlistPass
from hwtHls.llvm.llvmIr import LlvmCompilationBundle, IntentionalCompilationInterupt, \
    StringRef, Any, AnyToFunction, AnyToModule, AnyToLoop, AnyToMachineFunction, Module, Function, \
    HwtHlsIoMetadata, IODirection, MachineFunction
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from hwtHls.platform.platform import HlsDebugBundle, \
    _runOnSsaModuleGetter
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from hwtHls.ssa.translation.toLlvm import ToLlvmIrTranslator


def _isOverriddenFunc(method: MethodType):
    prntFunc = getattr(PassTestInjector, method.__name__)
    return method.__func__ != prntFunc


class PassTestInjector():
    """
    Abstract class for PassTestInjector implementations.
    An object which wraps test functions and injects them into compilation pipeline.
    
    :note: Call :meth:`~.install` to actually install tests in the pipeline to be executed.
    """

    class TIME_LOG_STAGE(Enum):
        NO_OPT_IR = auto()
        OPT_IR = auto()
        OPT_MIR = auto()
        HLSNETLIST = auto()
        RTL = auto()

    @staticmethod
    def logTimeToStdout(stage: TIME_LOG_STAGE, t: timedelta):
        """
        Function which can be used as an argument of :meth:`~.setDebugLogTime` to log times in stdout
        """
        print(stage.name, t)

    def __init__(self, topToRunTestsOn: HwModule, tc: SimTestCase):
        self._topToRunTestsOn = topToRunTestsOn
        self._debugLogTime = None
        self.tc = tc
        self._logFileNameStem = "" if tc is None else Path(tc.DEFAULT_LOG_DIR, tc.getTestName())
        self._lastWorkingIr: Optional[str] = None
        self._compilationBundleStack: list[ToLlvmIrTranslator] = []
        self._platform = None
        self._runSsaPasses_original: Callable[["HlsScope", ToLlvmIrTranslator], None] = None
        self._runSsaToNetlist_original: Callable[["HlsScope", ToLlvmIrTranslator, HlsNetlistCtx], HlsNetlistCtx] = None
        self._runMirToHlsNetlist_original: Callable[["HlsScope", ToLlvmIrTranslator, HlsNetlistCtx, ...], HlsNetlistCtx] = None
        self.setRunTestsAfter()

    def setRunTestsAfter(self,
                      runTestAfterPassFilter:Optional[set["str"]]=None,
                      runTestBeforeLlvmIrPasses:bool=True,
                      runTestAfterEachPass:bool=False,
                      runTestAfterEachIrPass:bool=False,
                      runTestAfterIrPasses:bool=True,
                      runTestAfterEachMirPass:bool=False,
                      runTestAfterMirPasses:bool=True,
                      runTestAfterMirVRegIfConverterChange:bool=False,
                      runTestAfterMirGISelCombinerChange:bool=False,
                      runTestAfterEachHlsNetlistPass:bool=False,
                      runTestAfterHlsNetlistPasses:bool=True,) -> Self:
        """
        :note: This function has options for common places where tests can be executed, to run tests on
            different places you shoul override the function which constructs the pass pipeline/runs pass.
        
        :attention: runTestAfterPass is a positive filter and has priority over runTestAfterEachPass etc.
            but for it to actually execute test after any pass runTestAfterEachPass or similar must be enabled first.
        :attentino: Call this after all test functions on this object are defined because this check
            if they are defined to decide if the tests should execute.
        """
        self._runTestAfterPassFilter = runTestAfterPassFilter
        self._hasLlvmIrTestFn = _isOverriddenFunc(self.testLlvmIr) or _isOverriddenFunc(self.testLlvmIrOrMir)
        self._hasLlvmMirTestFn = _isOverriddenFunc(self.testLlvmMir) or _isOverriddenFunc(self.testLlvmIrOrMir)
        self._hasHlsNetlistTestFn = _isOverriddenFunc(self.testHlsNetlist)

        self._runTestBeforeLlvmIrPasses = self._hasLlvmIrTestFn and runTestBeforeLlvmIrPasses
        self._runTestAfterIrPasses = self._hasLlvmIrTestFn and runTestAfterIrPasses
        self._runTestAfterMirPasses = self._hasLlvmIrTestFn and runTestAfterMirPasses
        self._runTestAfterHlsNetlistPasses = self._hasHlsNetlistTestFn and runTestAfterHlsNetlistPasses

        self._runTestAfterEachIrPass = runTestAfterEachIrPass or (runTestAfterEachPass and self._hasLlvmIrTestFn)
        self._runTestAfterEachMirPass = runTestAfterEachMirPass or (runTestAfterEachPass and self._hasLlvmMirTestFn)
        if runTestAfterMirGISelCombinerChange or runTestAfterMirVRegIfConverterChange:
            assert self._hasLlvmMirTestFn
        self._runTestAfterMirVRegIfConverterChange = runTestAfterMirVRegIfConverterChange
        self._runTestAfterMirGISelCombinerChange = runTestAfterMirGISelCombinerChange
        self._runTestAfterEachHlsNetlistPass = runTestAfterEachHlsNetlistPass or (runTestAfterEachPass and self._hasHlsNetlistTestFn)
        return self

    def setDebugLogTime(self, debugLogTime: Optional[Callable[[TIME_LOG_STAGE, timedelta], None]]) -> Self:
        """
        Set callback for time logging/profiling
        """
        self._debugLogTime = debugLogTime
        return self

    def setLogFileNameStem(self, logFileNameStem: Optional[Union[Path, str]]) -> Self:
        self._logFileNameStem = logFileNameStem
        return self

    def install(self, platform: VirtualHlsPlatform):
        self._platform = platform

        self._runSsaPasses_original = platform.runSsaPasses
        platform.runSsaPasses = self.runSsaPasses

        self._runSsaToNetlist_original = platform.runSsaToNetlist
        platform.runSsaToNetlist = self.runSsaToNetlist

        self._runMirToHlsNetlist_original = platform.runMirToHlsNetlist
        platform.runMirToHlsNetlist = self.runMirToHlsNetlist

    def testLlvmIr(self, platform: VirtualHlsPlatform, toLlvm: ToLlvmIrTranslator):
        return self.testLlvmIrOrMir(platform, toLlvm, False)

    def testLlvmMir(self, platform: VirtualHlsPlatform, toLlvm: ToLlvmIrTranslator):
        return self.testLlvmIrOrMir(platform, toLlvm, True)

    def testLlvmIrOrMir(self, platform: VirtualHlsPlatform, toLlvm: ToLlvmIrTranslator, isMir: bool):
        """
        :note: you likely should override this function in your child class
        """
        pass

    def testHlsNetlist(self, nethlist: HlsNetlistCtx) -> None:
        """
        :note: you likely should override this function in your child class
        """
        pass

    def _runWithTimeLog(self, stage: TIME_LOG_STAGE, fn: Callable[[LlvmCompilationBundle, ], None], *args, **kwargs):
        if self._debugLogTime:
            time0 = datetime.now()
        fn(*args, **kwargs)
        if self._debugLogTime:
            time1 = datetime.now()
            self._debugLogTime(stage, time1 - time0)

    def runTestAfterLlvmIrOrMirPass(self, passName: StringRef, ir: Any):
        """
        This method is used as a after-pass callback from LLVM/C++ to executes test functions.
        """
        # print("runTestAfterLlvmIrOrMirPass", passName.str())
        f = self._runTestAfterPassFilter
        runTest = f is None or passName.str() in f

        F = AnyToFunction(ir)
        if F is None:
            M = AnyToModule(ir)
            if M is None:
                L = AnyToLoop(ir)
                if L is None:
                    MF = AnyToMachineFunction(ir)
                    if MF is not None:
                        if runTest and self._runTestAfterEachMirPass:
                            try:
                                self._runWithTimeLog(self.TIME_LOG_STAGE.OPT_MIR, self.testLlvmMir, self._platform, self._compilationBundleStack[-1])
                            except:
                                raise AssertionError(f"Broken after {passName.str():s}, lastWorking:\n{self._lastWorkingIr}\n broken:\n{str(MF):s}")
                        self._lastWorkingIr = str(MF)
                        return
                    else:
                        raise TypeError("unknown type of ir", ir)

                F = L.getHeader().getParent()
                assert F
            else:
                M: Module
                for obj in M:
                    if isinstance(obj, Function):
                        F = obj
                        break
                assert F is not None

        if runTest and self._runTestAfterEachIrPass:
            try:
                self._runWithTimeLog(self.TIME_LOG_STAGE.OPT_IR, self.testLlvmIr, self._platform, self._compilationBundleStack[-1])
            except:
                raise AssertionError(f"Broken after {passName.str():s} lastWorking:\n{self._lastWorkingIr}\n broken:\n{str(F):s}")

        # [todo] this is very inefficient, if only some passes are selected, do this in beforePass for selected passes
        self._lastWorkingIr = str(F)
    
    def runTestAfterLlvmMirChange(self, passName: StringRef, MF: MachineFunction):
        """
        This method is used as a after-pass callback from LLVM/C++ to executes test functions after MIR changes.
        """
        # print("runTestAfterLlvmIrOrMirPass", passName.str())
        try:
            self._runWithTimeLog(self.TIME_LOG_STAGE.OPT_MIR, self.testLlvmMir, self._platform, self._compilationBundleStack[-1])
        except:
            raise AssertionError(f"Broken after {passName.str():s}, lastWorking:\n{self._lastWorkingIr}\n broken:\n{str(MF):s}")
        self._lastWorkingIr = str(MF)

    def runTestAfterHlsNetlistPass(self, passId, passObj: HlsNetlistPass, netlist: HlsNetlistCtx):
        assert isinstance(passObj, (HlsNetlistPass, HlsAndRtlNetlistPass)), passObj
        f = self._runTestAfterPassFilter
        runTest = f is None or passObj.getName() in f
        assert self._runTestAfterEachHlsNetlistPass, "This function should not be added to pass callbacks if tests are not enabled"
        if not runTest:
            return
        try:
            self._runWithTimeLog(self.TIME_LOG_STAGE.HLSNETLIST, self.testHlsNetlist, self, netlist)
        except:
            raise AssertionError(f"Broken after {passId}")  # , lastWorking:\n{self._lastWorkingIr}\n broken:\n{str(MF):s}

    def _isCurrentlyCompilingTop(self, hls: "HlsScope", toLlvm: ToLlvmIrTranslator):
        return hls.parentHwModule._parent is None and (self._topToRunTestsOn is None or
                                                       self._topToRunTestsOn is toLlvm.parentHwModule)

    def runSsaPasses(self, hls: "HlsScope", toLlvm: ToLlvmIrTranslator):
        """
        Override for :meth:`VirtualHlsPlatform.runSsaPasses` which executes tests
        """
        res = self._runSsaPasses_original(hls, toLlvm)
        self._compilationBundleStack.append(toLlvm)
        isTop = self._isCurrentlyCompilingTop(hls, toLlvm)
        if isTop:
            if self._runTestBeforeLlvmIrPasses:
                self._runWithTimeLog(self.TIME_LOG_STAGE.NO_OPT_IR, self.testLlvmIr, self._platform, toLlvm)
            llvm: LlvmCompilationBundle = toLlvm.llvm
            if self._runTestAfterEachIrPass:
                llvm.registerAfterPassCallbackForIr(self.runTestAfterLlvmIrOrMirPass)
                llvm.registerAfterPassCallbackForMir(self.runTestAfterLlvmIrOrMirPass)  # legacy PassManager may also execute IR passes added by TargetPassConfig
            elif self._runTestAfterEachMirPass:
                llvm.registerAfterPassCallbackForMir(self.runTestAfterLlvmIrOrMirPass)
            if self._runTestAfterMirVRegIfConverterChange:
                llvm._dbgMirVRegIfConverterChangeCallbackFn = self.runTestAfterLlvmMirChange
            if self._runTestAfterMirGISelCombinerChange:
                llvm._dbgMirGISelCombinerChangeCallbackFn = self.runTestAfterLlvmMirChange

        return res

    def runSsaToNetlist(self, hls:"HlsScope", toLlvm: ToLlvmIrTranslator, netlist: HlsNetlistCtx) -> HlsNetlistCtx:
        """
        Override for :meth:`VirtualHlsPlatform.runSsaToNetlist` which executes tests
        """
        try:
            return self._runSsaToNetlist_original(hls, toLlvm, netlist)
        except IntentionalCompilationInterupt:
            isTop = hls.parentHwModule._parent is None
            if isTop and self._runTestAfterIrPasses:
                # if the compilation was interrupted prematurely (by this debug exception)
                # execute IR tests for debugging purposes
                self._runWithTimeLog(self.TIME_LOG_STAGE.OPT_IR, self.testLlvmIr, self._platform, toLlvm)
            raise
        finally:
            self._compilationBundleStack.pop()

    def _backupIoPortOrder(self, hls: "HlsScope", toLlvm: ToLlvmIrTranslator, netlist: HlsNetlistCtx):
        topIoOrder = netlist.topIoOrder = {}
        for i, (_, _, _, ioProxy, _, _ , md) in enumerate(toLlvm.ioSorted):
            md: HwtHlsIoMetadata
            topIoOrder[ioProxy] = (i, md.direction == IODirection.IO_DIR_OUT)

    def runMirToHlsNetlist(self, hls: "HlsScope", toLlvm: ToLlvmIrTranslator, netlist: HlsNetlistCtx,
                      *args) -> HlsNetlistCtx:
        """
        Override for :meth:`VirtualHlsPlatform.runMirToHlsNetlist` which executes tests
        """
        isTop = self._isCurrentlyCompilingTop(hls, toLlvm)
        if isTop:
            if self._runTestAfterEachHlsNetlistPass:
                self._backupIoPortOrder(hls, toLlvm, netlist)
                netlist.callbacksAfterPass.append(self.runTestAfterHlsNetlistPass)
            try:
                if self._runTestAfterIrPasses:
                    self._runWithTimeLog(self.TIME_LOG_STAGE.OPT_IR, self.testLlvmIr, self._platform, toLlvm)
                if self._runTestAfterMirPasses:
                    self._runWithTimeLog(self.TIME_LOG_STAGE.OPT_MIR, self.testLlvmMir, self._platform, toLlvm)
            except:
                dbg = self._platform._debug.runDebugIfEnabled
                D = HlsDebugBundle
                llvm = toLlvm.llvm
                if llvm.main is None:
                    raise NotImplementedError()
                else:
                    mf = llvm.getMachineFunction(llvm.main)

                dbg(D.DBG_2_0_mir, (toLlvm, mf), applyFnGetter=_runOnSsaModuleGetter)
                dbg(D.DBG_2_0_mirCfg, (toLlvm, mf), applyFnGetter=_runOnSsaModuleGetter)
                raise

        netlist = self._runMirToHlsNetlist_original(hls, toLlvm, netlist, *args)
        return netlist

