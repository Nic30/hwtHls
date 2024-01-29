from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Optional, Union, Callable, Set

from hwtHls.frontend.ast.astToSsa import HlsAstToSsa
from hwtHls.llvm.llvmIr import LlvmCompilationBundle, MachineFunction, IntentionalCompilationInterupt
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.platform.platform import DebugId, HlsDebugBundle
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.ssa.analysis.llvmIrInterpret import LlvmIrInterpret, \
    SimIoUnderflowErr
from hwtHls.ssa.analysis.llvmMirInterpret import LlvmMirInterpret
from hwtHls.ssa.translation.toLlvm import ToLlvmIrTranslator
from pyDigitalWaveTools.vcd.writer import VcdWriter


class TestLlvmIrAndMirPlatform(VirtualHlsPlatform):

    class TEST_NO_OPT_IR:
        """
        This is a constant used for :meth:`TestLlvmIrAndMirPlatform.forSimpleDataInDataOutUnit` to automatically generate
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
                 noOptIrTest:Optional[Callable[[LlvmCompilationBundle, ], None]]=None,
                 optIrTest:Optional[Callable[[LlvmCompilationBundle, ], None]]=None,
                 optMirTest:Optional[Callable[[LlvmCompilationBundle, ], None]]=None,
                 debugDir:Optional[Union[str, Path]]="tmp",
                 debugFilter:Optional[Set[DebugId]]=HlsDebugBundle.DEFAULT,
                 debugLogTime: Optional[Callable[[TIME_LOG_STAGE, timedelta], None]]=None):
        VirtualHlsPlatform.__init__(self, debugDir=debugDir, debugFilter=debugFilter)
        self._debugLogTime = debugLogTime
        self._noOptIrTest = noOptIrTest
        self._optIrTest = optIrTest
        self._optMirTest = optMirTest

    def _runWithTimeLog(self, stage: TIME_LOG_STAGE, fn: Callable[[LlvmCompilationBundle, ], None], *args, **kwargs):
        if self._debugLogTime:
            time0 = datetime.now()
        fn(*args, **kwargs)
        if self._debugLogTime:
            time1 = datetime.now()
            self._debugLogTime(stage, time1 - time0)

    def runSsaPasses(self, hls: "HlsScope", toSsa: HlsAstToSsa):
        res = super(TestLlvmIrAndMirPlatform, self).runSsaPasses(hls, toSsa)
        tr: ToLlvmIrTranslator = toSsa.start
        if self._noOptIrTest:
            self._runWithTimeLog(self.TIME_LOG_STAGE.NO_OPT_IR, self._noOptIrTest, tr.llvm)

        return res

    def runSsaToNetlist(self, hls:"HlsScope", toSsa:HlsAstToSsa) -> HlsNetlistCtx:
        try:
            return VirtualHlsPlatform.runSsaToNetlist(self, hls, toSsa)
        except IntentionalCompilationInterupt:
            tr: ToLlvmIrTranslator = toSsa.start
            if self._optIrTest:
                # if the compilation was interrupted prematurely (by this debug exception)
                # execute IR tests for debugging purposes
                self._runWithTimeLog(self.TIME_LOG_STAGE.OPT_IR, self._optIrTest, tr.llvm)
            raise

    def runNetlistTranslation(self,
                      hls: "HlsScope", toSsa: HlsAstToSsa,
                      MF: MachineFunction, *args):
        tr: ToLlvmIrTranslator = toSsa.start
        try:
            if self._optIrTest:
                self._runWithTimeLog(self.TIME_LOG_STAGE.OPT_IR, self._optIrTest, tr.llvm)
            if self._optMirTest:
                self._runWithTimeLog(self.TIME_LOG_STAGE.OPT_MIR, self._optMirTest, tr.llvm)
        except:
            dbg = self._debug.runDebugIfEnabled
            D = HlsDebugBundle
            dbg(D.DBG_3_mir, (hls, toSsa))
            dbg(D.DBG_4_mirCfg, (hls, toSsa))
            raise

        netlist = super(TestLlvmIrAndMirPlatform, self).runNetlistTranslation(hls, toSsa, MF, *args)
        return netlist

    @classmethod
    def forSimpleDataInDataOutUnit(cls,
                                   prepareDataInFn: Callable[[], None],
                                   checkDataOutFn: Callable[[], None],
                                   logFileNameStem: Optional[Union[Path, str]], *args, **kwargs):

        def testLlvmOptIr(llvm: LlvmCompilationBundle):
            dataIn = prepareDataInFn()
            dataOut = []
            args = [iter(dataIn), dataOut]
            interpret = LlvmIrInterpret(llvm.main)
            try:
                if logFileNameStem is not None:
                    with open(str(logFileNameStem) + ".llvmIrWave.vcd", "w") as vcdFile:
                        waveLog = VcdWriter(vcdFile)
                        interpret.installWaveLog(waveLog, llvm.strCtx)
                        interpret.run(args)
                else:
                    interpret.run(args)
            except SimIoUnderflowErr:
                pass
            checkDataOutFn(dataOut)

        def testLlvmOptMir(llvm: LlvmCompilationBundle):
            dataIn = prepareDataInFn()
            dataOut = []
            args = [iter(dataIn), dataOut]
            interpret = LlvmMirInterpret(llvm.getMachineFunction(llvm.main))
            try:
                if logFileNameStem is not None:
                    with open(str(logFileNameStem) + ".llvmMirWave.vcd", "w") as vcdFile:
                        waveLog = VcdWriter(vcdFile)
                        interpret.installWaveLog(waveLog, llvm.strCtx)
                        interpret.run(args)
                else:
                    interpret.run(args)
            except SimIoUnderflowErr:
                pass
            checkDataOutFn(dataOut)

        if "optIrTest" not in kwargs:
            kwargs["optIrTest"] = testLlvmOptIr
        if "optMirTest" not in kwargs:
            kwargs["optMirTest"] = testLlvmOptMir
        if kwargs.get("noOptIrTest", None) is cls.TEST_NO_OPT_IR:
            kwargs["noOptIrTest"] = testLlvmOptIr

        return cls(*args, **kwargs)
