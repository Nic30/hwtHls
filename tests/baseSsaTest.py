from io import StringIO
import os
from typing import Set, Tuple, Dict, List

from hwt.synthesizer.unit import Unit
from hwtHls.frontend.ast.astToSsa import HlsAstToSsa
from hwtHls.llvm.llvmIr import MachineFunction, MachineBasicBlock, Register, MachineLoopInfo
from hwtHls.netlist.analysis.dataThreadsForBlocks import HlsNetlistAnalysisPassDataThreadsForBlocks
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.translation.dumpBlockSync import HlsNetlistPassDumpBlockSync
from hwtHls.netlist.translation.dumpDataThreads import HlsNetlistPassDumpDataThreads
from hwtHls.platform.platform import HlsDebugBundle
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.netlist.analysis.blockSyncType import HlsNetlistAnalysisPassBlockSyncType
from hwtHls.ssa.analysis.consystencyCheck import SsaPassConsystencyCheck
from hwtHls.ssa.translation.dumpMIR import SsaPassDumpMIR
from hwtHls.ssa.translation.llvmMirToNetlist.datapath import BlockLiveInMuxSyncDict
from hwtHls.ssa.translation.llvmMirToNetlist.mirToNetlist import HlsNetlistAnalysisPassMirToNetlist
from hwtHls.ssa.translation.toLl import SsaPassDumpToLl
from hwtHls.ssa.translation.toLlvm import SsaPassToLlvm, ToLlvmIrTranslator
from hwtLib.examples.base_serialization_TC import BaseSerializationTC


class TestFinishedSuccessfuly(BaseException):

    @classmethod
    def raise_(cls, *args):
        raise cls(*args)


class BaseTestPlatform(VirtualHlsPlatform):

    def __init__(self):
        VirtualHlsPlatform.__init__(self, debugDir=None, debugFilter=HlsDebugBundle.NONE)
        self.postPyOpt = StringIO()
        self.mir = StringIO()
        self.dataThreads = StringIO()
        self.blockSync = StringIO()

    def runSsaPasses(self, hls:"HlsScope", toSsa:HlsAstToSsa):
        SsaPassConsystencyCheck().apply(hls, toSsa)
        SsaPassDumpToLl(lambda name: (self.postPyOpt, False)).apply(hls, toSsa)
        SsaPassToLlvm(self._llvmCliArgs).apply(hls, toSsa)

    def runNetlistTranslation(self,
                              hls: "HlsScope", toSsa: HlsAstToSsa,
                              mf: MachineFunction,
                              backedges: Set[Tuple[MachineBasicBlock, MachineBasicBlock]],
                              liveness: Dict[MachineBasicBlock, Dict[MachineBasicBlock, Set[Register]]],
                              ioRegs: List[Register],
                              registerTypes: Dict[Register, int],
                              loops: MachineLoopInfo):
        tr: ToLlvmIrTranslator = toSsa.start
        assert isinstance(tr, ToLlvmIrTranslator), tr
        toNetlist = HlsNetlistAnalysisPassMirToNetlist(
            hls, tr, mf, backedges, liveness, ioRegs, registerTypes, loops)
        netlist = toNetlist.netlist
        dbgTracer, doCloseTrace = self._getDebugTracer(netlist, HlsDebugBundle.DBG_5_netlistConsttructionTrace)
        toNetlist.setDebugTracer(dbgTracer)
        
        SsaPassDumpMIR(lambda name: (self.mir, False)).apply(hls, toSsa)

        try:
            toNetlist.translateDatapathInBlocks(mf, toSsa.ioNodeConstructors)
            threads = netlist.getAnalysis(HlsNetlistAnalysisPassDataThreadsForBlocks)
            toNetlist.updateThreadsOnLiveInMuxes(threads)
            HlsNetlistPassDumpDataThreads(lambda name: (self.dataThreads, False)).apply(hls, netlist)
    
            netlist.getAnalysis(HlsNetlistAnalysisPassBlockSyncType)
            HlsNetlistPassDumpBlockSync(lambda name: (self.blockSync, False), addLegend=False).apply(hls, netlist)
    
            blockLiveInMuxInputSync: BlockLiveInMuxSyncDict = toNetlist.constructLiveInMuxes(mf)
            toNetlist.extractRstValues(mf, threads)
            toNetlist.resolveLoopControl(mf, blockLiveInMuxInputSync)
            toNetlist.resolveBlockEn(mf, threads)
            toNetlist.netlist.invalidateAnalysis(HlsNetlistAnalysisPassDataThreadsForBlocks)  # because we modified the netlist
            toNetlist.connectOrderingPorts(mf)
        finally:
            if doCloseTrace:
                dbgTracer._out.close()

        return netlist

    def runHlsNetlistPasses(self, hls:"HlsScope", netlist:HlsNetlistCtx):
        raise TestFinishedSuccessfuly()


class BaseSsaTC(BaseSerializationTC):
    """
    :attention: you need to specify __FILE__ = __file__ on each subclass to resolve paths to files
    """
    TEST_FRONTEND = True
    TEST_MIR = True
    TEST_THREADS_AND_SYNC = True

    def tearDown(self):
        self.rmSim()

    def _runTranslation(self, unit_cls, p: BaseTestPlatform):
        self.rmSim()

        with self.assertRaises(TestFinishedSuccessfuly):
            self.compileSimAndStart(unit_cls, target_platform=p)

        self.rmSim()

    def _test_ll(self, unitConstructor: Unit, name=None):
        p = BaseTestPlatform()
        if isinstance(unitConstructor, Unit):
            unit = unitConstructor
        else:
            unit = unitConstructor()

        self._runTranslation(unit, p)
        if name is None:
            name = unit.__class__.__name__

        if self.TEST_FRONTEND:
            self.assert_same_as_file(p.postPyOpt.getvalue(), os.path.join("data", name + ".0.postPyOpt.ll"))
        if self.TEST_MIR:
            self.assert_same_as_file(p.mir.getvalue(), os.path.join("data", name + ".1.mir.ll"))
        if self.TEST_THREADS_AND_SYNC:
            self.assert_same_as_file(p.dataThreads.getvalue(), os.path.join("data", name + ".2.dataThreads.txt"))
            self.assert_same_as_file(p.blockSync.getvalue(), os.path.join("data", name + ".3.blockSync.dot"))

