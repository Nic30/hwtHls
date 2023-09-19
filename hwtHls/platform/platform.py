from pathlib import Path
from typing import Optional, Union, Set, Tuple, Dict, List, Type

from hwt.synthesizer.dummyPlatform import DummyPlatform
from hwtHls.architecture.allocator import HlsAllocator
from hwtHls.architecture.interArchElementNodeSharingAnalysis import InterArchElementNodeSharingAnalysis
from hwtHls.architecture.transformation.addSyncSigNames import RtlNetlistPassAddSyncSigNames
from hwtHls.architecture.transformation.archElementsToSubunits import RtlArchPassTransplantArchElementsToSubunits
from hwtHls.architecture.transformation.channelMerge import RtlArchPassChannelMerge
from hwtHls.architecture.transformation.controlLogicMinimize import RtlNetlistPassControlLogicMinimize
from hwtHls.architecture.transformation.ioPortPrivatization import RtlArchPassIoPortPrivatization
from hwtHls.architecture.transformation.loopControlPrivatization import RtlArchPassLoopControlPrivatization
from hwtHls.architecture.transformation.mergeTiedFsms import RtlArchPassMergeTiedFsms
from hwtHls.architecture.translation.dumpArchDot import RtlArchPassDumpArchDot
from hwtHls.architecture.translation.dumpStreamNodes import RtlNetlistPassDumpStreamNodes
from hwtHls.frontend.ast.astToSsa import HlsAstToSsa
from hwtHls.llvm.llvmIr import MachineFunction, MachineBasicBlock, Register, MachineLoopInfo
from hwtHls.netlist.analysis.betweenSyncIslands import HlsNetlistAnalysisPassBetweenSyncIslands
from hwtHls.netlist.analysis.betweenSyncIslandsConsystencyCheck import HlsNetlistPassBetweenSyncIslandsConsystencyCheck
from hwtHls.netlist.analysis.blockSyncType import HlsNetlistAnalysisPassBlockSyncType
from hwtHls.netlist.analysis.consystencyCheck import HlsNetlistPassConsystencyCheck
from hwtHls.netlist.analysis.dataThreadsForBlocks import HlsNetlistAnalysisPassDataThreadsForBlocks
from hwtHls.netlist.analysis.schedule import HlsNetlistAnalysisPassRunScheduler
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.scheduler.scheduler import HlsScheduler
from hwtHls.netlist.transformation.aggregateBitwiseOps import HlsNetlistPassAggregateBitwiseOps
from hwtHls.netlist.transformation.aggregateIoSyncScc import HlsNetlistPassAggregateIoSyncSccs
from hwtHls.netlist.transformation.betweenSyncIslandsMerge import HlsNetlistPassBetweenSyncIslandsMerge
from hwtHls.netlist.transformation.constNodeDuplication import HlsNetlistPassConstNodeDuplication
from hwtHls.netlist.transformation.createIoClusters import HlsNetlistPassCreateIoClusters
from hwtHls.netlist.transformation.disaggregateAggregates import HlsNetlistPassDisaggregateAggregates
from hwtHls.netlist.transformation.moveExplicitSyncOutOfDataAndAddVoidDataLinks import HlsNetlistPassMoveExplicitSyncOutOfDataAndAddVoidDataLinks
from hwtHls.netlist.transformation.readSyncToAckOfIoNodes import HlsNetlistPassReadSyncToAckOfIoNodes
from hwtHls.netlist.transformation.romDeduplication import HlsNetlistPassRomDeduplication
from hwtHls.netlist.transformation.simplify import HlsNetlistPassSimplify
from hwtHls.netlist.transformation.simplifyExpr.trivialSimplifyExplicitSync import HlsNetlistPassTrivialSimplifyExplicitSync
from hwtHls.netlist.translation.betweenSyncIslandsToGraphwiz import HlsNetlistPassBetweenSyncIslandsToGraphwiz
from hwtHls.netlist.translation.dumpBlockSync import HlsNetlistPassDumpBlockSync
from hwtHls.netlist.translation.dumpDataThreads import HlsNetlistPassDumpDataThreads
from hwtHls.netlist.translation.dumpNodesDot import HlsNetlistPassDumpNodesDot, \
    HlsNetlistPassDumpIoClustersDot
from hwtHls.netlist.translation.dumpNodesTxt import HlsNetlistPassDumpNodesTxt
from hwtHls.netlist.translation.dumpSchedulingJson import HlsNetlistPassDumpSchedulingJson
from hwtHls.netlist.translation.dumpSyncDomainsDot import HlsNetlistPassDumpSyncDomainsDot
from hwtHls.platform.fileUtils import outputFileGetter
from hwtHls.ssa.analysis.consystencyCheck import SsaPassConsystencyCheck
from hwtHls.ssa.translation.dumpMIR import SsaPassDumpMIR
from hwtHls.ssa.translation.dumpMirCfg import SsaPassDumpMirCfg
from hwtHls.ssa.translation.llvmMirToNetlist.datapath import BlockLiveInMuxSyncDict
from hwtHls.ssa.translation.llvmMirToNetlist.mirToNetlist import HlsNetlistAnalysisPassMirToNetlist
from hwtHls.ssa.translation.toGraphwiz import SsaPassDumpToDot
from hwtHls.ssa.translation.toLl import SsaPassDumpToLl
from hwtHls.ssa.translation.toLlvm import SsaPassToLlvm, ToLlvmIrTranslator


DebugId = Tuple[Type, Optional[str]]


class HlsDebugBundle():
    """
    :note: if the number N in DBG_N_* is the same it means that these debug options are working with the same input
    """
    DEFAULT_DEBUG_DIR = "tmp"

    DBG_0_pyFrontedBytecode = (None, "00.bytecode.{0}.txt")  # bytecode for every translated function
    DBG_0_pyFrontedBeginCfg = (None, "00.cfg.begin.{0}.dot")  # initial CFG after parsing of bytecode
    DBG_0_pyFrontedPreprocCfg = (None, "00.cfg.{0}.dot")  # step by step CFG during preprocessor evaluation
    DBG_0_pyFrontedFinalCfg = (None, "00.cfg.final.{0}.dot")  # final CFG after preprocessor execution

    # ssa
    DBG_0_preSsaOpt = (SsaPassDumpToDot, "00.preSsaOpt.dot")  # raw input code
    DBG_1_frontend = (SsaPassDumpToDot, "01.frontend.dot")  # after frontend transformations
    DBG_2_preLlvm = (SsaPassDumpToLl, "02.preLlvm.ll")  # translated to LLVM IR
    # mir
    DBG_3_mir = (SsaPassDumpMIR, "03.mir.ll")  # translated and optimized to LLVM MIR by LLVM
    DBG_4_mirCfg = (SsaPassDumpMirCfg, "04.mirCfg.dot")  # Control Flow Graph of MIR
    DBG_5_dthreads = (HlsNetlistPassDumpDataThreads, "05.dthreads.txt")  # instructions packed in data treads
    DBG_6_blockSync = (HlsNetlistPassDumpBlockSync, "06.blockSync.dot")  # synchronization features of basic blocks
    DBG_7_preSync = (HlsNetlistPassDumpNodesDot, "07.preSync.dot")  # io of basic blocks before implementation of sync
    DBG_8_postRst = (HlsNetlistPassDumpNodesDot, "08.postRst.dot")  # basic block io after implementation of reset value extraction
    DBG_9_postLoop = (HlsNetlistPassDumpNodesDot, "09.postLoop.dot")  # basic block io after implementation of loops
    DBG_10_postSync = (HlsNetlistPassDumpBlockSync, "10.postSync.dot")  # basic block io after implementation of complete control flow sync
    # hls netlist
    DBG_11_netlist = (HlsNetlistPassDumpNodesDot, "11.netlist.dot")  # basic blocks disolved to netlist
    DBG_11_netlistTxt = (HlsNetlistPassDumpNodesTxt, "11.netlist.txt")  # same as DBG_11_netlist just in txt
    DBG_11_netlistIoClusters = (HlsNetlistPassDumpIoClustersDot, "11.netlistIoClusters.dot")  #
    DBG_12_netlistSimplifyTrace = (None, "12.netlistSimplifyTrace.txt")  # trace of netlist simplifier
    DBG_12_netlistSimplifiedErr = (HlsNetlistPassDumpNodesDot, "12.err.netlistSimplified.dot")  # try to dump netlist if simplified failed
    DBG_14_netlistSimplified = (HlsNetlistPassDumpNodesDot, "14.netlistSimplified.dot")  # dump simplified netlist
    DBG_14_netlistSimplifiedTxt = (HlsNetlistPassDumpNodesTxt, "14.netlistSimplified.txt")  # same as DBG_13_netlistSimplified just in txt
    DBG_14_netlistSimplifiedIoClusters = (HlsNetlistPassDumpIoClustersDot, "14.netlistSimplifiedIoClusters.dot")
    DBG_14_netlistSyncDomains = (HlsNetlistPassDumpSyncDomainsDot, "14.netlistSyncDomains.dot")  # dump association of IO to individual logic node clouds
    DBG_17_netlistAggregated = (HlsNetlistPassDumpNodesDot, "17.netlistAggregated.dot")  # dump netlist after selected nodes were agregated to scheduling primitives
    DBG_18_hwscheduleErr = (HlsNetlistPassDumpSchedulingJson, "18.err.hwschedule.json")  # try dump scheduling if scheduler failed
    DBG_19_hwschedule = (HlsNetlistPassDumpSchedulingJson, "19.hwschedule.json")  # node scheduling after first scheduling atempt
    # arch gen
    DBG_20_netlistSyncIslandsTrace = (None, "20.netlistSyncIslandsTrace.txt")  # trace of sync islands simplifier
    DBG_20_netlistSyncIslands = (HlsNetlistPassBetweenSyncIslandsToGraphwiz, "20.netlistSyncIslands.dot")  # dump transitive enclosure of DBG_15_syncDomains
    DBG_20_addSyncSigNames = (RtlNetlistPassAddSyncSigNames, None)  # signal names are directly in output RTL
    DBG_21_finalHwschedule = (HlsNetlistPassDumpSchedulingJson, "21.final.hwschedule.json")  # node scheduling which will be used to generate circuit
    DBG_22_finalNetlist = (HlsNetlistPassDumpNodesDot, "22.final.netlist.dot")  # basic blocks disolved to netlist
    DBG_22_finalNetlistTxt = (HlsNetlistPassDumpNodesTxt, "22.final.netlist.txt")  # same as DBG_11_netlist just in txt
    DBG_22_arch = (RtlArchPassDumpArchDot, "22.arch.dot")  # relations between arch elements in whole generated architecutre
    DBG_23_sync = (RtlNetlistPassDumpStreamNodes, "22.sync.txt")  # control expressions of IO, FSMs and pipelines
    DBG_24_regFileHierarchy = (RtlArchPassTransplantArchElementsToSubunits, None)  # extract registers in pipeline stage or fsm to separate component

    ALL = None
    NONE = {}
    # all without DBG_20_addSyncSigNames, DBG_24_regFileHierarchy because it changes optimization behavior
    ALL_RELIABLE = {
        DBG_0_pyFrontedBytecode,
        DBG_0_pyFrontedBeginCfg,
        DBG_0_pyFrontedFinalCfg,
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
        DBG_11_netlistTxt,
        DBG_11_netlistIoClusters,
        DBG_12_netlistSimplifyTrace,
        DBG_12_netlistSimplifiedErr,
        DBG_14_netlistSimplified,
        DBG_14_netlistSimplifiedTxt,
        DBG_14_netlistSimplifiedIoClusters,
        DBG_14_netlistSyncDomains,
        DBG_17_netlistAggregated,
        DBG_18_hwscheduleErr,
        DBG_19_hwschedule,
        DBG_20_netlistSyncIslandsTrace,
        DBG_20_netlistSyncIslands,
        DBG_21_finalHwschedule,
        DBG_22_finalNetlist,
        DBG_22_finalNetlistTxt,
        DBG_22_arch,
        DBG_23_sync,
    }
    DEFAULT = NONE

    # bundles of debug features to debug problems in a specific phase of compilation
    DBG_FRONTEND = {
        DBG_0_pyFrontedBytecode,
        DBG_0_pyFrontedBeginCfg,
        DBG_0_pyFrontedPreprocCfg,
        DBG_0_pyFrontedFinalCfg,
        DBG_0_preSsaOpt,
        DBG_1_frontend
    }
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
        DBG_11_netlistTxt,
        DBG_11_netlistIoClusters,
        DBG_12_netlistSimplifyTrace,
        DBG_12_netlistSimplifiedErr,
        DBG_14_netlistSimplified,
        DBG_14_netlistSimplified,
        DBG_14_netlistSyncDomains,
    }
    DBG_SCHEDULING = {
        DBG_17_netlistAggregated,
        DBG_18_hwscheduleErr,
        DBG_19_hwschedule,
        DBG_20_addSyncSigNames,
        DBG_21_finalHwschedule,
    }
    DBG_ARCH_SYNC = {
        DBG_3_mir,
        DBG_14_netlistSyncDomains,
        DBG_20_netlistSyncIslandsTrace,
        DBG_20_netlistSyncIslands,
        DBG_20_addSyncSigNames,
        DBG_21_finalHwschedule,
        DBG_22_finalNetlist,
        DBG_22_finalNetlistTxt,
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

    def runDebugIfEnabled(self, id_: DebugId, applyArgs: tuple,
                          clsOverride: Optional[Type]=None,
                          constructorArgs: Optional[tuple]=None,
                          constructorKwargs: Optional[dict]=None):

        debugDir = self.dir
        if debugDir is not None and self.isActivated(id_):
            if self.firstRun:
                if debugDir and not debugDir.exists():
                    debugDir.mkdir()
                self.firstRun = False
            if clsOverride is None:
                cls = id_[0]
            else:
                cls = clsOverride

            if constructorArgs is None:
                constructorArgs = ()
            if constructorKwargs is None:
                constructorKwargs = {}

            _, fileNameSuffix = id_
            if fileNameSuffix is not None:
                outStreamGetter = outputFileGetter(debugDir, fileNameSuffix)
                cls(outStreamGetter, *constructorArgs, **constructorKwargs).apply(*applyArgs)
            else:
                cls(*constructorArgs, **constructorKwargs).apply(*applyArgs)

    def runAssertIfEnabled(self, cls: Type, args:tuple):
        if self.dir is not None:
            cls().apply(*args)


class DefaultHlsPlatform(DummyPlatform):
    """
    A base platform which is a container of target config and compilation pipeline configuration.
    """

    def __init__(self, debugDir:Optional[Union[str, Path]]=HlsDebugBundle.DEFAULT_DEBUG_DIR,
                 debugFilter: Optional[Set[DebugId]]=HlsDebugBundle.DEFAULT):
        DummyPlatform.__init__(self)
        self.allocator = HlsAllocator
        self.scheduler = HlsScheduler
        self._debug = HlsDebugBundle(debugDir, debugFilter)
        self._debugExpandCompositeNodes = False
        self._llvmCliArgs:List[Tuple[str, int, str, str]] = [
            #("debug-pass", 0, "", "Arguments"), # print used passes starting from machinemoduleinfo
            # ("debug-only", 0, "", "hwtfpga-pretonetlist-combiner"),
            # ("print-after-all", 0, "", "true"),
            # ("print-before-all", 0, "", "true"),
            # ("time-passes", 0, "", "true"),
            # ("print-before", 0, "", "machine-sink"),
            # ("print-after", 0, "", "machine-sink"),
            # ("view-dag-combine1-dags", 0, "", "true"),
            # ("view-legalize-types-dags", 0, "", "true"),
            # ("view-dag-combine-lt-dags", 0, "", "true"),
            # ("view-legalize-dags", 0, "", "true"),
            # ("view-dag-combine2-dags", 0, "", "true"),
            # ("view-isel-dags", 0, "", "true"),
            # ("view-sched-dags", 0, "", "true"),
            # ("view-sunit-dags", 0, "", "true"),
            # ("print-after-isel", 0, "", "true"),
            # ("debug-only", 0, "", "mir-canonicalizer"), # :note: available only in llvm debug build #"early-ifcvt-limit"
            # ("debug-only", 0, "", "simplifycfg")
            # ("print-lsr-output", 0, "", "true"),
            # ("print-before", 0, "", "loop-unroll"),
            # ("debug-only", 0, "", "loop-unroll"), # :note: available only in llvm debug build
            # ("print-after", 0, "", "loop-unroll"),
            # ("debug-only", 0, "", "loop-unroll"), # :note: available only in llvm debug build
            # ("print-after", 0, "", "loop-unroll"),
            # ("print-before", 0, "", "early-if-predicator"),
            # ("print-after", 0, "", "early-if-predicator"),
            # ("print-before", 0, "", "early-ifcvt"),
            # ("print-after", 0, "", "early-ifcvt"),
            # ("print-before", 0, "", "vreg-if-converter"),
            # ("debug-only", 0, "", "vreg-if-converter"), # :note: available only in llvm debug build
            # ("print-after", 0, "", "vreg-if-converter"),
            # ("debug", 0, "", "1"),
            # ("print-before", 0, "", "hwtfpga-preregalloc-combiner"),
            # ("print-after", 0, "", "hwtfpga-preregalloc-combiner"),
        ]

    def _getDebugTracer(self, netlist: HlsNetlistCtx, dbgId: DebugId):
        dbgDir = self._debug.dir
        if dbgDir and self._debug.isActivated(dbgId):
            traceFile, doCloseTrace = outputFileGetter(self._debug.dir, dbgId[1])(netlist.label)
            dbgTracer = DebugTracer(traceFile)
        else:
            dbgTracer = DebugTracer(None)
            doCloseTrace = False
        return dbgTracer, doCloseTrace

    def beforeThreadToSsa(self, thread: "HlsThread"):
        thread.debugEnable(self)

    def runSsaPasses(self, hls: "HlsScope", toSsa: HlsAstToSsa):
        dbg = self._debug.runDebugIfEnabled

        dbg(HlsDebugBundle.DBG_0_preSsaOpt, (hls, toSsa), constructorKwargs=dict(extractPipeline=False))
        self._debug.runAssertIfEnabled(SsaPassConsystencyCheck, (hls, toSsa))
        # try:
        #    SsaPassAxiStreamReadLowering().apply(hls, toSsa)
        #    SsaPassAxiStreamWriteLowering().apply(hls, toSsa)
        # finally:
        dbg(HlsDebugBundle.DBG_1_frontend, (hls, toSsa), constructorKwargs=dict(extractPipeline=False))

        # convert frontend SSA to LLVM SSA for more advanced optimizations
        SsaPassToLlvm(self._llvmCliArgs).apply(hls, toSsa)

        dbg(HlsDebugBundle.DBG_2_preLlvm, (hls, toSsa))

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
        dbg = self._debug.runDebugIfEnabled
        D = HlsDebugBundle
        dbg(D.DBG_3_mir, (hls, toSsa))
        dbg(D.DBG_4_mirCfg, (hls, toSsa))

        toNetlist = HlsNetlistAnalysisPassMirToNetlist(
            hls, tr, mf, backedges, liveness, ioRegs, registerTypes, loops)
        netlist = toNetlist.netlist

        toNetlist.translateDatapathInBlocks(mf, toSsa.ioNodeConstructors)
        threads = netlist.getAnalysis(HlsNetlistAnalysisPassDataThreadsForBlocks)
        toNetlist.updateThreadsOnLiveInMuxes(threads)
        dbg(D.DBG_5_dthreads, (hls, netlist))

        netlist.getAnalysis(HlsNetlistAnalysisPassBlockSyncType)
        dbg(D.DBG_6_blockSync, (hls, netlist))

        blockLiveInMuxInputSync: BlockLiveInMuxSyncDict = toNetlist.constructLiveInMuxes(mf)
        dbg(D.DBG_7_preSync, (hls, netlist))

        toNetlist.extractRstValues(mf, threads)
        dbg(D.DBG_8_postRst, (hls, netlist))

        toNetlist.resolveLoopControl(mf, blockLiveInMuxInputSync)
        dbg(D.DBG_9_postLoop, (hls, netlist))

        toNetlist.resolveBlockEn(mf, threads)
        netlist.invalidateAnalysis(HlsNetlistAnalysisPassDataThreadsForBlocks)  # because we modified the netlist
        toNetlist.connectOrderingPorts(mf)
        dbg(D.DBG_10_postSync, (hls, netlist))

        return netlist

    def runHlsNetlistPasses(self, hls: "HlsScope", netlist: HlsNetlistCtx):
        """
        :note: now we can not touch MIR because it was deallocated
        """
        D = HlsDebugBundle
        dbg = self._debug.runDebugIfEnabled
        dbg(D.DBG_11_netlist, (hls, netlist))
        dbg(D.DBG_11_netlistTxt, (hls, netlist))
        self._debug.runAssertIfEnabled(HlsNetlistPassConsystencyCheck, (hls, netlist))

        HlsNetlistPassReadSyncToAckOfIoNodes().apply(hls, netlist)
        dbgTracer, doCloseTrace = self._getDebugTracer(netlist, D.DBG_12_netlistSimplifyTrace)
        self._debug.runAssertIfEnabled(HlsNetlistPassConsystencyCheck, (hls, netlist))

        try:  # try-except for closing of dbgTracer

            with dbgTracer.scoped(HlsNetlistPassTrivialSimplifyExplicitSync.apply, None):
                HlsNetlistPassTrivialSimplifyExplicitSync(dbgTracer).apply(hls, netlist)

            HlsNetlistPassMoveExplicitSyncOutOfDataAndAddVoidDataLinks().apply(hls, netlist)
            self._debug.runAssertIfEnabled(HlsNetlistPassConsystencyCheck, (hls, netlist))

            dbg(D.DBG_11_netlistIoClusters, (hls, netlist))

            while True:
                try:
                    with dbgTracer.scoped(HlsNetlistPassSimplify.apply, None):
                        HlsNetlistPassSimplify(dbgTracer).apply(hls, netlist)  # done second time after HlsNetlistPassInjectVldMaskToSkipWhenConditions
                except:
                    # if something went wrong try to debug actual state of the netlist
                    dbg(D.DBG_12_netlistSimplifiedErr, (hls, netlist))
                    raise

                # if all predecessor IO have some skipWhen condition the extraCond may be incomplete due to hoisting
                # this may result in successors working without any data
                HlsNetlistPassConstNodeDuplication().apply(hls, netlist)

                dbg(D.DBG_14_netlistSimplified, (hls, netlist))
                dbg(D.DBG_14_netlistSimplifiedTxt, (hls, netlist))
                dbg(D.DBG_14_netlistSimplifiedIoClusters, (hls, netlist))
                dbg(D.DBG_14_netlistSyncDomains, (hls, netlist))

                self._debug.runAssertIfEnabled(HlsNetlistPassConsystencyCheck, (hls, netlist))

                # aggregation to make scheduling less computationally costly
                HlsNetlistPassAggregateIoSyncSccs().apply(hls, netlist)
                HlsNetlistPassAggregateBitwiseOps().apply(hls, netlist)

                dbg(D.DBG_17_netlistAggregated, (hls, netlist))

                try:
                    netlist.getAnalysis(HlsNetlistAnalysisPassRunScheduler)
                except Exception as e:
                    # try to debug scheduling if something went wrong
                    try:
                        dbg(D.DBG_18_hwscheduleErr, (hls, netlist), constructorKwargs=dict(
                            expandCompositeNodes=self._debugExpandCompositeNodes))
                    except:
                        raise AssertionError("HlsNetlistAnalysisPassRunScheduler failed and DBG_18_hwscheduleErr also failed") from e
                    raise

                HlsNetlistPassDisaggregateAggregates().apply(hls, netlist)
                if self.runHlsNetlistPostSchedulingPasses(hls, netlist):
                    netlist.invalidateAnalysis(HlsNetlistAnalysisPassRunScheduler)
                else:
                    HlsNetlistPassRomDeduplication().apply(hls, netlist)
                    break
        finally:
            if doCloseTrace:
                dbgTracer._out.close()
        # merge buffers between same times in same arch element
        # HlsNetlistPassBackedgeBufferMerge().apply(hls, netlist)
        dbg(D.DBG_19_hwschedule, (hls, netlist), constructorKwargs=dict(
            expandCompositeNodes=self._debugExpandCompositeNodes))
        self._debug.runAssertIfEnabled(HlsNetlistPassConsystencyCheck, (hls, netlist))

    def runHlsNetlistPostSchedulingPasses(self, hls: "HlsScope", netlist: HlsNetlistCtx) -> bool:
        modified = False
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

        HlsNetlistPassCreateIoClusters().apply(hls, netlist)
        dbgTracer, doCloseTrace = self._getDebugTracer(netlist, D.DBG_20_netlistSyncIslandsTrace)

        try:
            netlist.getAnalysis(HlsNetlistAnalysisPassBetweenSyncIslands)  # done explicitely to trigger potential exception there
            HlsNetlistPassBetweenSyncIslandsConsystencyCheck().apply(hls, netlist)
            HlsNetlistPassBetweenSyncIslandsMerge(dbgTracer).apply(hls, netlist)
            HlsNetlistPassBetweenSyncIslandsConsystencyCheck().apply(hls, netlist)
        finally:
            dbg.runDebugIfEnabled(D.DBG_20_netlistSyncIslands, (hls, netlist))
            if doCloseTrace:
                dbgTracer._out.close()

        dbg.runDebugIfEnabled(D.DBG_20_addSyncSigNames, (hls, netlist))

        allocator = netlist.allocator
        allocator._discoverArchElements()

        RtlArchPassLoopControlPrivatization().apply(self, allocator)
        dbg.runDebugIfEnabled(D.DBG_21_finalHwschedule, (hls, netlist), constructorKwargs=dict(
                          expandCompositeNodes=self._debugExpandCompositeNodes))

        iea = InterArchElementNodeSharingAnalysis(netlist.normalizedClkPeriod)
        allocator._iea = iea
        if len(allocator._archElements) > 1:  # analyze sharing only if there are multiple elements
            iea._analyzeInterElementsNodeSharing(allocator._archElements)
            if iea.interElemConnections:  # it could be the case that the elements are completely independent
                # merge FSM to parent if its every state requires sync with parent
                RtlArchPassMergeTiedFsms().apply(hls, allocator)
                allocator.declareInterElemenetBoundarySignals(iea)

        RtlArchPassChannelMerge().apply(hls, allocator)
        # resolve IO port to element association for multi ported IO
        RtlArchPassIoPortPrivatization().apply(self, allocator)

        dbg.runDebugIfEnabled(D.DBG_22_finalNetlist, (hls, netlist))
        dbg.runDebugIfEnabled(D.DBG_22_finalNetlistTxt, (hls, netlist))

        for e in allocator._archElements:
            e.allocateDataPath(iea)

        if iea.interElemConnections:
            allocator.finalizeInterElementsConnections(iea)

        # :note: must be after finalizeInterElementsConnections because it needs inter element sync channels
        # RtlArchPassFsmShareTiedStateTransitions().apply(self, allocator)
        dbg.runDebugIfEnabled(D.DBG_22_arch, (hls, netlist))

        for e in allocator._archElements:
            e.allocateSync()

    def runRtlNetlistPasses(self, hls: "HlsScope", netlist: HlsNetlistCtx):
        RtlNetlistPassControlLogicMinimize().apply(hls, netlist)

        dbg = self._debug.runDebugIfEnabled
        D = HlsDebugBundle
        dbg(D.DBG_23_sync, (hls, netlist))
        dbg(D.DBG_24_regFileHierarchy, (hls, netlist))
