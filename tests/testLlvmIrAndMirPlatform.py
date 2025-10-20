from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Optional, Union, Callable, Set, List, Sequence, Self

from hwt.hdl.const import HConst
from hwt.hwModule import HwModule
from hwt.pyUtils.typingFuture import override
from hwtHls.llvm.llvmIr import LlvmCompilationBundle, IntentionalCompilationInterupt, \
    StringRef, Any, AnyToFunction, AnyToModule, AnyToLoop, AnyToMachineFunction, Module, Function
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.platform.debugBundleTypes import LlvmCliArgTuple
from hwtHls.platform.platform import DebugId, HlsDebugBundle, \
    _runOnSsaModuleGetter
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from hwtHls.ssa.analysis.llvmIrInterpret import LlvmIrInterpret, \
    SimIoUnderflowErr
from hwtHls.ssa.analysis.llvmMirInterpret import LlvmMirInterpret
from hwtHls.ssa.translation.toLlvm import ToLlvmIrTranslator
from pyDigitalWaveTools.vcd.writer import VcdWriter


class TestLlvmIrAndMirPlatform(VirtualHlsPlatform):

    class TEST_NO_OPT_IR:
        """
        This is a constant used for :meth:`TestLlvmIrAndMirPlatform.forSimpleDataInDataOutHwModule` to automatically generate
        noOptIrTest.
        """

        def __init__(self):
            raise AssertionError("This class should be used as a constant")

    class TIME_LOG_STAGE(Enum):
        NO_OPT_IR, OPT_IR, OPT_MIR = range(3)

    @staticmethod
    def logTimeToStdout(stage: TIME_LOG_STAGE, t: timedelta):
        print(stage.name, t)

    def __init__(self,
                 topToRunTestsOn: Optional[HwModule]=None,
                 noOptIrTest:Optional[Callable[[Self, LlvmCompilationBundle], None]]=None,
                 optIrTest:Optional[Callable[[Self, LlvmCompilationBundle], None]]=None,
                 optMirTest:Optional[Callable[[Self, LlvmCompilationBundle], None]]=None,
                 debugDir:Optional[Union[str, Path]]="tmp",
                 debugFilter:Optional[Set[DebugId]]=HlsDebugBundle.DEFAULT,
                 llvmCliArgs:List[LlvmCliArgTuple]=[],
                 debugLogTime: Optional[Callable[[TIME_LOG_STAGE, timedelta], None]]=None,
                 runTestAfterEachPass:bool=False,
                 runTestAfterEachIrPass:bool=False,
                 runTestAfterEachMirPass:bool=False,
                 ):
        VirtualHlsPlatform.__init__(self, debugDir=debugDir, debugFilter=debugFilter, llvmCliArgs=llvmCliArgs)
        self._topToRunTestsOn = topToRunTestsOn
        self._debugLogTime = debugLogTime
        self._noOptIrTest = noOptIrTest
        self._optIrTest = optIrTest
        self._optMirTest = optMirTest
        self._runTestAfterEachIrPass = runTestAfterEachIrPass or runTestAfterEachPass
        self._runTestAfterEachMirPass = runTestAfterEachMirPass or runTestAfterEachPass
        self._lastWorkingIr: Optional[str] = None
        self.llvm: Optional[LlvmCompilationBundle] = None

    def _runWithTimeLog(self, stage: TIME_LOG_STAGE, fn: Callable[[LlvmCompilationBundle, ], None], *args, **kwargs):
        if self._debugLogTime:
            time0 = datetime.now()
        fn(*args, **kwargs)
        if self._debugLogTime:
            time1 = datetime.now()
            self._debugLogTime(stage, time1 - time0)

    def runTestAfterPass(self, passName: StringRef, ir: Any):
        """
        This method is used as a after-pass callback from LLVM/C++ to executes test functions.
        """
        # print("runTestAfterPass", passName.str())
        F = AnyToFunction(ir)
        if F is None:
            M = AnyToModule(ir)
            if M is None:
                L = AnyToLoop(ir)
                if L is None:
                    MF = AnyToMachineFunction(ir)
                    if MF is not None:
                        if self._runTestAfterEachMirPass:
                            try:
                                self._runWithTimeLog(self.TIME_LOG_STAGE.OPT_MIR, self._optMirTest, self, self.toLlvm)
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
        if self._runTestAfterEachIrPass:
            try:
                self._runWithTimeLog(self.TIME_LOG_STAGE.OPT_IR, self._optIrTest, self, self.toLlvm)
            except:
                raise AssertionError(f"Broken after {passName.str():s} lastWorking:\n{self._lastWorkingIr}\n broken:\n{str(F):s}")
        self._lastWorkingIr = str(F)

    def _isCurrentlyCompilingTop(self, hls: "HlsScope", toLlvm: ToLlvmIrTranslator):
        return hls.parentHwModule._parent is None and (self._topToRunTestsOn is None or
                                                       self._topToRunTestsOn is toLlvm.parentHwModule)

    @override
    def runSsaPasses(self, hls: "HlsScope", toLlvm: ToLlvmIrTranslator):
        res = super(TestLlvmIrAndMirPlatform, self).runSsaPasses(hls, toLlvm)
        self.toLlvm = toLlvm
        isTop = self._isCurrentlyCompilingTop(hls, toLlvm)
        if isTop:
            # [todo] launch tests only on top function
            if self._noOptIrTest:
                self._runWithTimeLog(self.TIME_LOG_STAGE.NO_OPT_IR, self._noOptIrTest, self, toLlvm)
            llvm: LlvmCompilationBundle = toLlvm.llvm
            if self._runTestAfterEachIrPass:
                llvm.registerAfterPassCallbackForIr(self.runTestAfterPass)
                llvm.registerAfterPassCallbackForMir(self.runTestAfterPass)  # legacy PassManager may also execute IR passes added by TargetPassConfig
            elif self._runTestAfterEachMirPass:
                llvm.registerAfterPassCallbackForMir(self.runTestAfterPass)

        return res

    @override
    def runSsaToNetlist(self, hls:"HlsScope", toLlvm: ToLlvmIrTranslator, netlist: HlsNetlistCtx) -> HlsNetlistCtx:
        try:
            return VirtualHlsPlatform.runSsaToNetlist(self, hls, toLlvm, netlist)
        except IntentionalCompilationInterupt:
            isTop = hls.parentHwModule._parent is None
            if isTop and self._optIrTest:
                # if the compilation was interrupted prematurely (by this debug exception)
                # execute IR tests for debugging purposes
                self._runWithTimeLog(self.TIME_LOG_STAGE.OPT_IR, self._optIrTest, self, toLlvm)
            raise

    @override
    def runMirToHlsNetlist(self,
                      hls: "HlsScope", toLlvm: ToLlvmIrTranslator,
                      *args):
        isTop = self._isCurrentlyCompilingTop(hls, toLlvm)
        if isTop:
            try:
                if self._optIrTest:
                    self._runWithTimeLog(self.TIME_LOG_STAGE.OPT_IR, self._optIrTest, self, toLlvm)
                if self._optMirTest:
                    self._runWithTimeLog(self.TIME_LOG_STAGE.OPT_MIR, self._optMirTest, self, toLlvm)
            except:
                dbg = self._debug.runDebugIfEnabled
                D = HlsDebugBundle
                llvm = toLlvm.llvm
                if llvm.main is None:
                    raise NotImplementedError()
                else:
                    mf = llvm.getMachineFunction(llvm.main)

                dbg(D.DBG_2_0_mir, (toLlvm, mf), applyFnGetter=_runOnSsaModuleGetter)
                dbg(D.DBG_2_0_mirCfg, (toLlvm, mf), applyFnGetter=_runOnSsaModuleGetter)
                raise

        netlist = super(TestLlvmIrAndMirPlatform, self).runMirToHlsNetlist(hls, toLlvm, *args)
        return netlist

    @classmethod
    def forSimpleDataInDataOutHwModule(cls,
                                   prepareDataInFn: Callable[[], Sequence],
                                   checkDataOutFn: Optional[Callable[[Union[List[HConst], List[List[HConst]]]], None]],
                                   logFileNameStem: Optional[Union[Path, str]],
                                   inputCnt=1,
                                   outputCnt=1,
                                   *args, **kwargs):
        """
        This function is a syntax sugar for :class:`~.TestLlvmIrAndMirPlatform` constructor.
        It creates instance which will have generated testing function for LLVM IR and LLVM MIR.
        
        :param prepareDataInFn: function called before each test to generate new test data
        :param checkDataOutFn: function called after function is executed to test if output is correct
        :param inputCnt: number of inputs of tested function (inputs must be at the beginning of parameters)
        :param outputCnt: number of outputs of tested function (outputs must be at the end of parameters)
        :note: for args/kwargs see constructor of this :class:`~.TestLlvmIrAndMirPlatform`
        """
        # [todo] this partially duplicit with BaseIrMirRtl_TC._test_OneInOneOut
        if checkDataOutFn is not None:

            def testLlvmOptIrOrMir(platform: TestLlvmIrAndMirPlatform, toLlvm: ToLlvmIrTranslator, isMir: bool):
                """
                Execute interpret on optimized IR with product of createDataInDataOut function and then call checkDataOutFn  
                """
                dataIn = prepareDataInFn()
                dataOut = []
                args = []

                if inputCnt == 1:
                    args.append(iter(dataIn))
                else:
                    assert len(dataIn) == inputCnt, len(inputCnt)
                    args.extend(iter(d) for d in dataIn)

                if outputCnt == 1:
                    args.append(dataOut)
                else:
                    args.extend([] for _ in range(outputCnt))

                if isMir:
                    interpret = LlvmMirInterpret(toLlvm.llvm, toLlvm.placeholderObjectSlots, platform._componentGenerators, args)
                    waveLogFileName = str(logFileNameStem) + ".llvmMirWave.vcd"
                else:
                    interpret = LlvmIrInterpret(toLlvm.llvm, toLlvm.placeholderObjectSlots, platform._componentGenerators, args)
                    waveLogFileName = str(logFileNameStem) + ".llvmIrWave.vcd"
          
                try:
                    if logFileNameStem is not None:
                        with open(waveLogFileName, "w") as vcdFile:
                            waveLog = VcdWriter(vcdFile)
                            interpret.installWaveLog(waveLog)
                            interpret.run()
                    else:
                        interpret.run()
                except SimIoUnderflowErr:
                    pass
                checkDataOutFn(dataOut)

            def testLlvmOptIr(platform: TestLlvmIrAndMirPlatform, toLlvm: ToLlvmIrTranslator):
                return testLlvmOptIrOrMir(platform, toLlvm, False)

            if kwargs.get("noOptIrTest", None) is cls.TEST_NO_OPT_IR:
                kwargs["noOptIrTest"] = testLlvmOptIr
            if "optIrTest" not in kwargs:
                kwargs["optIrTest"] = testLlvmOptIr
            if "optMirTest" not in kwargs:

                def testLlvmOptMir(platform: TestLlvmIrAndMirPlatform, toLlvm: ToLlvmIrTranslator):
                    return testLlvmOptIrOrMir(platform, toLlvm, True)

                kwargs["optMirTest"] = testLlvmOptMir

        return cls(*args, **kwargs)
