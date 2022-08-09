from pathlib import Path
from typing import Optional, Union, Set, Tuple, Dict, List

from hwt.synthesizer.dummyPlatform import DummyPlatform
from hwtHls.architecture.allocator import HlsAllocator
from hwtHls.architecture.interArchElementNodeSharingAnalysis import InterArchElementNodeSharingAnalysis
from hwtHls.architecture.transformation.controlLogicMinimize import RtlNetlistPassControlLogicMinimize
from hwtHls.architecture.transformation.singleStagePipelineToFsm import RtlArchPassSingleStagePipelineToFsm
from hwtHls.architecture.translation.dumpStreamNodes import RtlNetlistPassDumpStreamNodes
from hwtHls.architecture.translation.toGraphwiz import RtlArchPassToGraphwiz
from hwtHls.architecture.translation.toTimeline import RtlArchPassShowTimeline
from hwtHls.frontend.ast.astToSsa import HlsAstToSsa
from hwtHls.llvm.llvmIr import MachineFunction, MachineBasicBlock, Register, MachineLoopInfo
from hwtHls.netlist.analysis.blockSyncType import HlsNetlistAnalysisPassBlockSyncType
from hwtHls.netlist.analysis.consystencyCheck import HlsNetlistPassConsystencyCheck
from hwtHls.netlist.analysis.dataThreads import HlsNetlistAnalysisPassDataThreads
from hwtHls.netlist.analysis.schedule import HlsNetlistAnalysisPassRunScheduler
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.scheduler.scheduler import HlsScheduler
from hwtHls.netlist.transformation.aggregateBitwiseOpsPass import HlsNetlistPassAggregateBitwiseOps
from hwtHls.netlist.transformation.mergeExplicitSync import HlsNetlistPassMergeExplicitSync
from hwtHls.netlist.transformation.simplify import HlsNetlistPassSimplify
from hwtHls.netlist.translation.dumpBlockSync import HlsNetlistPassDumpBlockSync
from hwtHls.netlist.translation.dumpDataThreads import HlsNetlistPassDumpDataThreads
from hwtHls.netlist.translation.toGraphwiz import HlsNetlistPassDumpToDot
from hwtHls.netlist.translation.toTimeline import HlsNetlistPassShowTimeline
from hwtHls.platform.fileUtils import outputFileGetter
from hwtHls.ssa.analysis.consystencyCheck import SsaPassConsystencyCheck
from hwtHls.ssa.transformation.axiStreamReadLowering.axiStreamReadLoweringPass import SsaPassAxiStreamReadLowering
from hwtHls.ssa.transformation.extractPartDrivers.extractPartDriversPass import SsaPassExtractPartDrivers
from hwtHls.ssa.translation.dumpMIR import SsaPassDumpMIR
from hwtHls.ssa.translation.dumpMirCfg import SsaPassDumpMirCfg
from hwtHls.ssa.translation.llvmToMirAndMirToHlsNetlist.datapath import BlockLiveInMuxSyncDict
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

    def runSsaPasses(self, hls: "HlsScope", toSsa: HlsAstToSsa):
        debugDir = self._debugDir
        if debugDir and not debugDir.exists():
            debugDir.mkdir()
        if debugDir:
            SsaPassDumpToDot(outputFileGetter(debugDir, ".0.preSsaOpt.dot"), extractPipeline=False).apply(hls, toSsa)
        
        SsaPassConsystencyCheck().apply(hls, toSsa)
        SsaPassAxiStreamReadLowering().apply(hls, toSsa)
        SsaPassAxiStreamWriteLowering().apply(hls, toSsa)
        if debugDir:
            SsaPassDumpToDot(outputFileGetter(debugDir, ".1.frontend.dot"), extractPipeline=False).apply(hls, toSsa)

        SsaPassExtractPartDrivers().apply(hls, toSsa)
        if debugDir:
            SsaPassDumpToDot(outputFileGetter(debugDir, ".2.sliceBreak.dot"), extractPipeline=False).apply(hls, toSsa)

        SsaPassToLlvm().apply(hls, toSsa)
        if debugDir:
            SsaPassDumpToLl(outputFileGetter(debugDir, ".3.preLlvm.ll")).apply(hls, toSsa)
   
    def runSsaToNetlist(self, hls: "HlsScope", toSsa: HlsAstToSsa) -> HlsNetlistCtx:
        tr: ToLlvmIrTranslator = toSsa.start
        assert isinstance(tr, ToLlvmIrTranslator), tr
        netlist = tr.llvm.runOpt(self.runNetlistTranslation, hls, toSsa)
        assert netlist is not None
        return netlist

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
        debugDir = self._debugDir
        if debugDir:
            SsaPassDumpMIR(outputFileGetter(debugDir, ".5.mir.ll")).apply(hls, toSsa)
            SsaPassDumpMirCfg(outputFileGetter(debugDir, ".5.mirCfg.dot")).apply(hls, toSsa)
        
        toNetlist._translateDatapathInBlocks(mf, toSsa.ioNodeConstructors)
        blockLiveInMuxInputSync: BlockLiveInMuxSyncDict = toNetlist._constructLiveInMuxes(mf, backedges, liveness)
        # thread analysis must be done before we connect control, because once we do that
        # everything will blend together 
        threads = toNetlist.netlist.getAnalysis(HlsNetlistAnalysisPassDataThreads)
        toNetlist._updateThreadsOnPhiMuxes(threads)
        if debugDir:
            HlsNetlistPassDumpDataThreads(outputFileGetter(debugDir, ".6.dthreads.txt")).apply(hls, netlist)

        toNetlist.netlist.getAnalysis(HlsNetlistAnalysisPassBlockSyncType)
        if debugDir:
            HlsNetlistPassDumpBlockSync(outputFileGetter(debugDir, ".7.blockSync.dot")).apply(hls, netlist)
            HlsNetlistPassDumpToDot(outputFileGetter(debugDir, ".8.preSync.dot")).apply(hls, netlist)

        toNetlist._extractRstValues(mf, threads)
        if debugDir:
            HlsNetlistPassDumpToDot(outputFileGetter(debugDir, ".8.postRst.dot")).apply(hls, netlist)
        toNetlist._resolveLoopHeaders(mf, blockLiveInMuxInputSync)
        if debugDir:
            HlsNetlistPassDumpToDot(outputFileGetter(debugDir, ".8.postLoop.dot")).apply(hls, netlist)

        toNetlist._resolveBlockEn(mf, backedges, threads)
        # toNetlist.netlist.invalidateAnalysis(HlsNetlistAnalysisPassDataThreads)  # because we modified the netlist
        toNetlist._connectOrderingPorts(mf, backedges)
        if debugDir:
            HlsNetlistPassDumpBlockSync(outputFileGetter(debugDir, ".9.postSync.dot")).apply(hls, netlist)

        return netlist

    def runHlsNetlistPasses(self, hls: "HlsScope", netlist: HlsNetlistCtx):
        """
        :note: now we can not touch MIR because it was deallocated
        """
        debugDir = self._debugDir
        if debugDir and not debugDir.exists():
            debugDir.mkdir()
        if debugDir:
            HlsNetlistPassDumpToDot(outputFileGetter(debugDir, ".10.netlist.dot")).apply(hls, netlist)
            HlsNetlistPassConsystencyCheck().apply(hls, netlist)
            
        HlsNetlistPassSimplify().apply(hls, netlist)
        
        if debugDir:
            HlsNetlistPassDumpToDot(outputFileGetter(debugDir, ".11.netlistSimplified.dot")).apply(hls, netlist)
            HlsNetlistPassConsystencyCheck().apply(hls, netlist)
           
        HlsNetlistPassMergeExplicitSync().apply(hls, netlist)
        HlsNetlistPassAggregateBitwiseOps().apply(hls, netlist)
        if debugDir:
            HlsNetlistPassDumpToDot(outputFileGetter(debugDir, ".12.netlistAggregated.dot")).apply(hls, netlist)
            HlsNetlistPassShowTimeline(outputFileGetter(debugDir, ".13.schedule.html"),
                                      expandCompositeNodes=self._debugExpandCompositeNodes).apply(hls, netlist)
            HlsNetlistPassConsystencyCheck().apply(hls, netlist)

        netlist.getAnalysis(HlsNetlistAnalysisPassRunScheduler)

    def runHlsNetlistToRtlNetlist(self, hls: "HlsScope", netlist: HlsNetlistCtx):
        """
        Translate scheduled circuit to RTL
        
        Problems:

          1. When resolving logic in clock cycle we do not know about registers which will be constructed later.
             Because we did not seen use of this value yet.
          
          2. If the node spans over multiple clock cycles and some part is not in this arch element
              we do not know about it explicitly from node list.
          
          3. We can not just insert register object because it does not solve nodes spanning multiple clock cycles.
        
        * We walk the netlist and discover in which time the value is live (in netlist format the connection could lead to any time)
          and we need to find out in which times we should construct registers and most importantly in which arch. element we should construct them.

        * For each node which is crossing arch element boundary or spans multiple cycles we also have mark the individual parts for clock cycles
          if the node is crossing arch. elem. boundary we also must ask it to declare its io so the node can be constructed from any 
          arch element.

        * First arch element which sees the node allocates it, the allocation is marked in allocator and happens only once.

        * Each arch element explicitly queries the node for the specific time (and input/output combination if node spans over more arch. elements).
        """
        allocator = netlist.allocator
        allocator._discoverArchElements()
        
        RtlArchPassSingleStagePipelineToFsm().apply(self, allocator)
        
        iea = InterArchElementNodeSharingAnalysis(netlist.normalizedClkPeriod)
        allocator._iea = iea         
        if len(allocator._archElements) > 1:
            iea._analyzeInterElementsNodeSharing(allocator._archElements)
            if iea.interElemConnections:  # it could be the case that the elements are completely independent
                allocator.declareInterElemenetBoundarySignals(iea)

        for e in allocator._archElements:
            e.allocateDataPath(iea)

        if iea.interElemConnections:
            allocator.finalizeInterElementsConnections(iea)
        # :note: must be after finalizeInterElementsConnections because it needs inter element sync channels
        # RtlArchPassFsmShareTiedStateTransitions().apply(self, allocator)
        if self._debugDir:
            RtlArchPassToGraphwiz(outputFileGetter(self._debugDir, ".14.arch.dot")).apply(hls, netlist)
        for e in allocator._archElements:
            e.allocateSync()

    def runRtlNetlistPasses(self, hls: "HlsScope", netlist: HlsNetlistCtx):
        debugDir = self._debugDir
        RtlNetlistPassControlLogicMinimize().apply(hls, netlist)
        if debugDir:
            RtlNetlistPassDumpStreamNodes(outputFileGetter(debugDir, ".15.sync.txt")).apply(hls, netlist)
            RtlArchPassShowTimeline(outputFileGetter(debugDir, ".16.archSchedule.html")).apply(hls, netlist)

