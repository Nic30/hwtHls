from pathlib import Path
from typing import Optional, Union, Set, Tuple, Dict, List, Type

from hwt.synthesizer.dummyPlatform import DummyPlatform
from hwtHls.architecture.allocator import HlsAllocator
from hwtHls.architecture.interArchElementNodeSharingAnalysis import InterArchElementNodeSharingAnalysis
from hwtHls.architecture.transformation.controlLogicMinimize import RtlNetlistPassControlLogicMinimize
from hwtHls.architecture.transformation.ioPortPrivatization import RtlArchPassIoPortPrivatization
from hwtHls.architecture.transformation.loopControlPrivatization import RtlArchPassLoopControlPrivatization
from hwtHls.architecture.transformation.singleStagePipelineToFsm import RtlArchPassSingleStagePipelineToFsm
from hwtHls.architecture.translation.dumpStreamNodes import RtlNetlistPassDumpStreamNodes
from hwtHls.architecture.translation.toGraphwiz import RtlArchPassToGraphwiz
from hwtHls.architecture.translation.toTimeline import RtlArchPassShowTimeline
from hwtHls.frontend.ast.astToSsa import HlsAstToSsa
from hwtHls.llvm.llvmIr import MachineFunction, MachineBasicBlock, Register, MachineLoopInfo
from hwtHls.netlist.analysis.blockSyncType import HlsNetlistAnalysisPassBlockSyncType
from hwtHls.netlist.analysis.consystencyCheck import HlsNetlistPassConsystencyCheck
from hwtHls.netlist.analysis.dataThreadsForBlocks import HlsNetlistAnalysisPassDataThreadsForBlocks
from hwtHls.netlist.analysis.schedule import HlsNetlistAnalysisPassRunScheduler
from hwtHls.netlist.analysis.syncReach import HlsNetlistAnalysisPassSyncReach
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.scheduler.scheduler import HlsScheduler
from hwtHls.netlist.transformation.aggregateBitwiseOps import HlsNetlistPassAggregateBitwiseOps
from hwtHls.netlist.transformation.aggregateIoSyncScc import HlsNetlistPassAggregateIoSyncSccs
from hwtHls.netlist.transformation.disaggregateAggregates import HlsNetlistPassDisaggregateAggregates
from hwtHls.netlist.transformation.injectVldMaskToSkipWhenConditions import HlsNetlistPassInjectVldMaskToSkipWhenConditions
from hwtHls.netlist.transformation.simplify import HlsNetlistPassSimplify
from hwtHls.netlist.translation.dumpBlockSync import HlsNetlistPassDumpBlockSync
from hwtHls.netlist.translation.dumpDataThreads import HlsNetlistPassDumpDataThreads
from hwtHls.netlist.translation.dumpNodes import HlsNetlistPassDumpNodes
from hwtHls.netlist.translation.syncDomainsToGraphwiz import HlsNetlistPassSyncDomainsToGraphwiz
from hwtHls.netlist.translation.syncReachToGraphwiz import HlsNetlistPassSyncReachToGraphwiz
from hwtHls.netlist.translation.toGraphwiz import HlsNetlistPassDumpToDot
from hwtHls.netlist.translation.toTimelineJson import HlsNetlistPassShowTimelineJson
from hwtHls.platform.fileUtils import outputFileGetter
from hwtHls.ssa.analysis.consystencyCheck import SsaPassConsystencyCheck
from hwtHls.ssa.transformation.axiStreamLowering.axiStreamReadLoweringPass import SsaPassAxiStreamReadLowering
from hwtHls.ssa.transformation.axiStreamLowering.axiStreamWriteLowering import SsaPassAxiStreamWriteLowering
from hwtHls.ssa.translation.dumpMIR import SsaPassDumpMIR
from hwtHls.ssa.translation.dumpMirCfg import SsaPassDumpMirCfg
from hwtHls.ssa.translation.llvmMirToNetlist.datapath import BlockLiveInMuxSyncDict
from hwtHls.ssa.translation.llvmMirToNetlist.mirToNetlist import HlsNetlistAnalysisPassMirToNetlist
from hwtHls.ssa.translation.toGraphwiz import SsaPassDumpToDot
from hwtHls.ssa.translation.toLl import SsaPassDumpToLl
from hwtHls.ssa.translation.toLlvm import SsaPassToLlvm, ToLlvmIrTranslator
from hwtHls.netlist.transformation.constNodeDuplication import HlsNetlistPassConstNodeDuplication
from hwtHls.netlist.transformation.readSyncToAckOfIoNodes import HlsNetlistPassReadSyncToAckOfIoNodes
from hwtHls.architecture.transformation.archElementsToSubunits import RtlArchPassTransplantArchElementsToSubunits
from hwtHls.netlist.transformation.postSchedluling.postSchedulingChannelMerging import HlsNetlistPassPostSchedulingChannelMerge
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.architecture.transformation.addSyncSigNames import RtlNetlistPassAddSyncSigNames
DebugId = Tuple[Type, Optional[str]]


class HlsDebugBundle():
    DBG_0_preSsaOpt = (SsaPassDumpToDot, ".0.preSsaOpt.dot")  # raw input code
    DBG_1_frontend = (SsaPassDumpToDot, ".1.frontend.dot")  # after frontend transformations
    DBG_2_preLlvm = (SsaPassDumpToLl, ".2.preLlvm.ll")  # translated to LLVM IR
    DBG_3_mir = (SsaPassDumpMIR, ".3.mir.ll")  # translated and optimized to LLVM MIR by LLVM
    DBG_4_mirCfg = (SsaPassDumpMirCfg, ".4.mirCfg.dot")  # Control Flow Graph of MIR
    DBG_5_dthreads = (HlsNetlistPassDumpDataThreads, ".5.dthreads.txt")  # instructions packed in data treads
    DBG_6_blockSync = (HlsNetlistPassDumpBlockSync, ".6.blockSync.dot")  # synchronization features of basic blocks
    DBG_7_preSync = (HlsNetlistPassDumpToDot, ".7.preSync.dot")  # io of basic blocks before implementation of sync
    DBG_8_postRst = (HlsNetlistPassDumpToDot, ".8.postRst.dot")  # basic block io after implementation of reset value extraction
    DBG_9_postLoop = (HlsNetlistPassDumpToDot, ".9.postLoop.dot")  # basic block io after implementation of loops
    DBG_10_postSync = (HlsNetlistPassDumpBlockSync, ".10.postSync.dot")  # basic block io after implementation of complete control flow sync
    DBG_11_netlist = (HlsNetlistPassDumpToDot, ".11.netlist.dot")  # basic blocks disolved to netlist
    DBG_12_nodes = (HlsNetlistPassDumpNodes, ".11.netlist.txt")  # same as DBG_11_netlist just in txt
    DBG_12_netlistSimplifyTrace = (None, ".12.netlistSimplifyTrace.txt")  # trace of netlist simplifier
    DBG_12_netlistSimplifiedErr = (HlsNetlistPassDumpToDot, ".12.err.netlistSimplified.dot")  # try to dump netlist if simplified failed
    DBG_13_netlistSimplifiedErr = (HlsNetlistPassDumpToDot, ".13.err.netlistSimplified.dot")  # try to dump netlist if simplified failed in later stage
    DBG_13_netlistSimplified = (HlsNetlistPassDumpToDot, ".13.netlistSimplified.dot")  # dump simplified netlist
    DBG_14_nodesSimplified = (HlsNetlistPassDumpNodes, ".14.netlistSimplified.txt")  # same as DBG_13_netlistSimplified just in txt
    DBG_15_syncDomains = (HlsNetlistPassSyncDomainsToGraphwiz, ".15.syncDomains.dot")  # dump association of IO to individual logic node clouds
    DBG_16_syncReach = (HlsNetlistPassSyncReachToGraphwiz, ".16.syncReach.dot")  # dump transitive enclosure of DBG_15_syncDomains
    DBG_17_netlistAggregated = (HlsNetlistPassDumpToDot, ".17.netlistAggregated.dot")  # dump netlist after selected nodes were agregated to scheduling primitives
    DBG_18_hwscheduleErr = (HlsNetlistPassShowTimelineJson, ".18.err.hwschedule.json")  # try dump scheduling if scheduler failed
    DBG_19_hwschedule = (HlsNetlistPassShowTimelineJson, ".19.hwschedule.json")  # node scheduling after first scheduling atempt
    DBG_20_addSyncSigNames = (RtlNetlistPassAddSyncSigNames, None)  # signal names are directly in output RTL
    DBG_21_final_hwschedule = (HlsNetlistPassShowTimelineJson, ".21.final.hwschedule.json")  # node scheduling which will be used to generate circuit
    DBG_22_arch = (RtlArchPassToGraphwiz, ".22.arch.dot")  # relations between arch elements in whole generated architecutre
    DBG_23_sync = (RtlNetlistPassDumpStreamNodes, ".22.sync.txt")  # control expressions of IO, FSMs and pipelines
    DBG_24_archSchedule = (RtlArchPassShowTimeline, ".23.archSchedule.html")  # scheduling on architectural level
    DBG_25_regFileHierarchy = (RtlArchPassTransplantArchElementsToSubunits, None)  # extract registers in pipeline stage or fsm to separate component

    ALL = None
    NONE = {}
    # all without DBG_20_addSyncSigNames, DBG_25_regFileHierarchy because it changes optimization behavior
    ALL_RELIABLE = {
        DBG_0_preSsaOpt,
        DBG_1_frontend,
        DBG_2_preLlvm,
        DBG_3_mir,
        DBG_4_mirCfg,
        DBG_5_dthreads,
        DBG_6_blockSync,
        DBG_7_preSync,
        DBG_8_postRst,
        DBG_9_postLoop,
        DBG_10_postSync,
        DBG_11_netlist,
        DBG_12_nodes,
        DBG_12_netlistSimplifyTrace,
        DBG_12_netlistSimplifiedErr,
        DBG_13_netlistSimplifiedErr,
        DBG_13_netlistSimplified,
        DBG_14_nodesSimplified,
        DBG_15_syncDomains,
        DBG_16_syncReach,
        DBG_17_netlistAggregated,
        DBG_18_hwscheduleErr,
        DBG_19_hwschedule,
        DBG_21_final_hwschedule,
        DBG_22_arch,
        DBG_23_sync,
        DBG_24_archSchedule,
    }
    DEFAULT = NONE

    # bundles of debug features to debug problems in a specific phase of compilation
    DBG_FRONTEND = {DBG_0_preSsaOpt, DBG_1_frontend}
    DBG_NETLIST_GEN = {
        DBG_3_mir,
        DBG_4_mirCfg,
        DBG_5_dthreads,
        DBG_6_blockSync,
        DBG_7_preSync,
        DBG_8_postRst,
        DBG_9_postLoop,
        DBG_10_postSync,
        DBG_11_netlist,
    }
    DBG_NETLIST_OPT = {
        DBG_11_netlist,
        DBG_12_nodes,
        DBG_12_netlistSimplifyTrace,
        DBG_12_netlistSimplifiedErr,
        DBG_13_netlistSimplifiedErr,
        DBG_13_netlistSimplified,
        DBG_14_nodesSimplified,
        DBG_15_syncDomains,
        DBG_16_syncReach,
    }
    DBG_SCHEDULING = {
        DBG_16_syncReach,
        DBG_17_netlistAggregated,
        DBG_18_hwscheduleErr,
        DBG_19_hwschedule,
        DBG_20_addSyncSigNames,
        DBG_21_final_hwschedule,
    }
    DBG_ARCH_SYNC = {
        DBG_3_mir,
        DBG_15_syncDomains,
        DBG_16_syncReach,
        DBG_20_addSyncSigNames,
        DBG_21_final_hwschedule,
        DBG_22_arch,
        DBG_23_sync,
    }

    def __init__(self, debugDir:Optional[Union[str, Path]], filter_: Optional[Set[DebugId]]):
        """
        :attention: if debugDir is None no debug option will be enabled 
        """
        self.dir = None if debugDir is None else Path(debugDir)
        self.filter = filter_
        self.firstRun = True

    def isActivated(self, item: DebugId):
        return self.filter is None or item in self.filter

    def runDebugIfEnabled(self, cls: Type, id_: DebugId, applyArgs:tuple, *args, **kwargs):
        if self.firstRun:
            debugDir = self.dir
            if debugDir and not debugDir.exists():
                debugDir.mkdir()
            self.firstRun = False
        
        if self.dir is not None and self.isActivated(id_):
            _, fileNameSuffix = id_
            if fileNameSuffix is not None:
                cls(outputFileGetter(self.dir, fileNameSuffix), *args, **kwargs).apply(*applyArgs)
            else:
                cls(*args, **kwargs).apply(*applyArgs)
                
    def runAssertIfEnabled(self, cls: Type, args:tuple):
        if self.dir is not None:
            cls().apply(*args)
          

class DefaultHlsPlatform(DummyPlatform):
    """
    A base platform which is a container of target config and compilation pipeline configuration.
    """

    def __init__(self, debugDir:Optional[Union[str, Path]]="tmp",
                 debugFilter: Optional[Set[DebugId]]=HlsDebugBundle.DEFAULT):
        DummyPlatform.__init__(self)
        self.allocator = HlsAllocator
        self.scheduler = HlsScheduler
        self._debug = HlsDebugBundle(debugDir, debugFilter)
        self._debugExpandCompositeNodes = False

    def runSsaPasses(self, hls: "HlsScope", toSsa: HlsAstToSsa):
        dbg = self._debug.runDebugIfEnabled

        dbg(SsaPassDumpToDot, HlsDebugBundle.DBG_0_preSsaOpt, (hls, toSsa), extractPipeline=False)
        self._debug.runAssertIfEnabled(SsaPassConsystencyCheck, (hls, toSsa))

        SsaPassAxiStreamReadLowering().apply(hls, toSsa)
        SsaPassAxiStreamWriteLowering().apply(hls, toSsa)
        dbg(SsaPassDumpToDot, HlsDebugBundle.DBG_1_frontend, (hls, toSsa), extractPipeline=False)

        # convert frontend SSA to LLVM SSA for more advanced optimizations
        SsaPassToLlvm().apply(hls, toSsa)
        
        dbg(SsaPassDumpToLl, HlsDebugBundle.DBG_2_preLlvm, (hls, toSsa))
   
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
        """
        .. figure:: ./_static/DefaultHlsPlatform.runNetlistTranslation.png
        """
        tr: ToLlvmIrTranslator = toSsa.start
        assert isinstance(tr, ToLlvmIrTranslator), tr
        toNetlist = HlsNetlistAnalysisPassMirToNetlist(
            hls, tr, mf, backedges, liveness, ioRegs, registerTypes, loops)
        netlist = toNetlist.netlist
        dbg = self._debug.runDebugIfEnabled
        D = HlsDebugBundle
        dbg(SsaPassDumpMIR, D.DBG_3_mir, (hls, toSsa))
        dbg(SsaPassDumpMirCfg, D.DBG_4_mirCfg, (hls, toSsa))
        
        toNetlist.translateDatapathInBlocks(mf, toSsa.ioNodeConstructors)
        blockLiveInMuxInputSync: BlockLiveInMuxSyncDict = toNetlist.constructLiveInMuxes(mf)
        # thread analysis must be done before we connect control, because once we do that
        # everything will blend together 
        threads = netlist.getAnalysis(HlsNetlistAnalysisPassDataThreadsForBlocks)
        toNetlist.updateThreadsOnPhiMuxes(threads)
        dbg(HlsNetlistPassDumpDataThreads, D.DBG_5_dthreads, (hls, netlist))

        netlist.getAnalysis(HlsNetlistAnalysisPassBlockSyncType)
        dbg(HlsNetlistPassDumpBlockSync, D.DBG_6_blockSync, (hls, netlist))
        dbg(HlsNetlistPassDumpToDot, D.DBG_7_preSync, (hls, netlist))

        toNetlist.extractRstValues(mf, threads)
        dbg(HlsNetlistPassDumpToDot, D.DBG_8_postRst, (hls, netlist))
        
        toNetlist.resolveLoopHeaders(mf, blockLiveInMuxInputSync)
        dbg(HlsNetlistPassDumpToDot, D.DBG_9_postLoop, (hls, netlist))

        toNetlist.resolveBlockEn(mf, threads)
        netlist.invalidateAnalysis(HlsNetlistAnalysisPassDataThreadsForBlocks)  # because we modified the netlist
        toNetlist.connectOrderingPorts(mf)
        dbg(HlsNetlistPassDumpBlockSync, D.DBG_10_postSync, (hls, netlist))

        return netlist

    def runHlsNetlistPasses(self, hls: "HlsScope", netlist: HlsNetlistCtx):
        """
        :note: now we can not touch MIR because it was deallocated
        """
        D = HlsDebugBundle
        dbg = self._debug.runDebugIfEnabled
        dbg(HlsNetlistPassDumpToDot, D.DBG_11_netlist, (hls, netlist))
        dbg(HlsNetlistPassDumpNodes, D.DBG_12_nodes, (hls, netlist))
        self._debug.runAssertIfEnabled(HlsNetlistPassConsystencyCheck, (hls, netlist))

        HlsNetlistPassReadSyncToAckOfIoNodes().apply(hls, netlist)

        firstPass = True
        while True:
            dbgDir = self._debug.dir
            if dbgDir and self._debug.isActivated(D.DBG_12_netlistSimplifyTrace):
                traceFile, doCloseTrace = outputFileGetter(self._debug.dir, D.DBG_12_netlistSimplifyTrace[1])(netlist.label)
                dbgTracer = DebugTracer(traceFile)
            else:
                dbgTracer = DebugTracer(None)
                doCloseTrace = False
            try:
                HlsNetlistPassSimplify(dbgTracer).apply(hls, netlist)  # done second time after HlsNetlistPassInjectVldMaskToSkipWhenConditions 
            except:
                if doCloseTrace:
                    traceFile.close()
                # if something went wrong try to debug actual state of the netlist
                dbg(HlsNetlistPassDumpToDot, D.DBG_12_netlistSimplifiedErr if firstPass else D.DBG_13_netlistSimplifiedErr, (hls, netlist))
                raise

            if firstPass:
                # done in advance in order to check transitively connected IO only once and in order to avoid checks for HlsNetNodeReadSync later
                HlsNetlistPassInjectVldMaskToSkipWhenConditions().apply(hls, netlist)  # done after simply because rewrite is costly
                firstPass = False
                continue
    
            # if all predecessor IO have some skipWhen condition the extraCond may be incomplete due to hoisting
            # this may result in successors working without any data 
            HlsNetlistPassConstNodeDuplication().apply(hls, netlist)
    
            dbg(HlsNetlistPassDumpToDot, D.DBG_13_netlistSimplified, (hls, netlist))
            dbg(HlsNetlistPassDumpNodes, D.DBG_14_nodesSimplified, (hls, netlist))
            dbg(HlsNetlistPassSyncDomainsToGraphwiz, D.DBG_15_syncDomains, (hls, netlist))
            netlist.getAnalysis(HlsNetlistAnalysisPassSyncReach)  # must be executed before aggregation
                
            dbg(HlsNetlistPassSyncReachToGraphwiz, D.DBG_16_syncReach, (hls, netlist))
            self._debug.runAssertIfEnabled(HlsNetlistPassConsystencyCheck, (hls, netlist))

            # aggregation to make scheduling less computationally costly
            HlsNetlistPassAggregateIoSyncSccs().apply(hls, netlist)
            HlsNetlistPassAggregateBitwiseOps().apply(hls, netlist)
    
            dbg(HlsNetlistPassDumpToDot, D.DBG_17_netlistAggregated, (hls, netlist))
        
            try:
                netlist.getAnalysis(HlsNetlistAnalysisPassRunScheduler)
            except:
                # try to debug scheduling if something went wrong
                dbg(HlsNetlistPassShowTimelineJson, D.DBG_18_hwscheduleErr, (hls, netlist),
                    expandCompositeNodes=self._debugExpandCompositeNodes)
                raise
            
            HlsNetlistPassDisaggregateAggregates().apply(hls, netlist)
            if self.runHlsNetlistPostSchedulingPasses(hls, netlist):
                netlist.invalidateAnalysis(HlsNetlistAnalysisPassRunScheduler)
            else:
                break

        # merge buffers between same times in same arch element
        # HlsNetlistPassBackedgeBufferMerge().apply(hls, netlist)
        dbg(HlsNetlistPassShowTimelineJson, D.DBG_19_hwschedule, (hls, netlist),
            expandCompositeNodes=self._debugExpandCompositeNodes)
        self._debug.runAssertIfEnabled(HlsNetlistPassConsystencyCheck, (hls, netlist))

    def runHlsNetlistPostSchedulingPasses(self, hls: "HlsScope", netlist: HlsNetlistCtx) -> bool:
        modified = False
        # modified |= HlsNetlistPassPostSchedulingChannelMerge().apply(hls, netlist)
        return modified

    def runHlsNetlistToRtlNetlist(self, hls: "HlsScope", netlist: HlsNetlistCtx):
        """
        Translate scheduled circuit to RTL
        
        Problems:

          1. When resolving logic in clock cycle we do not know about registers which will be constructed later.
             Because we did not seen use of this value yet.
          
          2. If the node spans over multiple clock cycles and some part is not in this arch element
              we do not know about it explicitly from node list.
          
          3. We can not just insert register object because it does not solve nodes spanning multiple clock cycles.
            And it generated value aliases which must be reduced to prevent duplication.
        
        * We walk the netlist and discover in which time the value is live (in netlist format the connection could lead to any time)
          and we need to find out in which times we should construct registers and most importantly in which arch. element we should construct them.

        * For each node which is crossing arch element boundary or spans multiple cycles we also have mark the individual parts for clock cycles
          if the node is crossing arch. elem. boundary we also must ask it to declare its IO first so the node can be constructed from any 
          arch element.

        * First arch element which sees the node allocates it. The allocation is marked in allocator and happens only once.

        * Each arch element explicitly queries the node for the specific time (and input/output combination if node spans over more arch. elements).
        """
        dbg = self._debug
        D = HlsDebugBundle
        dbg.runAssertIfEnabled(HlsNetlistPassConsystencyCheck, (hls, netlist))
        if dbg.dir is not None:
            netlist.scheduler._checkAllNodesScheduled()
        
        dbg.runDebugIfEnabled(RtlNetlistPassAddSyncSigNames, D.DBG_20_addSyncSigNames, (hls, netlist))
        allocator = netlist.allocator
        allocator._discoverArchElements()
        # RtlArchPassSingleStagePipelineToFsm().apply(self, allocator)
        RtlArchPassLoopControlPrivatization().apply(self, allocator)

        dbg.runDebugIfEnabled(HlsNetlistPassShowTimelineJson, D.DBG_21_final_hwschedule, (hls, netlist),
                          expandCompositeNodes=self._debugExpandCompositeNodes)
        
        iea = InterArchElementNodeSharingAnalysis(netlist.normalizedClkPeriod)
        allocator._iea = iea         
        if len(allocator._archElements) > 1:  # analyze sharing only if there are multiple elements
            iea._analyzeInterElementsNodeSharing(allocator._archElements)
            if iea.interElemConnections:  # it could be the case that the elements are completely independent
                allocator.declareInterElemenetBoundarySignals(iea)
        # resolve IO port to element association for multi ported IO
        RtlArchPassIoPortPrivatization().apply(self, allocator)

        for e in allocator._archElements:
            e.allocateDataPath(iea)

        if iea.interElemConnections:
            allocator.finalizeInterElementsConnections(iea)
        # :note: must be after finalizeInterElementsConnections because it needs inter element sync channels
        # RtlArchPassFsmShareTiedStateTransitions().apply(self, allocator)
        dbg.runDebugIfEnabled(RtlArchPassToGraphwiz, D.DBG_22_arch, (hls, netlist))

        for e in allocator._archElements:
            e.allocateSync()

    def runRtlNetlistPasses(self, hls: "HlsScope", netlist: HlsNetlistCtx):
        RtlNetlistPassControlLogicMinimize().apply(hls, netlist)

        dbg = self._debug.runDebugIfEnabled
        dbg(RtlNetlistPassDumpStreamNodes, HlsDebugBundle.DBG_23_sync, (hls, netlist))
        dbg(RtlArchPassShowTimeline, HlsDebugBundle.DBG_24_archSchedule, (hls, netlist))
        dbg(RtlArchPassTransplantArchElementsToSubunits, HlsDebugBundle.DBG_25_regFileHierarchy, (hls, netlist))
        
