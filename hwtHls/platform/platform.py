from pathlib import Path
from typing import Optional, Union, Set, Tuple, Dict, List

from hwt.synthesizer.dummyPlatform import DummyPlatform
from hwtHls.llvm.llvmIr import MachineFunction, MachineBasicBlock, Register, MachineLoopInfo
from hwtHls.netlist.allocator.allocator import HlsAllocator
from hwtHls.netlist.analysis.blockSyncType import HlsNetlistAnalysisPassBlockSyncType
from hwtHls.netlist.analysis.consystencyCheck import HlsNetlistPassConsystencyCheck
from hwtHls.netlist.analysis.dataThreads import HlsNetlistAnalysisPassDataThreads
from hwtHls.netlist.analysis.schedule import HlsNetlistAnalysisPassRunScheduler
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.scheduler.scheduler import HlsScheduler
from hwtHls.netlist.transformation.aggregateBitwiseOpsPass import HlsNetlistPassAggregateBitwiseOps
from hwtHls.netlist.transformation.dce import HlsNetlistPassDCE
from hwtHls.netlist.transformation.mergeExplicitSync import HlsNetlistPassMergeExplicitSync
from hwtHls.netlist.transformation.simplify import HlsNetlistPassSimplify
from hwtHls.netlist.translation.dumpBlockSync import HlsNetlistPassDumpBlockSync
from hwtHls.netlist.translation.dumpDataThreads import HlsNetlistPassDumpDataThreads
from hwtHls.netlist.translation.dumpStreamNodes import RtlNetlistPassDumpStreamNodes
from hwtHls.netlist.translation.toGraphwiz import HlsNetlistPassDumpToDot
from hwtHls.netlist.translation.toTimeline import HlsNetlistPassShowTimeline
from hwtHls.netlist.translation.toTimelineArchLevel import HlsNetlistPassShowTimelineArchLevel
from hwtHls.platform.fileUtils import outputFileGetter
from hwtHls.ssa.analysis.consystencyCheck import SsaPassConsystencyCheck
from hwtHls.ssa.transformation.axiStreamReadLowering.axiStreamReadLoweringPass import SsaPassAxiStreamReadLowering
from hwtHls.ssa.transformation.extractPartDrivers.extractPartDriversPass import SsaPassExtractPartDrivers
from hwtHls.ssa.translation.dumpMIR import SsaPassDumpMIR
from hwtHls.frontend.ast.astToSsa import HlsAstToSsa
from hwtHls.ssa.translation.llvmToMirAndMirToHlsNetlist.mirToNetlist import HlsNetlistAnalysisPassMirToNetlist
from hwtHls.ssa.translation.toGraphwiz import SsaPassDumpToDot
from hwtHls.ssa.translation.toLl import SsaPassDumpToLl
from hwtHls.ssa.translation.toLlvm import SsaPassToLlvm, ToLlvmIrTranslator


class DefaultHlsPlatform(DummyPlatform):
    """
    :ivar _debugDir: an optional directory path, if specified the debug log files will be produced
    """

    def __init__(self, debugDir:Optional[Union[str, Path]]=None):
        
        DummyPlatform.__init__(self)
        self.allocator = HlsAllocator
        self.scheduler = HlsScheduler  # HlsScheduler #ForceDirectedScheduler
        self._debugDir = None if debugDir is None else Path(debugDir)
        self._debugExpandCompositeNodes = False

    def runSsaPasses(self, hls: "HlsStreamProc", toSsa: HlsAstToSsa):
        debugDir = self._debugDir
        if debugDir and not debugDir.exists():
            debugDir.mkdir()
        if debugDir:
            SsaPassDumpToDot(outputFileGetter(debugDir, ".0.preSsaOpt.dot"), extractPipeline=False).apply(hls, toSsa)
        
        SsaPassConsystencyCheck().apply(hls, toSsa)
        SsaPassAxiStreamReadLowering().apply(hls, toSsa)
        if debugDir:
            SsaPassDumpToDot(outputFileGetter(debugDir, ".1.frontend.dot"), extractPipeline=False).apply(hls, toSsa)

        SsaPassExtractPartDrivers().apply(hls, toSsa)
        if debugDir:
            SsaPassDumpToDot(outputFileGetter(debugDir, ".2.sliceBreak.dot"), extractPipeline=False).apply(hls, toSsa)

        SsaPassToLlvm().apply(hls, toSsa)
        if debugDir:
            SsaPassDumpToLl(outputFileGetter(debugDir, ".3.preLlvm.ll")).apply(hls, toSsa)
   
    def runSsaToNetlist(self, hls: "HlsStreamProc", toSsa: HlsAstToSsa) -> HlsNetlistCtx:
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
    
            if self._debugDir:
                SsaPassDumpMIR(outputFileGetter(self._debugDir, ".5.mir.ll")).apply(hls, toSsa)
            
            toNetlist._translateDatapathInBlocks(mf)
            toNetlist._constructLiveInMuxes(mf, backedges, liveness)
            # thread analysis must be done before we connect control, because once we do that
            # everything will blend together 
            threads = toNetlist.netlist.requestAnalysis(HlsNetlistAnalysisPassDataThreads)
            toNetlist._updateThreadsOnPhiMuxes(threads)
            if self._debugDir:
                HlsNetlistPassDumpDataThreads(outputFileGetter(self._debugDir, ".6.dthreads.txt")).apply(hls, netlist)

            toNetlist.netlist.requestAnalysis(HlsNetlistAnalysisPassBlockSyncType)
            if self._debugDir:
                HlsNetlistPassDumpBlockSync(outputFileGetter(self._debugDir, ".7.blockSync.txt")).apply(hls, netlist)
                HlsNetlistPassDumpToDot(outputFileGetter(self._debugDir, ".8.preSync.dot")).apply(hls, netlist)

            toNetlist._resolveBlockEn(mf, backedges, threads)
            #toNetlist.netlist.invalidateAnalysis(HlsNetlistAnalysisPassDataThreads)  # because we modified the netlist
            toNetlist._connectOrderingPorts(mf, backedges)

        tr.llvm.runOpt(runNetlistTranslation)
        assert netlist is not None
        
        return netlist

    def runHlsNetlistPasses(self, hls: "HlsStreamProc", netlist: HlsNetlistCtx):
        debugDir = self._debugDir
        if debugDir:
            HlsNetlistPassConsystencyCheck().apply(hls, netlist)
            
        HlsNetlistPassDCE().apply(hls, netlist)
        HlsNetlistPassSimplify().apply(hls, netlist)
        # if debugDir:
        #   HlsNetlistPassDumpToDot(debugDir / "top_p0.dot").apply(hls, pipeline)
           
        HlsNetlistPassMergeExplicitSync().apply(hls, netlist)
        HlsNetlistPassAggregateBitwiseOps().apply(hls, netlist)
        if debugDir:
            # HlsNetlistPassConsystencyCheck().apply(hls, pipeline)
            # HlsNetlistPassDumpToDot(debugDir / "top_p1.dot").apply(hls, pipeline)
            HlsNetlistPassShowTimeline(outputFileGetter(debugDir, ".9.schedule.html"),
                                           expandCompositeNodes=self._debugExpandCompositeNodes).apply(hls, netlist)
        netlist.requestAnalysis(HlsNetlistAnalysisPassRunScheduler)

    def runRtlNetlistPasses(self, hls: "HlsStreamProc", netlist: HlsNetlistCtx):
        debugDir = self._debugDir
        if debugDir:
            RtlNetlistPassDumpStreamNodes(outputFileGetter(debugDir, ".10.sync.txt")).apply(hls, netlist)
            HlsNetlistPassShowTimelineArchLevel(outputFileGetter(debugDir, ".11.archSchedule.html")).apply(hls, netlist)

