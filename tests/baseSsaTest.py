from io import StringIO
import os
from typing import Set, Tuple, Dict, List

from hwt.synthesizer.unit import Unit
from hwtHls.llvm.llvmIr import MachineFunction, MachineBasicBlock, Register, MachineLoopInfo
from hwtHls.netlist.analysis.blockSyncType import HlsNetlistAnalysisPassBlockSyncType
from hwtHls.netlist.analysis.dataThreads import HlsNetlistAnalysisPassDataThreads
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.translation.dumpBlockSync import HlsNetlistPassDumpBlockSync
from hwtHls.netlist.translation.dumpDataThreads import HlsNetlistPassDumpDataThreads
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.ssa.analysis.consystencyCheck import SsaPassConsystencyCheck
from hwtHls.ssa.analysis.dumpMIR import SsaPassDumpMIR
from hwtHls.ssa.transformation.extractPartDrivers.extractPartDriversPass import SsaPassExtractPartDrivers
from hwtHls.ssa.transformation.runFn import SsaPassRunFn
from hwtHls.ssa.translation.fromAst.astToSsa import AstToSsa
from hwtHls.ssa.translation.llvmToMirAndMirToHlsNetlist.mirToNetlist import HlsNetlistAnalysisPassMirToNetlist
from hwtHls.ssa.translation.toLl import SsaPassDumpToLl
from hwtHls.ssa.translation.toLlvm import SsaPassToLlvm, ToLlvmIrTranslator
from hwtLib.examples.base_serialization_TC import BaseSerializationTC


class TestFinishedSuccessfuly(BaseException):

    @classmethod
    def raise_(cls, *args):
        raise cls(*args)


class BaseTestPlatform(VirtualHlsPlatform):

    def __init__(self):
        VirtualHlsPlatform.__init__(self, debugDir=None)
        self.preOpt = StringIO()
        self.postPyOpt = StringIO()
        self.mir = StringIO()
        self.dataThreads = StringIO()
        self.blockSync = StringIO()

    def runSsaPasses(self, hls:"HlsStreamProc", toSsa:AstToSsa):
        SsaPassConsystencyCheck().apply(hls, toSsa)
        SsaPassDumpToLl(lambda name: (self.preOpt, False)).apply(hls, toSsa)
        SsaPassExtractPartDrivers().apply(hls, toSsa)
        SsaPassConsystencyCheck().apply(hls, toSsa)
        SsaPassDumpToLl(lambda name: (self.postPyOpt, False)).apply(hls, toSsa)
        SsaPassToLlvm().apply(hls, toSsa)

    def runSsaToNetlist(self, hls:"HlsStreamProc", toSsa:AstToSsa) -> HlsNetlistCtx:
        tr: ToLlvmIrTranslator = toSsa.start
        assert isinstance(tr, ToLlvmIrTranslator), tr
        netlist = None

        def runNetlistTranslation(mf: MachineFunction,
                     backedges: Set[Tuple[MachineBasicBlock, MachineBasicBlock]],
                     liveness: Dict[MachineBasicBlock, Dict[MachineBasicBlock, Set[Register]]],
                     ioRegs: List[Register],
                     registerTypes: Dict[Register, int],
                     loops: MachineLoopInfo):
            nonlocal netlist
            toNetlist = HlsNetlistAnalysisPassMirToNetlist(
                hls, tr, mf, backedges, liveness, ioRegs, registerTypes, loops)
            netlist = toNetlist.netlist
    
            SsaPassDumpMIR(lambda name: (self.mir, False)).apply(hls, toSsa)
            
            toNetlist._translateDatapathInBlocks(mf)
            toNetlist._constructLiveInMuxes(mf, backedges, liveness)
            # thread analysis must be done before we connect control, because once we do that
            # everything will blend together 
            threads = toNetlist.netlist.requestAnalysis(HlsNetlistAnalysisPassDataThreads)
            toNetlist._updateThreadsOnPhiMuxes(threads)
            HlsNetlistPassDumpDataThreads(lambda name: (self.dataThreads, False)).apply(hls, netlist)

            toNetlist.netlist.requestAnalysis(HlsNetlistAnalysisPassBlockSyncType)
            HlsNetlistPassDumpBlockSync(lambda name: (self.blockSync, False)).apply(hls, netlist)

            toNetlist._resolveBlockEn(mf, backedges, threads)
            toNetlist.netlist.invalidateAnalysis(HlsNetlistAnalysisPassDataThreads)  # because we modified the netlist
            toNetlist._connectOrderingPorts(mf, backedges)

        tr.llvm.runOpt(runNetlistTranslation)
        assert netlist is not None
        
        return netlist

    def runHlsNetlistPasses(self, hls:"HlsStreamProc", netlist:HlsNetlistCtx):
        raise TestFinishedSuccessfuly()


class BaseSsaTC(BaseSerializationTC):
    """
    :attention: you need to specify __FILE__ = __file__ on each subclass to resolve paths to files
    """

    def tearDown(self):
        self.rmSim()

    def _runTranslation(self, unit_cls, p: BaseTestPlatform):
        self.rmSim()
        with self.assertRaises(TestFinishedSuccessfuly):
            self.compileSimAndStart(unit_cls, target_platform=p)
        self.rmSim()

    def _test_ll(self, unit_constructor: Unit, name=None):
        p = BaseTestPlatform()
        unit = unit_constructor()
        self._runTranslation(unit, p)
        if name is None:
            name = unit.__class__.__name__
        
        self.assert_same_as_file(p.preOpt, os.path.join("data", name + ".0.preOpt.ll"))
        self.assert_same_as_file(p.postPyOpt, os.path.join("data", name + ".1.postPyOpt.ll"))
        self.assert_same_as_file(p.mir, os.path.join("data", name + ".0.mir.ll"))
        self.assert_same_as_file(p.dataThreads, os.path.join("data", name + ".0.dataThreads.ll"))
        self.assert_same_as_file(p.blockSync, os.path.join("data", name + ".0.blockSync.ll"))
        
