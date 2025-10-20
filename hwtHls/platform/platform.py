from io import StringIO
from pathlib import Path
import sys
from typing import Optional, Union, Type

from hwt.hdl.operatorDefs import HOperatorDef
from hwt.hwModule import HwModule
from hwt.serializer.resourceAnalyzer.resourceTypes import RtlResourceType
from hwt.synthesizer.dummyPlatform import DummyPlatform
from hwtHls.architecture.componentGenerator import ComponentGenerator
from hwtHls.architecture.transformation.addImplicitSyncChannels import HlsArchPassAddImplicitSyncChannels
from hwtHls.architecture.transformation.addRtlSigNames import HlsAndRtlNetlistPassAddSignalForDeepExpr
from hwtHls.architecture.transformation.archStructureSimplify import HlsArchPassArchStructureSimplify
from hwtHls.architecture.transformation.channelMerge import RtlArchPassChannelMerge
from hwtHls.architecture.transformation.channelReduceSyncStrength import HlsArchPassChannelReduceSyncStrength
from hwtHls.architecture.transformation.channelReduceUselessValid import HlsArchPassChannelReduceUselessValid
from hwtHls.architecture.transformation.controlLogicMinimize import HlsAndRtlNetlistPassControlLogicMinimize
from hwtHls.architecture.transformation.fsmStateNextWriteConstruction import HlsAndRtlNetlistPassFsmStateNextWriteConstruction
from hwtHls.architecture.transformation.ioPortPrivatization import HlsArchPassIoPortPrivatization
from hwtHls.architecture.transformation.loopControlLowering import HlsAndRtlNetlistPassLoopControlLowering
from hwtHls.architecture.transformation.moveArchElementPortsToMinimizeSync import HlsArchPassMoveArchElementPortsToMinimizeSync
from hwtHls.architecture.transformation.syncLowering import HlsArchPassSyncLowering
from hwtHls.llvm.llvmIr import MachineFunction, MachineBasicBlock, Register, MachineLoopInfo, ModulePassManager, \
    IoLowerAxiMMPass
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
from hwtHls.netlist.transformation.operatorToHwtLowering import HlsNetlistPassOperatorToHwtLowering
from hwtHls.netlist.transformation.readSyncToAckOfIoNodes import HlsNetlistPassReadSyncToAckOfIoNodes
from hwtHls.netlist.transformation.romDeduplication import HlsNetlistPassRomDeduplication
from hwtHls.netlist.transformation.simplify import HlsNetlistPassSimplify
from hwtHls.netlist.transformation.simplifyExpr.trivialSimplifyExplicitSync import HlsNetlistPassTrivialSimplifyExplicitSync
from hwtHls.platform.debugBundle import HlsDebugBundle, DebugId
from hwtHls.platform.debugBundleTypes import LlvmCliArgTuple
from hwtHls.platform.fileUtils import outputFileGetter
from hwtHls.ssa.analysis.consistencyCheck import SsaPassConsistencyCheck
from hwtHls.ssa.translation.llvmMirToNetlist.datapath import BlockLiveInMuxSyncDict
from hwtHls.ssa.translation.llvmMirToNetlist.mirToNetlist import HlsNetlistAnalysisPassMirToNetlist
from hwtHls.ssa.translation.toLlvm import ToLlvmIrTranslator
from hwtHls.ssa.translation.toLlvmUtils import getIoNodeConstructors


ComponentGeneratorDict = dict[Union[Type[RtlResourceType], RtlResourceType, Type["HlsNetNode"], HOperatorDef],
                                        ComponentGenerator]


class DefaultHlsPlatform(DummyPlatform):
    """
    A base platform which is a container of target config and compilation pipeline configuration.
    
    :ivar _componentGenerators: dictionary of generators which are used to resolve properties
        (scheduling, resources) of intrinsic-like nodes and to translate them into RLT in final phase.
    :ivar schedulerCls: type of scheduler to use
    :ivar _debug: an object holding debug configuration values
    :ivar _debugExpandCompositeNodes: debug option which expands all composite nodes
        during dumps of HlsNetlist
    :ivar _llvmCliArgs: llvm CLI arguments which are passed to compilation of main functions
    """

    def __init__(self, debugDir:Optional[Union[str, Path]]=HlsDebugBundle.DEFAULT_DEBUG_DIR,
                 debugFilter: Optional[set[DebugId]]=HlsDebugBundle.DEFAULT,
                 llvmCliArgs: list[LlvmCliArgTuple]=[]):
        DummyPlatform.__init__(self)
        self.schedulerCls = HlsScheduler
        self._componentGenerators: ComponentGeneratorDict = {}
        self._debug = HlsDebugBundle(debugDir, debugFilter)
        self._debugExpandCompositeNodes = False
        self._llvmCliArgs: list[LlvmCliArgTuple] = llvmCliArgs
        self._llvmIoLowerPasses: list["ModulePass"] = []

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
        thread.prepareLlvmTranslator()
        thread.debugCopyConfig(self)

    def runSsaPasses(self, hls: "HlsScope", toLlvm: ToLlvmIrTranslator):
        DBG = self._debug.runDebugIfEnabled
        DBG(HlsDebugBundle.DBG_1_0_preLlvm, (toLlvm,), applyFnGetter=_runOnSsaModuleGetter)
        DBG(SsaPassConsistencyCheck, (toLlvm,), applyFnGetter=_runOnSsaModuleGetter)

    def installLlvmIoLowerPass(self, modulePassCls: "ModulePass"):
        passes = self._llvmIoLowerPasses
        if modulePassCls not in passes:
            passes.append(modulePassCls)

    def addExtraModulePasses(self, MPM: ModulePassManager):
        for pCls in self._llvmIoLowerPasses:
            MPM.addPass(pCls())

    def runSsaToNetlist(self, hls: "HlsScope", toLlvm: ToLlvmIrTranslator, netlist: HlsNetlistCtx) -> HlsNetlistCtx:
        """
        :param hls: compilation scope
        :param toLlvm: object which providing LLVM IR for to netlist translation
        :param netlist: netlist object where translated netlist nodes should be placed
        """
        assert isinstance(toLlvm, ToLlvmIrTranslator), toLlvm
        toLlvm.llvm.runOpt(self.runMirToHlsNetlist, self.addExtraModulePasses, hls, toLlvm, netlist)
        netlist._channelsBetweenLlvmThreads = None  # delete because MachineFunctions are deallocated

    def runMirToHlsNetlist(self,
                           hls: "HlsScope",
                           toLlvm: ToLlvmIrTranslator,
                           netlist: HlsNetlistCtx,
                           mf: MachineFunction,
                           backedges: set[tuple[MachineBasicBlock, MachineBasicBlock]],
                           liveness: dict[MachineBasicBlock, dict[MachineBasicBlock, set[Register]]],
                           ioRegs: list[Register],
                           registerTypes: dict[Register, int],
                           loops: MachineLoopInfo):
        """
        :attention: This function is called from c++ at the end of llvm pipeline.
          It is implemented in this way to allow access to analysis in llvm pass manager.
        :note: this function may be called multipletimes for single llvm::Module if it contains mutiple function. 
        """
        assert isinstance(toLlvm, ToLlvmIrTranslator), toLlvm
        DBG = self._debug.runDebugIfEnabled
        D = HlsDebugBundle
        DBG(D.DBG_2_0_mir, (toLlvm, mf), applyFnGetter=_runOnSsaModuleGetter)
        DBG(D.DBG_2_0_mirCfg, (toLlvm, mf), applyFnGetter=_runOnSsaModuleGetter)

        dbgTracer, doCloseTrace = self._getDebugTracer(netlist.label, D.DBG_2_1_netlistConstructionTrace)
        netlist.dbgSubmoduleBuidTracer, submoduleBuildDbgTracerDoClose = self._getDebugTracer(netlist.label, D.DBG_2_1_submoduleBuildLogMir)

        toNetlist = HlsNetlistAnalysisPassMirToNetlist(
            hls, toLlvm, mf, backedges, liveness, ioRegs, registerTypes,
            loops, netlist, getIoNodeConstructors(toLlvm), dbgTracer)

        initSchedulingResourceConstraintsFromIO(netlist.scheduler.resourceUsage.resourceConstraints,
                                                (io[0] for io in toLlvm.ioSorted))
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
            if submoduleBuildDbgTracerDoClose:
                netlist.dbgSubmoduleBuidTracer._out.close()
            netlist.dbgSubmoduleBuidTracer = None

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

        assert netlist.dbgSubmoduleBuidTracer is None
        netlist.dbgSubmoduleBuidTracer, submoduleBuildDbgTracerDoClose = self._getDebugTracer(netlist.label, D.DBG_3_4_submoduleBuildLogPreSchedule)
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
                        raise AssertionError("HlsNetlistPassSimplify failed and DBG_3_1_netlistSimplifiedErr also failed") from e
                    raise
                with netlist.dbgSubmoduleBuidTracer.scoped((HlsNetlistPassOperatorToHwtLowering, "preSchedule"), None):
                    HlsNetlistPassOperatorToHwtLowering(isScheduled=False, debugTracer=netlist.dbgSubmoduleBuidTracer).runOnHlsNetlist(netlist)

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

                with netlist.dbgSubmoduleBuidTracer.scoped(HlsNetlistAnalysisPassRunScheduler, None):
                    try:
                        netlist.getAnalysis(HlsNetlistAnalysisPassRunScheduler)
                    except Exception as e:
                        # try to debug scheduling if something went wrong
                        try:
                            DBG(D.DBG_4_0_hwscheduleErr, (netlist,), constructorKwargs=dict(
                                expandCompositeNodes=self._debugExpandCompositeNodes))
                        except:
                            raise AssertionError("HlsNetlistAnalysisPassRunScheduler failed and DBG_4_0_hwscheduleErr also failed") from e
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
            if submoduleBuildDbgTracerDoClose:
                netlist.dbgSubmoduleBuidTracer._out.close()
            netlist.dbgSubmoduleBuidTracer = None
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
            assert netlist.dbgSubmoduleBuidTracer is None
            netlist.dbgSubmoduleBuidTracer, doCloseTrace = self._getDebugTracer(netlist.label, D.DBG_4_0_submoduleBuildLogPostSchedule)
            try:
                HlsNetlistPassOperatorToHwtLowering(isScheduled=True, debugTracer=netlist.dbgSubmoduleBuidTracer).runOnHlsNetlist(netlist)
            finally:
                if doCloseTrace:
                    netlist.dbgSubmoduleBuidTracer._out.close()
                netlist.dbgSubmoduleBuidTracer = None

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
            HlsArchPassSyncLowering(dbgDumpNodes=self._debug.isActivated((HlsArchPassSyncLowering, "nodes")),
                                    dbgDumpAbc=self._debug.isActivated((HlsArchPassSyncLowering, "abc"))
                                    ).runOnHlsNetlist(netlist)
            DBG(lambda: HlsNetlistPassConsistencyCheck(checkCycleFree=False,
                                                       checkAllArchElementPortsInSameClockCycle=False),
                (netlist,))

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
        DBG(D.DBG_4_4_archBasic, (netlist,), constructorKwargs=dict(hideSyncLogic=True, hideFunctionalUnits=True))
        DBG(D.DBG_4_4_archCoarse, (netlist,), constructorKwargs=dict(hideSyncLogic=True))
        DBG(D.DBG_4_4_archDetail, (netlist,))

        for e in netlist.iterAllNodes():
            e: ArchElement
            e.rtlAllocSync()

    def runHlsAndRtlNetlistPasses(self, hls: "HlsScope", netlist: HlsNetlistCtx):
        DBG = self._debug.runDebugIfEnabled
        D = HlsDebugBundle

        HlsAndRtlNetlistPassControlLogicMinimize().runOnHlsNetlist(netlist)
        DBG(D.DBG_4_5_sync, (netlist,))
        DBG(D.DBG_4_5_regFileHierarchy, (netlist,))
