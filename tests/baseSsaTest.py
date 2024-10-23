from io import StringIO
import os
from typing import Set, Tuple, Dict, List

from hwt.hwModule import HwModule
from hwtHls.frontend.ast.astToSsa import HlsAstToSsa
from hwtHls.llvm.llvmIr import MachineFunction, MachineBasicBlock, Register, MachineLoopInfo
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.translation.dumpBlockSync import HlsNetlistAnalysisPassDumpBlockSync
from hwtHls.platform.platform import HlsDebugBundle
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.netlist.analysis.blockSyncType import HlsNetlistAnalysisPassBlockSyncType
from hwtHls.ssa.analysis.consistencyCheck import SsaPassConsistencyCheck
from hwtHls.ssa.translation.dumpMIR import SsaPassDumpMIR
from hwtHls.ssa.translation.llvmMirToNetlist.datapath import BlockLiveInMuxSyncDict
from hwtHls.ssa.translation.llvmMirToNetlist.mirToNetlist import HlsNetlistAnalysisPassMirToNetlist
from hwtHls.ssa.translation.toLl import SsaPassDumpToLl
from hwtHls.ssa.translation.toLlvm import SsaPassToLlvm, ToLlvmIrTranslator
from hwtLib.examples.base_serialization_TC import BaseSerializationTC
from hwtHls.netlist.scheduler.resourceList import initSchedulingResourceConstraintsFromIO


class TestFinishedSuccessfuly(BaseException):

    @classmethod
    def raise_(cls, *args):
        raise cls(*args)


class BaseTestPlatform(VirtualHlsPlatform):

    def __init__(self):
        VirtualHlsPlatform.__init__(self, debugDir=None, debugFilter=HlsDebugBundle.NONE)
        self.postPyOpt = StringIO()
        self.mir = StringIO()
        self.blockSync = StringIO()

    def runSsaPasses(self, hls:"HlsScope", toSsa:HlsAstToSsa):
        SsaPassConsistencyCheck().runOnSsaModule(toSsa)
        SsaPassDumpToLl(lambda name: (self.postPyOpt, False)).runOnSsaModule(toSsa)
        SsaPassToLlvm(hls, self._llvmCliArgs).runOnSsaModule(toSsa)

    def runMirToHlsNetlist(self,
                              hls: "HlsScope", toSsa: HlsAstToSsa, netlist: HlsNetlistCtx,
                              mf: MachineFunction,
                              backedges: Set[Tuple[MachineBasicBlock, MachineBasicBlock]],
                              liveness: Dict[MachineBasicBlock, Dict[MachineBasicBlock, Set[Register]]],
                              ioRegs: List[Register],
                              registerTypes: Dict[Register, int],
                              loops: MachineLoopInfo):
        tr: ToLlvmIrTranslator = toSsa.start
        assert isinstance(tr, ToLlvmIrTranslator), tr
        dbgTracer, doCloseTrace = self._getDebugTracer(netlist.label, HlsDebugBundle.DBG_2_1_netlistConstructionTrace)
        toNetlist = HlsNetlistAnalysisPassMirToNetlist(
            hls, tr, mf, backedges, liveness, ioRegs, registerTypes, loops, netlist, toSsa.ioNodeConstructors, dbgTracer)

        initSchedulingResourceConstraintsFromIO(netlist.scheduler.resourceUsage.resourceConstraints, tr.topIo.keys())

        SsaPassDumpMIR(lambda name: (self.mir, False)).runOnSsaModule(toSsa)

        try:
            toNetlist.translateDatapathInBlocks(mf)

            netlist.getAnalysis(HlsNetlistAnalysisPassBlockSyncType)
            HlsNetlistAnalysisPassDumpBlockSync(lambda name: (self.blockSync, False), addLegend=False).runOnHlsNetlist(netlist)

            blockLiveInMuxInputSync: BlockLiveInMuxSyncDict = toNetlist.constructLiveInMuxes(mf)
            toNetlist.extractRstValues(mf)
            toNetlist.resolveControlForBlockWithChannelLivein(mf, blockLiveInMuxInputSync)
            toNetlist.resolveBlockEn(mf)
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
    TEST_BLOCK_SYNC = True

    def tearDown(self):
        self.rmSim()

    def _runTranslation(self, unit_cls, p: BaseTestPlatform):
        self.rmSim()

        with self.assertRaises(TestFinishedSuccessfuly):
            self.compileSimAndStart(unit_cls, target_platform=p)

        self.rmSim()

    def _test_ll(self, hwModuleConstructor: HwModule, name=None):
        p = BaseTestPlatform()
        # p._llvmCliArgs += [("print-after-all", 0, "", "true"),]
        if isinstance(hwModuleConstructor, HwModule):
            unit = hwModuleConstructor
        else:
            unit = hwModuleConstructor()

        self._runTranslation(unit, p)
        if name is None:
            name = unit.__class__.__name__

        if self.TEST_FRONTEND:
            self.assert_same_as_file(p.postPyOpt.getvalue(), os.path.join("data", name + ".0.postPyOpt.ll"))
        if self.TEST_MIR:
            self.assert_same_as_file(p.mir.getvalue(), os.path.join("data", name + ".1.mir.ll"))
        if self.TEST_BLOCK_SYNC:
            self.assert_same_as_file(p.blockSync.getvalue(), os.path.join("data", name + ".2.blockSync.dot"))

