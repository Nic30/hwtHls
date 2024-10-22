from io import StringIO
from pathlib import Path
import sys
from typing import Optional, Union, Set, Tuple, Dict, List

from hwt.synthesizer.dummyPlatform import DummyPlatform
from hwtHls.architecture.transformation.addImplicitSyncChannels import HlsArchPassAddImplicitSyncChannels
from hwtHls.architecture.transformation.addRtlSigNames import HlsAndRtlNetlistPassAddSignalForDeepExpr
from hwtHls.architecture.transformation.archStructureSimplify import HlsArchPassArchStructureSimplify
from hwtHls.architecture.transformation.channelMerge import RtlArchPassChannelMerge
from hwtHls.architecture.transformation.channelReduceSyncStrength import HlsArchPassChannelReduceSyncStrength
from hwtHls.architecture.transformation.controlLogicMinimize import HlsAndRtlNetlistPassControlLogicMinimize
from hwtHls.architecture.transformation.ioPortPrivatization import HlsArchPassIoPortPrivatization
from hwtHls.architecture.transformation.loopControlLowering import HlsAndRtlNetlistPassLoopControlLowering
from hwtHls.architecture.transformation.moveArchElementPortsToMinimizeSync import HlsArchPassMoveArchElementPortsToMinimizeSync
from hwtHls.architecture.transformation.operatorToHwtLowering import HlsAndRtlNetlistPassOperatorToHwtLowering
from hwtHls.architecture.transformation.syncLowering import HlsArchPassSyncLowering
from hwtHls.frontend.ast.astToSsa import HlsAstToSsa
from hwtHls.llvm.llvmIr import MachineFunction, MachineBasicBlock, Register, MachineLoopInfo
from hwtHls.netlist.analysis.blockSyncType import HlsNetlistAnalysisPassBlockSyncType
from hwtHls.netlist.analysis.consistencyCheck import HlsNetlistPassConsistencyCheck
from hwtHls.netlist.analysis.schedule import HlsNetlistAnalysisPassRunScheduler
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.scheduler.resourceList import initSchedulingResourceConstraintsFromIO
from hwtHls.netlist.scheduler.scheduler import HlsScheduler
from hwtHls.netlist.transformation.aggregateBitwiseOps import HlsNetlistPassAggregateBitwiseOps
from hwtHls.netlist.transformation.aggregateIoSyncSccs import HlsNetlistPassAggregateIoSyncSccs
from hwtHls.netlist.transformation.archElementStageInit import HlsNetlistPassArchElementStageInit
from hwtHls.netlist.transformation.constNodeDuplication import HlsNetlistPassConstNodeDuplication
from hwtHls.netlist.transformation.disaggregateAggregates import HlsNetlistPassDisaggregateAggregates
from hwtHls.netlist.transformation.multiClockNodeSplit import HlsNetlistPassMultiClockNodeSplit
from hwtHls.netlist.transformation.readSyncToAckOfIoNodes import HlsNetlistPassReadSyncToAckOfIoNodes
from hwtHls.netlist.transformation.romDeduplication import HlsNetlistPassRomDeduplication
from hwtHls.netlist.transformation.simplify import HlsNetlistPassSimplify
from hwtHls.netlist.transformation.simplifyExpr.trivialSimplifyExplicitSync import HlsNetlistPassTrivialSimplifyExplicitSync
from hwtHls.platform.debugBundle import HlsDebugBundle, DebugId
from hwtHls.platform.fileUtils import outputFileGetter
from hwtHls.ssa.analysis.consistencyCheck import SsaPassConsistencyCheck
from hwtHls.ssa.translation.llvmMirToNetlist.datapath import BlockLiveInMuxSyncDict
from hwtHls.ssa.translation.llvmMirToNetlist.mirToNetlist import HlsNetlistAnalysisPassMirToNetlist
from hwtHls.ssa.translation.toLlvm import SsaPassToLlvm, ToLlvmIrTranslator
from hwtHls.architecture.transformation.fsmStateNextWriteConstruction import HlsAndRtlNetlistPassFsmStateNextWriteConstruction
from hwtHls.architecture.transformation.channelReduceUselessValid import HlsArchPassChannelReduceUselessValid


def _runOnSsaMouduleGetter(p):
    return p.runOnSsaModule


LlvmCliArgTuple = Tuple[str, int, str, str]


class DefaultHlsPlatform(DummyPlatform):
    """
    A base platform which is a container of target config and compilation pipeline configuration.
    """

    def __init__(self, debugDir:Optional[Union[str, Path]]=HlsDebugBundle.DEFAULT_DEBUG_DIR,
                 debugFilter: Optional[Set[DebugId]]=HlsDebugBundle.DEFAULT,
                 llvmCliArgs:List[LlvmCliArgTuple]=[]):
        DummyPlatform.__init__(self)
        self.schedulerCls = HlsScheduler
        self._debug = HlsDebugBundle(debugDir, debugFilter)
        self._debugExpandCompositeNodes = False
        self._llvmCliArgs:List[LlvmCliArgTuple] = [
            # ("debug-pass-manager", 0, "", ""),  # print used passes until machinemoduleinfo
            # ("debug-pass", 0, "", "Arguments"), # print used passes starting from machinemoduleinfo
            # ("debug-pass", 0, "", "Structure"), # same as Arguments but pretty formated
            # ("print-after-all", 0, "", "true"),
            # ("print-before-all", 0, "", "true"),
            # ("print-before", 0, "", "hwtfpga-pretonetlist-combiner"),
            # ("verify-each", 0, "", ""), # run verification after each pass
            # ("pass-remarks-output", 0, "", "opt.yaml"),
            # ("time-passes", 0, "", "true"), # profile times of passes and analysis
            # ("time-phases", 0, "", ""), [todo] rm
            # ("view-dag-combine1-dags", 0, "", "true"),
            # ("view-legalize-types-dags", 0, "", "true"),
            # ("view-dag-combine-lt-dags", 0, "", "true"),
            # ("view-legalize-dags", 0, "", "true"),
            # ("view-dag-combine2-dags", 0, "", "true"),
            # ("view-isel-dags", 0, "", "true"),
            # ("view-sched-dags", 0, "", "true"),
            # ("view-sunit-dags", 0, "", "true"),
            # ("vregifcvt-trace", 0, "", "true"),
            # ("print-after-isel", 0, "", "true"),
            # ("print-lsr-output", 0, "", "true"),
            # ("debug-only", 0, "", "vreg-if-converter"), # :note: available only in llvm debug build
            # ("debug-only", 0, "", "loop-simplify"), # :note: available only in llvm debug build
            # ("debug", 0, "", "1"),
        ] + llvmCliArgs

    def getPassManagerDebugLogFile(self) -> Optional[StringIO]:
        for llvmArg in self._llvmCliArgs:
            if llvmArg[0] == "debug-pass-manager":
                return sys.stderr
        return None

    def _getDebugTracer(self, scopeName: str, dbgId: DebugId):
        dbgDir = self._debug.dir
        if dbgDir and self._debug.isActivated(dbgId):
            traceFile, doCloseTrace = outputFileGetter(self._debug.dir, dbgId[1])(scopeName)
            dbgTracer = DebugTracer(traceFile)
        else:
            dbgTracer = DebugTracer(None)
            doCloseTrace = False
        return dbgTracer, doCloseTrace

    def beforeThreadToSsa(self, thread: "HlsThread"):
        thread.debugCopyConfig(self)

    def runSsaPasses(self, hls: "HlsScope", toSsa: HlsAstToSsa):
        DBG = self._debug.runDebugIfEnabled
        DBG(HlsDebugBundle.DBG_1_0_preSsaOpt, (toSsa,), applyFnGetter=_runOnSsaMouduleGetter,
            constructorKwargs=dict(extractPipeline=False))
        DBG(SsaPassConsistencyCheck, (toSsa,), applyFnGetter=_runOnSsaMouduleGetter)
        DBG(HlsDebugBundle.DBG_1_1_frontend, (toSsa,), applyFnGetter=_runOnSsaMouduleGetter,
            constructorKwargs=dict(extractPipeline=False))

        # convert frontend SSA to LLVM SSA for more advanced optimizations
        SsaPassToLlvm(hls, self._llvmCliArgs).runOnSsaModule(toSsa)

        DBG(HlsDebugBundle.DBG_1_2_preLlvm, (toSsa,), applyFnGetter=_runOnSsaMouduleGetter)

    def runSsaToNetlist(self, hls: "HlsScope", toSsa: HlsAstToSsa, netlist: HlsNetlistCtx) -> HlsNetlistCtx:
        """
        :param hls: compilation scope
        :param toSsa: object which providing ssa for to netlist translation
        :param netlist: netlist object where translated netlist nodes should be placed
        """
        tr: ToLlvmIrTranslator = toSsa.start
        assert isinstance(tr, ToLlvmIrTranslator), tr
        tr.llvm.runOpt(self.runMirToHlsNetlist, hls, toSsa, netlist)

    def runMirToHlsNetlist(self,
                           hls: "HlsScope", toSsa: HlsAstToSsa, netlist: HlsNetlistCtx,
                           mf: MachineFunction,
                           backedges: Set[Tuple[MachineBasicBlock, MachineBasicBlock]],
                           liveness: Dict[MachineBasicBlock, Dict[MachineBasicBlock, Set[Register]]],
                           ioRegs: List[Register],
                           registerTypes: Dict[Register, int],
                           loops: MachineLoopInfo):
        """
        :attention: This function is called from c++ at the end of llvm pipeline.
          It is implemented in this way to allow access to analysis in llvm pass manager. 
        """
        tr: ToLlvmIrTranslator = toSsa.start
        assert isinstance(tr, ToLlvmIrTranslator), tr
        DBG = self._debug.runDebugIfEnabled
        D = HlsDebugBundle
        DBG(D.DBG_2_0_mir, (toSsa,), applyFnGetter=_runOnSsaMouduleGetter)
        DBG(D.DBG_2_0_mirCfg, (toSsa,), applyFnGetter=_runOnSsaMouduleGetter)

        toNetlist = HlsNetlistAnalysisPassMirToNetlist(
            hls, tr, mf, backedges, liveness, ioRegs, registerTypes, loops, netlist, toSsa.ioNodeConstructors)

        initSchedulingResourceConstraintsFromIO(netlist.scheduler.resourceUsage.resourceConstraints, tr.topIo.keys())
        dbgTracer, doCloseTrace = self._getDebugTracer(netlist.label, D.DBG_2_1_netlistConstructionTrace)
        toNetlist.setDebugTracer(dbgTracer)
        try:
            toNetlist.translateDatapathInBlocks(mf)
            DBG(D.DBG_2_1_blockSync, (netlist,))

            blockLiveInMuxInputSync: BlockLiveInMuxSyncDict = toNetlist.constructLiveInMuxes(mf)
            DBG(D.DBG_2_2_preSync, (netlist,))

            toNetlist.extractRstValues(mf)
            DBG(D.DBG_2_3_postRst, (netlist,))

            toNetlist.resolveControlForBlockWithChannelLivein(mf, blockLiveInMuxInputSync)
            DBG(D.DBG_2_4_postLoop, (netlist,))

            toNetlist.resolveBlockEn(mf)
            toNetlist.connectOrderingPorts(mf)
            DBG(D.DBG_2_5_postSync, (netlist,))
        finally:
            if doCloseTrace:
                dbgTracer._out.close()

        # must drop reference on all MIR related objects
        netlist.invalidateAnalysis(HlsNetlistAnalysisPassBlockSyncType)
        netlist.invalidateAnalysis(HlsNetlistAnalysisPassMirToNetlist)
        # after this function the MIR is deallocated

    def runHlsNetlistPasses(self, hls: "HlsScope", netlist: HlsNetlistCtx):
        """
        :note: LLVM MIR is now deallocated
        """
        D = HlsDebugBundle
        DBG = self._debug.runDebugIfEnabled
        DBG(D.DBG_3_0_netlist, (netlist,))
        DBG(D.DBG_3_0_netlistTxt, (netlist,))
        DBG(HlsNetlistPassConsistencyCheck, (netlist,))

        HlsNetlistPassReadSyncToAckOfIoNodes().runOnHlsNetlist(netlist)

        dbgTracer, doCloseTrace = self._getDebugTracer(netlist.label, D.DBG_3_1_netlistSimplifyTrace)
        DBG(HlsNetlistPassConsistencyCheck, (netlist,))

        try:  # try-except for closing of dbgTracer

            with dbgTracer.scoped(HlsNetlistPassTrivialSimplifyExplicitSync, None):
                HlsNetlistPassTrivialSimplifyExplicitSync(dbgTracer).runOnHlsNetlist(netlist)

            DBG(HlsNetlistPassConsistencyCheck, (netlist,))

            DBG(D.DBG_3_0_netlistIoClusters, (netlist,))

            while True:
                try:
                    with dbgTracer.scoped(HlsNetlistPassSimplify, None):
                        HlsNetlistPassSimplify(dbgTracer).runOnHlsNetlist(netlist)  # done second time after HlsNetlistPassInjectVldMaskToSkipWhenConditions
                except Exception as e:
                    # if something went wrong try to debug actual state of the netlist
                    try:
                        DBG(D.DBG_3_1_netlistSimplifiedErr, (netlist,))
                    except:
                        raise AssertionError("HlsNetlistPassSimplify failed and DBG_12_netlistSimplifiedErr also failed") from e
                    raise

                # if all predecessor IO have some skipWhen condition the extraCond may be incomplete due to hoisting
                # this may result in successors working without any data
                HlsNetlistPassConstNodeDuplication().runOnHlsNetlist(netlist)

                DBG(D.DBG_3_2_netlistSimplified, (netlist,))
                DBG(D.DBG_3_2_netlistSimplifiedTxt, (netlist,))
                DBG(D.DBG_3_2_netlistSimplifiedIoClusters, (netlist,))
                DBG(D.DBG_3_2_netlistSyncDomains, (netlist,))
                DBG(HlsNetlistPassConsistencyCheck, (netlist,))

                DBG(lambda: HlsNetlistPassConsistencyCheck(
                    checkCycleFree=False), (netlist,))

                # aggregation to make scheduling less computationally costly
                HlsNetlistPassAggregateIoSyncSccs().runOnHlsNetlist(netlist)
                DBG(lambda: HlsNetlistPassConsistencyCheck(
                    checkCycleFree=False), (netlist,))

                HlsNetlistPassAggregateBitwiseOps().runOnHlsNetlist(netlist)
                DBG(lambda: HlsNetlistPassConsistencyCheck(
                    checkCycleFree=False), (netlist,))

                DBG(D.DBG_3_3_netlistAggregated, (netlist,))

                try:
                    netlist.getAnalysis(HlsNetlistAnalysisPassRunScheduler)
                except Exception as e:
                    # try to debug scheduling if something went wrong
                    try:
                        DBG(D.DBG_4_0_hwscheduleErr, (netlist,), constructorKwargs=dict(
                            expandCompositeNodes=self._debugExpandCompositeNodes))
                    except:
                        raise AssertionError("HlsNetlistAnalysisPassRunScheduler failed and DBG_18_hwscheduleErr also failed") from e
                    raise

                DBG(lambda: HlsNetlistPassConsistencyCheck(
                    checkCycleFree=False, checkAggregatePortsScheduling=True), (netlist,))

                HlsNetlistPassDisaggregateAggregates().runOnHlsNetlist(netlist)
                DBG(lambda: HlsNetlistPassConsistencyCheck(
                    checkCycleFree=False, checkAllArchElementPortsInSameClockCycle=True), (netlist,))

                if self.runHlsNetlistPostSchedulingPasses(hls, netlist):
                    # runHlsNetlistPostSchedulingPasses request another round of scheduling and simplification passes
                    netlist.invalidateAnalysis(HlsNetlistAnalysisPassRunScheduler)
                else:
                    break
        except Exception as e:
            try:
                DBG(D.DBG_4_4_finalNetlist, (netlist,), constructorKwargs=dict(showVoid=True))
                DBG(D.DBG_4_4_finalNetlistTxt, (netlist,))
            except:
                raise AssertionError("Previous pass failed and dump of netlist also failed") from e

            raise

        finally:
            if doCloseTrace:
                dbgTracer._out.close()

        DBG(lambda: HlsNetlistPassConsistencyCheck(
            checkCycleFree=False, checkAllArchElementPortsInSameClockCycle=True), (netlist,))

        HlsNetlistPassRomDeduplication().runOnHlsNetlist(netlist)
        # merge buffers between same times in same arch element
        # HlsNetlistPassBackedgeBufferMerge().runOnHlsNetlist(netlist)
        DBG(D.DBG_4_0_hwschedule, (netlist,), constructorKwargs=dict(
            expandCompositeNodes=self._debugExpandCompositeNodes))
        DBG(HlsNetlistPassConsistencyCheck, (netlist,))

    def runHlsNetlistPostSchedulingPasses(self, hls: "HlsScope", netlist: HlsNetlistCtx) -> bool:
        modified = False
        return modified

    def runHlsNetlistToArchNetlist(self, hls: "HlsScope", netlist: HlsNetlistCtx):
        DBG = self._debug.runDebugIfEnabled
        D = HlsDebugBundle
        DBG(HlsNetlistPassConsistencyCheck, (netlist,))
        if self._debug.dir is not None:
            netlist.scheduler._checkAllNodesScheduled()

        try:
            HlsNetlistPassArchElementStageInit().runOnHlsNetlist(netlist)
            HlsNetlistPassMultiClockNodeSplit().runOnHlsNetlist(netlist)
            DBG(lambda: HlsNetlistPassConsistencyCheck(
                checkCycleFree=False, checkAllArchElementPortsInSameClockCycle=True), (netlist,))

            DBG(D.DBG_4_0_addSignalNamesToSync, (netlist,))
            DBG(D.DBG_4_0_addSignalNamesToData, (netlist,))

        except Exception as e:
            try:
                DBG(D.DBG_4_4_finalNetlist, (netlist,), constructorKwargs=dict(showVoid=True))
                DBG(D.DBG_4_4_finalNetlistTxt, (netlist,))
            except:
                raise AssertionError("Previous pass failed and dump of netlist also failed") from e

            raise

    def runArchNetlistToRtlNetlist(self, hls: "HlsScope", netlist: HlsNetlistCtx):
        DBG = self._debug.runDebugIfEnabled
        D = HlsDebugBundle
        try:
            # HlsArchPassLoopControlPrivatization().runOnHlsNetlist(netlist)
            DBG(D.DBG_4_1_finalHwschedule, (netlist,), constructorKwargs=dict(
                              expandCompositeNodes=self._debugExpandCompositeNodes))

            # RtlArchPassMergeTiedFsms().runOnHlsNetlist(netlist)
            HlsArchPassArchStructureSimplify().runOnHlsNetlist(netlist)
            DBG(lambda: HlsNetlistPassConsistencyCheck(checkCycleFree=False), (netlist,))

            dbgTracer, doCloseTrace = self._getDebugTracer(netlist.label, D.DBG_4_2_netlistChannelMergeTrace)
            try:
                RtlArchPassChannelMerge(dbgTracer).runOnHlsNetlist(netlist)
            finally:
                if doCloseTrace:
                    dbgTracer._out.close()

            DBG(lambda: HlsNetlistPassConsistencyCheck(checkCycleFree=False), (netlist,))

            HlsArchPassIoPortPrivatization().runOnHlsNetlist(netlist)
            # HlsArchPassSyncPredicatePruning().runOnHlsNetlist(netlist)
            DBG(lambda: HlsNetlistPassConsistencyCheck(
                checkCycleFree=False, checkAllArchElementPortsInSameClockCycle=True), (netlist,))
            HlsArchPassMoveArchElementPortsToMinimizeSync().runOnHlsNetlist(netlist)
            HlsArchPassAddImplicitSyncChannels().runOnHlsNetlist(netlist)
            DBG(lambda: HlsNetlistPassConsistencyCheck(checkCycleFree=False,
                                                       checkAllArchElementPortsInSameClockCycle=True),
                (netlist,))
            # RtlArchPassConnectValidOfLoopInputs().runOnHlsNetlist(netlist)
            HlsAndRtlNetlistPassLoopControlLowering().runOnHlsNetlist(netlist)
            DBG(lambda: HlsNetlistPassConsistencyCheck(checkCycleFree=False,
                                                       checkAllArchElementPortsInSameClockCycle=True),
                (netlist,))
            HlsArchPassChannelReduceSyncStrength().runOnHlsNetlist(netlist)
            HlsArchPassChannelReduceUselessValid().runOnHlsNetlist(netlist)
            HlsAndRtlNetlistPassFsmStateNextWriteConstruction().runOnHlsNetlist(netlist)
            DBG(lambda: HlsNetlistPassConsistencyCheck(checkCycleFree=False,
                                                       checkAllArchElementPortsInSameClockCycle=True),
                (netlist,))
            DBG(D.DBG_4_3_handshakeSCCs, (netlist,))
            DBG(D.DBG_4_3_netlistBeforSyncLoweingDot, (netlist,), constructorKwargs=dict(showVoid=True))
            DBG(D.DBG_4_3_netlistBeforSyncLoweingTxt, (netlist,))
            # DBG(D.DBG_23_finalNetlist, (netlist,), constructorKwargs=dict(showVoid=True))
            HlsArchPassSyncLowering(dbgDumpNodes=False, dbgDumpAbc=False).runOnHlsNetlist(netlist)
            DBG(lambda: HlsNetlistPassConsistencyCheck(checkCycleFree=False,
                                                       checkAllArchElementPortsInSameClockCycle=False),
                (netlist,))

            HlsAndRtlNetlistPassOperatorToHwtLowering().runOnHlsNetlist(netlist)
            HlsAndRtlNetlistPassAddSignalForDeepExpr().runOnHlsNetlist(netlist)

        finally:
            try:
                DBG(D.DBG_4_4_finalNetlist, (netlist,), constructorKwargs=dict(showVoid=True))
                DBG(D.DBG_4_4_finalNetlistTxt, (netlist,))
            except Exception as e:
                raise AssertionError("Previous pass failed and dump of netlist also failed") from e

        for e in netlist.iterAllNodes():
            e: ArchElement
            assert not e._isMarkedRemoved, e
            e.rtlAllocDatapath()

        # :note: must be after finalizeInterElementsConnections because it needs inter element sync channels
        DBG(D.DBG_4_4_arch, (netlist,))

        for e in netlist.iterAllNodes():
            e: ArchElement
            e.rtlAllocSync()

    def runHlsAndRtlNetlistPasses(self, hls: "HlsScope", netlist: HlsNetlistCtx):
        DBG = self._debug.runDebugIfEnabled
        D = HlsDebugBundle

        HlsAndRtlNetlistPassControlLogicMinimize().runOnHlsNetlist(netlist)
        DBG(D.DBG_4_5_sync, (netlist,))
        DBG(D.DBG_4_5_regFileHierarchy, (netlist,))
