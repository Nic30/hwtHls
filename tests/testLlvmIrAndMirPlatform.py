from pathlib import Path
from typing import Optional, Union, Callable, Set

from hwtHls.frontend.ast.astToSsa import HlsAstToSsa
from hwtHls.llvm.llvmIr import LlvmCompilationBundle, MachineFunction
from hwtHls.platform.platform import DebugId, HlsDebugBundle
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.ssa.analysis.llvmIrInterpret import LlvmIrInterpret, \
    SimIoUnderflowErr
from hwtHls.ssa.analysis.llvmMirInterpret import LlvmMirInterpret
from hwtHls.ssa.translation.toLlvm import ToLlvmIrTranslator
from pyDigitalWaveTools.vcd.writer import VcdWriter


class TestLlvmIrAndMirPlatform(VirtualHlsPlatform):

    def __init__(self,
                 noOptIrTest:Optional[Callable[[LlvmCompilationBundle, ], None]]=None,
                 optIrTest:Optional[Callable[[LlvmCompilationBundle, ], None]]=None,
                 optMirTest:Optional[Callable[[LlvmCompilationBundle, ], None]]=None,
                 debugDir:Optional[Union[str, Path]]="tmp",
                 debugFilter:Optional[Set[DebugId]]=HlsDebugBundle.DEFAULT):
        VirtualHlsPlatform.__init__(self, debugDir=debugDir, debugFilter=debugFilter)
        self._noOptIrTest = noOptIrTest
        self._optIrTest = optIrTest
        self._optMirTest = optMirTest

    def runSsaPasses(self, hls: "HlsScope", toSsa: HlsAstToSsa):
        res = super(TestLlvmIrAndMirPlatform, self).runSsaPasses(hls, toSsa)
        tr: ToLlvmIrTranslator = toSsa.start
        if self._noOptIrTest:
            self._noOptIrTest(tr.llvm)
        return res

    def runNetlistTranslation(self,
                      hls: "HlsScope", toSsa: HlsAstToSsa,
                      MF: MachineFunction, *args):
        tr: ToLlvmIrTranslator = toSsa.start
        if self._optIrTest:
            self._optIrTest(tr.llvm)
        if self._optMirTest:
            self._optMirTest(tr.llvm)
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
        return cls(*args, **kwargs)
