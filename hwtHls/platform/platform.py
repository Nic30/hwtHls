from io import StringIO
from pathlib import Path
import sys
from typing import Optional, Union, Set, Tuple, Dict, List

from hwt.synthesizer.dummyPlatform import DummyPlatform
from hwtHls.architecture.transformation.addImplicitSyncChannels import RtlArchPassAddImplicitSyncChannels
from hwtHls.architecture.transformation.archStructureSimplify import RtlArchPassArchStructureSimplfy
from hwtHls.architecture.transformation.channelHandshakeCycleBreak import RtlArchPassChannelHandshakeCycleBreak
from hwtHls.architecture.transformation.channelMerge import RtlArchPassChannelMerge
from hwtHls.architecture.transformation.channelReduceSyncStrength import RtlArchPassChannelReduceSyncStrength
from hwtHls.architecture.transformation.controlLogicMinimize import HlsAndRtlNetlistPassControlLogicMinimize
from hwtHls.architecture.transformation.ioPortPrivatization import RtlArchPassIoPortPrivatization
from hwtHls.architecture.transformation.loopControlPrivatization import RtlArchPassLoopControlPrivatization
from hwtHls.architecture.transformation.mergeTiedFsms import RtlArchPassMergeTiedFsms
from hwtHls.architecture.transformation.moveArchElementPortsToMinimizeSync import RtlArchPassMoveArchElementPortsToMinimizeSync
from hwtHls.frontend.ast.astToSsa import HlsAstToSsa
from hwtHls.llvm.llvmIr import MachineFunction, MachineBasicBlock, Register, MachineLoopInfo
from hwtHls.netlist.analysis.betweenSyncIslands import HlsNetlistAnalysisPassBetweenSyncIslands
from hwtHls.netlist.analysis.betweenSyncIslandsConsystencyCheck import HlsNetlistPassBetweenSyncIslandsConsystencyCheck
from hwtHls.netlist.analysis.blockSyncType import HlsNetlistAnalysisPassBlockSyncType
from hwtHls.netlist.analysis.consystencyCheck import HlsNetlistPassConsystencyCheck
from hwtHls.netlist.analysis.dataThreadsForBlocks import HlsNetlistAnalysisPassDataThreadsForBlocks
from hwtHls.netlist.analysis.reachability import HlsNetlistAnalysisPassReachability
from hwtHls.netlist.analysis.schedule import HlsNetlistAnalysisPassRunScheduler
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.scheduler.scheduler import HlsScheduler
from hwtHls.netlist.transformation.aggregateArchElements import HlsNetlistPassAggregateArchElements
from hwtHls.netlist.transformation.aggregateBitwiseOps import HlsNetlistPassAggregateBitwiseOps
from hwtHls.netlist.transformation.aggregateIoSyncSccs import HlsNetlistPassAggregateIoSyncSccs
from hwtHls.netlist.transformation.aggregateLoops import HlsNetlistPassAggregateLoops
from hwtHls.netlist.transformation.betweenSyncIslandsMerge import HlsNetlistPassBetweenSyncIslandsMerge
from hwtHls.netlist.transformation.constNodeDuplication import HlsNetlistPassConstNodeDuplication
from hwtHls.netlist.transformation.createIoClusters import HlsNetlistPassCreateIoClusters
from hwtHls.netlist.transformation.disaggregateAggregates import HlsNetlistPassDisaggregateAggregates
from hwtHls.netlist.transformation.readSyncToAckOfIoNodes import HlsNetlistPassReadSyncToAckOfIoNodes
from hwtHls.netlist.transformation.romDeduplication import HlsNetlistPassRomDeduplication
from hwtHls.netlist.transformation.simplify import HlsNetlistPassSimplify
from hwtHls.netlist.transformation.simplifyExpr.trivialSimplifyExplicitSync import HlsNetlistPassTrivialSimplifyExplicitSync
from hwtHls.platform.debugBundle import HlsDebugBundle, DebugId
from hwtHls.platform.fileUtils import outputFileGetter
from hwtHls.ssa.analysis.consystencyCheck import SsaPassConsystencyCheck
from hwtHls.ssa.translation.llvmMirToNetlist.datapath import BlockLiveInMuxSyncDict
from hwtHls.ssa.translation.llvmMirToNetlist.mirToNetlist import HlsNetlistAnalysisPassMirToNetlist
from hwtHls.ssa.translation.toLlvm import SsaPassToLlvm, ToLlvmIrTranslator


def _runOnSsaMouduleGetter(p):
    return p.runOnSsaModule


class DefaultHlsPlatform(DummyPlatform):
    """
    A base platform which is a container of target config and compilation pipeline configuration.
    """

    def __init__(self, debugDir:Optional[Union[str, Path]]=HlsDebugBundle.DEFAULT_DEBUG_DIR,
                 debugFilter: Optional[Set[DebugId]]=HlsDebugBundle.DEFAULT):
        DummyPlatform.__init__(self)
        self.schedulerCls = HlsScheduler
        self._debug = HlsDebugBundle(debugDir, debugFilter)
        self._debugExpandCompositeNodes = False
        self._llvmCliArgs:List[Tuple[str, int, str, str]] = [
            # ("debug-pass-manager", 0, "", ""),  # print used passes until machinemoduleinfo
            # ("debug-pass", 0, "", "Arguments"), # print used passes starting from machinemoduleinfo
            # ("debug-pass", 0, "", "Structure"), # same as Arguments but pretty formated
            # ("debug-only", 0, "", "hwtfpga-pretonetlist-combiner"),
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
            # ("debug-only", 0, "", "mir-canonicalizer"), # :note: available only in llvm debug build #"early-ifcvt-limit"
            # ("print-lsr-output", 0, "", "true"),
            # ("debug-only", 0, "", "vreg-if-converter"), # :note: available only in llvm debug build
            # ("debug", 0, "", "1"),
        ]

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
        DBG(HlsDebugBundle.DBG_0_preSsaOpt, (toSsa,), applyFnGetter=_runOnSsaMouduleGetter,
            constructorKwargs=dict(extractPipeline=False))
        DBG(SsaPassConsystencyCheck, (toSsa,), applyFnGetter=_runOnSsaMouduleGetter)
        DBG(HlsDebugBundle.DBG_1_frontend, (toSsa,), applyFnGetter=_runOnSsaMouduleGetter,
            constructorKwargs=dict(extractPipeline=False))

        # convert frontend SSA to LLVM SSA for more advanced optimizations
        SsaPassToLlvm(hls, self._llvmCliArgs).runOnSsaModule(toSsa)

        DBG(HlsDebugBundle.DBG_2_preLlvm, (toSsa,), applyFnGetter=_runOnSsaMouduleGetter)

    def runSsaToNetlist(self, hls: "HlsScope", toSsa: HlsAstToSsa) -> HlsNetlistCtx:
        tr: ToLlvmIrTranslator = toSsa.start
        assert isinstance(tr, ToLlvmIrTranslator), tr
        netlist = tr.llvm.runOpt(self.runMirToHlsNetlist, hls, toSsa)
        assert netlist is not None
        return netlist

    def runMirToHlsNetlist(self,
                              hls: "HlsScope", toSsa: HlsAstToSsa,
                              mf: MachineFunction,
                              backedges: Set[Tuple[MachineBasicBlock, MachineBasicBlock]],
                              liveness: Dict[MachineBasicBlock, Dict[MachineBasicBlock, Set[Register]]],
                              ioRegs: List[Register],
                              registerTypes: Dict[Register, int],
                              loops: MachineLoopInfo):
        """
        .. figure:: ./_static/DefaultHlsPlatform.runMirToHlsNetlist.png
        """
        tr: ToLlvmIrTranslator = toSsa.start
        assert isinstance(tr, ToLlvmIrTranslator), tr
        DBG = self._debug.runDebugIfEnabled
        D = HlsDebugBundle
        DBG(D.DBG_3_mir, (toSsa,), applyFnGetter=_runOnSsaMouduleGetter)
        DBG(D.DBG_4_mirCfg, (toSsa,), applyFnGetter=_runOnSsaMouduleGetter)

        toNetlist = HlsNetlistAnalysisPassMirToNetlist(
            hls, tr, mf, backedges, liveness, ioRegs, registerTypes, loops)
        netlist = toNetlist.netlist
        dbgTracer, doCloseTrace = self._getDebugTracer(netlist.label, D.DBG_5_netlistConsttructionTrace)
        toNetlist.setDebugTracer(dbgTracer)
        try:
            toNetlist.translateDatapathInBlocks(mf, toSsa.ioNodeConstructors)
            threads = netlist.getAnalysis(HlsNetlistAnalysisPassDataThreadsForBlocks)
            toNetlist.updateThreadsOnLiveInMuxes(threads)
            DBG(D.DBG_5_dthreads, (netlist,))

            netlist.getAnalysis(HlsNetlistAnalysisPassBlockSyncType)
            DBG(D.DBG_6_blockSync, (netlist,))

            blockLiveInMuxInputSync: BlockLiveInMuxSyncDict = toNetlist.constructLiveInMuxes(mf)
            DBG(D.DBG_7_preSync, (netlist,))

            toNetlist.extractRstValues(mf, threads)
            DBG(D.DBG_8_postRst, (netlist,))

            toNetlist.resolveLoopControl(mf, blockLiveInMuxInputSync)
            DBG(D.DBG_9_postLoop, (netlist,))

            toNetlist.resolveBlockEn(mf, threads)
            netlist.invalidateAnalysis(HlsNetlistAnalysisPassDataThreadsForBlocks)  # because we modified the netlist
            toNetlist.connectOrderingPorts(mf)
            DBG(D.DBG_10_postSync, (netlist,))
        finally:
            if doCloseTrace:
                dbgTracer._out.close()

        # must drop reference on all MIR related objects
        netlist.invalidateAnalysis(HlsNetlistAnalysisPassBlockSyncType)
        netlist.invalidateAnalysis(HlsNetlistAnalysisPassMirToNetlist)
        netlist.invalidateAnalysis(HlsNetlistAnalysisPassReachability)

        return netlist

    def runHlsNetlistPasses(self, hls: "HlsScope", netlist: HlsNetlistCtx):
        """
        :note: now we can not touch MIR because it was deallocated
        """
        D = HlsDebugBundle
        DBG = self._debug.runDebugIfEnabled
        DBG(D.DBG_11_netlist, (netlist,))
        DBG(D.DBG_11_netlistTxt, (netlist,))
        DBG(HlsNetlistPassConsystencyCheck, (netlist,))

        HlsNetlistPassReadSyncToAckOfIoNodes().runOnHlsNetlist(netlist)

        dbgTracer, doCloseTrace = self._getDebugTracer(netlist.label, D.DBG_12_netlistSimplifyTrace)
        DBG(HlsNetlistPassConsystencyCheck, (netlist,))

        try:  # try-except for closing of dbgTracer

            with dbgTracer.scoped(HlsNetlistPassTrivialSimplifyExplicitSync, None):
                HlsNetlistPassTrivialSimplifyExplicitSync(dbgTracer).runOnHlsNetlist(netlist)

            DBG(HlsNetlistPassConsystencyCheck, (netlist,))

            DBG(D.DBG_11_netlistIoClusters, (netlist,))

            while True:
                try:
                    with dbgTracer.scoped(HlsNetlistPassSimplify, None):
                        HlsNetlistPassSimplify(dbgTracer).runOnHlsNetlist(netlist)  # done second time after HlsNetlistPassInjectVldMaskToSkipWhenConditions
                except Exception as e:
                    # if something went wrong try to debug actual state of the netlist
                    try:
                        DBG(D.DBG_12_netlistSimplifiedErr, (netlist,))
                    except:
                        raise AssertionError("HlsNetlistPassSimplify failed and DBG_12_netlistSimplifiedErr also failed") from e
                    raise

                # if all predecessor IO have some skipWhen condition the extraCond may be incomplete due to hoisting
                # this may result in successors working without any data
                HlsNetlistPassConstNodeDuplication().runOnHlsNetlist(netlist)

                DBG(D.DBG_14_netlistSimplified, (netlist,))
                DBG(D.DBG_14_netlistSimplifiedTxt, (netlist,))
                DBG(D.DBG_14_netlistSimplifiedIoClusters, (netlist,))
                DBG(D.DBG_14_netlistSyncDomains, (netlist,))
                DBG(HlsNetlistPassConsystencyCheck, (netlist,))

                # aggregation to make scheduling less computationally costly
                HlsNetlistPassAggregateLoops().runOnHlsNetlist(netlist)
                HlsNetlistPassAggregateIoSyncSccs().runOnHlsNetlist(netlist)
                HlsNetlistPassAggregateBitwiseOps().runOnHlsNetlist(netlist)

                DBG(D.DBG_17_netlistAggregated, (netlist,))

                try:
                    netlist.getAnalysis(HlsNetlistAnalysisPassRunScheduler)
                except Exception as e:
                    # try to debug scheduling if something went wrong
                    try:
                        DBG(D.DBG_18_hwscheduleErr, (netlist,), constructorKwargs=dict(
                            expandCompositeNodes=self._debugExpandCompositeNodes))
                        DBG(D.DBG_23_finalNetlist, (netlist,), constructorKwargs=dict(showVoid=True))
                        DBG(D.DBG_23_finalNetlistTxt, (netlist,))

                    except:
                        raise AssertionError("HlsNetlistAnalysisPassRunScheduler failed and DBG_18_hwscheduleErr also failed") from e
                    raise

                HlsNetlistPassDisaggregateAggregates().runOnHlsNetlist(netlist)
                if self.runHlsNetlistPostSchedulingPasses(hls, netlist):
                    netlist.invalidateAnalysis(HlsNetlistAnalysisPassRunScheduler)
                else:
                    break
        finally:
            if doCloseTrace:
                dbgTracer._out.close()

        HlsNetlistPassRomDeduplication().runOnHlsNetlist(netlist)
        # merge buffers between same times in same arch element
        # HlsNetlistPassBackedgeBufferMerge().runOnHlsNetlist(netlist)
        DBG(D.DBG_19_hwschedule, (netlist,), constructorKwargs=dict(
            expandCompositeNodes=self._debugExpandCompositeNodes))
        DBG(HlsNetlistPassConsystencyCheck, (netlist,))

    def runHlsNetlistPostSchedulingPasses(self, hls: "HlsScope", netlist: HlsNetlistCtx) -> bool:
        modified = False
        return modified

    def runHlsNetlistToArchNetlist(self, hls: "HlsScope", netlist: HlsNetlistCtx):
        DBG = self._debug.runDebugIfEnabled
        D = HlsDebugBundle
        DBG(HlsNetlistPassConsystencyCheck, (netlist,))
        if self._debug.dir is not None:
            netlist.scheduler._checkAllNodesScheduled()

        try:
            HlsNetlistPassCreateIoClusters().runOnHlsNetlist(netlist)
        except:
            # dump netlist if something went frong
            DBG.runDebugIfEnabled(D.DBG_23_finalNetlist, (netlist,), constructorKwargs=dict(showVoid=True))
            DBG.runDebugIfEnabled(D.DBG_23_finalNetlistTxt, (netlist,))
            raise

        dbgTracer, doCloseTrace = self._getDebugTracer(netlist.label, D.DBG_20_netlistSyncIslandsTrace)

        try:
            netlist.getAnalysis(HlsNetlistAnalysisPassBetweenSyncIslands)  # done explicitly to trigger potential exception there
            DBG(HlsNetlistPassBetweenSyncIslandsConsystencyCheck, (netlist,))
            HlsNetlistPassBetweenSyncIslandsMerge(dbgTracer).runOnHlsNetlist(netlist)
            DBG(HlsNetlistPassBetweenSyncIslandsConsystencyCheck, (netlist,))
        finally:
            DBG(D.DBG_20_netlistSyncIslands, (netlist,))
            if doCloseTrace:
                dbgTracer._out.close()

        try:
            HlsNetlistPassAggregateArchElements(netlist._dbgAddSignalNamesToSync).runOnHlsNetlist(netlist)
            DBG(lambda: HlsNetlistPassConsystencyCheck(
                checkCycleFree=False, checkAllArchElementPortsInSameClockCycle=True), (netlist,))

            DBG(D.DBG_20_addSignalNamesToSync, (netlist,))
            DBG(D.DBG_20_addSignalNamesToData, (netlist,))

        except Exception as e:
            try:
                DBG(D.DBG_23_finalNetlist, (netlist,), constructorKwargs=dict(showVoid=True))
                DBG(D.DBG_23_finalNetlistTxt, (netlist,))
            except:
                raise AssertionError("Previous pass failed and dump of netlist also failed") from e
                  
            raise

    def runArchNetlistToRtlNetlist(self, hls: "HlsScope", netlist: HlsNetlistCtx):
        DBG = self._debug.runDebugIfEnabled
        D = HlsDebugBundle
        try:
            RtlArchPassLoopControlPrivatization().runOnHlsNetlist(netlist)
            DBG(D.DBG_21_finalHwschedule, (netlist,), constructorKwargs=dict(
                              expandCompositeNodes=self._debugExpandCompositeNodes))

            RtlArchPassMergeTiedFsms().runOnHlsNetlist(netlist)
            RtlArchPassArchStructureSimplfy().runOnHlsNetlist(netlist)
            DBG(lambda: HlsNetlistPassConsystencyCheck(checkCycleFree=False), (netlist,))

            dbgTracer, doCloseTrace = self._getDebugTracer(netlist.label, D.DBG_22_netlistChannelMergeTrace)
            try:
                RtlArchPassChannelMerge(dbgTracer).runOnHlsNetlist(netlist)
            finally:
                if doCloseTrace:
                    dbgTracer._out.close()

            DBG(lambda: HlsNetlistPassConsystencyCheck(checkCycleFree=False), (netlist,))

            RtlArchPassIoPortPrivatization().runOnHlsNetlist(netlist)
            DBG(lambda: HlsNetlistPassConsystencyCheck(
                checkCycleFree=False, checkAllArchElementPortsInSameClockCycle=True), (netlist,))
            # RtlArchPassMoveArchElementPortsToMinimizeSync().runOnHlsNetlist(netlist)
            RtlArchPassAddImplicitSyncChannels().runOnHlsNetlist(netlist)
            DBG(lambda: HlsNetlistPassConsystencyCheck(checkCycleFree=False, checkAllArchElementPortsInSameClockCycle=True),
                (netlist,))
            RtlArchPassChannelReduceSyncStrength().runOnHlsNetlist(netlist)
            DBG(D.DBG_22_handshakeSCCs, (netlist,))
            RtlArchPassChannelHandshakeCycleBreak().runOnHlsNetlist(netlist)
        finally:
            DBG(D.DBG_23_finalNetlist, (netlist,), constructorKwargs=dict(showVoid=True))
            DBG(D.DBG_23_finalNetlistTxt, (netlist,))

        for e in netlist.nodes:
            e: ArchElement
            e.rtlAllocDatapath()

        # :note: must be after finalizeInterElementsConnections because it needs inter element sync channels
        DBG(D.DBG_23_arch, (netlist,))

        for e in netlist.nodes:
            e: ArchElement
            e.rtlAllocSync()

    def runHlsAndRtlNetlistPasses(self, hls: "HlsScope", netlist: HlsNetlistCtx):
        DBG = self._debug.runDebugIfEnabled
        D = HlsDebugBundle

        HlsAndRtlNetlistPassControlLogicMinimize().runOnHlsNetlist(netlist)
        DBG(D.DBG_24_sync, (netlist,))
        DBG(D.DBG_25_regFileHierarchy, (netlist,))
