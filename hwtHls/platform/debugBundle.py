from hwtHls.ssa.translation.dumpMIR import SsaPassDumpMIR
from hwtHls.ssa.translation.dumpMirCfg import SsaPassDumpMirCfg
from hwtHls.ssa.translation.toGraphwiz import SsaPassDumpToDot
from hwtHls.ssa.translation.toLl import SsaPassDumpToLl
from typing import Tuple, Type, Optional, Union, Set
from hwtHls.netlist.translation.dumpDataThreads import HlsNetlistAnalysisPassDumpDataThreads
from hwtHls.netlist.translation.dumpBlockSync import HlsNetlistAnalysisPassDumpBlockSync
from hwtHls.netlist.translation.dumpNodesDot import HlsNetlistAnalysisPassDumpNodesDot, \
    HlsNetlistAnalysisPassDumpIoClustersDot
from hwtHls.netlist.translation.dumpNodesTxt import HlsNetlistAnalysisPassDumpNodesTxt
from hwtHls.netlist.translation.dumpSyncDomainsDot import HlsNetlistAnalysisPassDumpSyncDomainsDot
from hwtHls.netlist.translation.dumpSchedulingJson import HlsNetlistAnalysisPassDumpSchedulingJson
from hwtHls.netlist.translation.betweenSyncIslandsToGraphwiz import HlsNetlistAnalysisPassBetweenSyncIslandsToGraphwiz
from hwtHls.architecture.transformation.addSyncSigNames import HlsAndRtlNetlistPassAddSignalNamesToSync, \
    HlsAndRtlNetlistPassAddSignalNamesToData
from hwtHls.architecture.translation.dumpArchDot import RtlArchAnalysisPassDumpArchDot
from hwtHls.architecture.translation.dumpStreamNodes import HlsAndRtlNetlistPassDumpStreamNodes
from hwtHls.architecture.transformation.archElementsToSubunits import RtlArchPassTransplantArchElementsToSubunits
from pathlib import Path
from hwtHls.platform.fileUtils import outputFileGetter
from hwtHls.architecture.translation.dumpHsSCCsDot import RtlArchAnalysisPassDumpHsSCCsDot
from hwtHls.ssa.transformation.ssaPass import SsaPass

DebugId = Tuple[Type, Optional[str]]


class HlsDebugBundle():
    """
    :note: if the number N in DBG_N_* is the same it means that these debug options are working with the same input
    """
    DEFAULT_DEBUG_DIR = "tmp"

    DBG_0_pyFrontedBytecodeTrace = (None, "00.bytecode.trace.txt")  # trace file for operations in during pybytecode translation
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
    DBG_5_netlistConsttructionTrace = (None, "05.netlistConsttructionTrace.txt")  # trace of netlist construction (typically from LLVM MIR)
    DBG_5_dthreads = (HlsNetlistAnalysisPassDumpDataThreads, "05.dthreads.txt")  # instructions packed in data treads
    DBG_6_blockSync = (HlsNetlistAnalysisPassDumpBlockSync, "06.blockSync.dot")  # synchronization features of basic blocks
    DBG_7_preSync = (HlsNetlistAnalysisPassDumpNodesDot, "07.preSync.dot")  # io of basic blocks before implementation of sync
    DBG_8_postRst = (HlsNetlistAnalysisPassDumpNodesDot, "08.postRst.dot")  # basic block io after implementation of reset value extraction
    DBG_9_postLoop = (HlsNetlistAnalysisPassDumpNodesDot, "09.postLoop.dot")  # basic block io after implementation of loops
    DBG_10_postSync = (HlsNetlistAnalysisPassDumpBlockSync, "10.postSync.dot")  # basic block io after implementation of complete control flow sync
    # hls netlist
    DBG_11_netlist = (HlsNetlistAnalysisPassDumpNodesDot, "11.netlist.dot")  # basic blocks disolved to netlist
    DBG_11_netlistTxt = (HlsNetlistAnalysisPassDumpNodesTxt, "11.netlist.txt")  # same as DBG_11_netlist just in txt
    DBG_11_netlistIoClusters = (HlsNetlistAnalysisPassDumpIoClustersDot, "11.netlistIoClusters.dot")  #
    DBG_12_netlistSimplifyTrace = (None, "12.netlistSimplifyTrace.txt")  # trace of netlist simplifier
    DBG_12_netlistSimplifiedErr = (HlsNetlistAnalysisPassDumpNodesDot, "12.netlistSimplified.err.dot")  # try to dump netlist if simplified failed
    DBG_14_netlistSimplified = (HlsNetlistAnalysisPassDumpNodesDot, "14.netlistSimplified.dot")  # dump simplified netlist
    DBG_14_netlistSimplifiedTxt = (HlsNetlistAnalysisPassDumpNodesTxt, "14.netlistSimplified.txt")  # same as DBG_13_netlistSimplified just in txt
    DBG_14_netlistSimplifiedIoClusters = (HlsNetlistAnalysisPassDumpIoClustersDot, "14.netlistSimplifiedIoClusters.dot")
    DBG_14_netlistSyncDomains = (HlsNetlistAnalysisPassDumpSyncDomainsDot, "14.netlistSyncDomains.dot")  # dump association of IO to individual logic node clouds
    DBG_17_netlistAggregated = (HlsNetlistAnalysisPassDumpNodesDot, "17.netlistAggregated.dot")  # dump netlist after selected nodes were agregated to scheduling primitives
    DBG_18_hwscheduleErr = (HlsNetlistAnalysisPassDumpSchedulingJson, "18.hwschedule.err.json")  # try dump scheduling if scheduler failed
    DBG_19_hwschedule = (HlsNetlistAnalysisPassDumpSchedulingJson, "19.hwschedule.json")  # node scheduling after first scheduling atempt
    # arch gen
    DBG_20_netlistSyncIslandsTrace = (None, "20.netlistSyncIslandsTrace.txt")  # trace of sync islands simplifier
    DBG_20_netlistSyncIslands = (HlsNetlistAnalysisPassBetweenSyncIslandsToGraphwiz, "20.netlistSyncIslands.dot")  # dump transitive enclosure of DBG_15_syncDomains
    DBG_20_addSignalNamesToSync = (HlsAndRtlNetlistPassAddSignalNamesToSync, None)  # signal names are directly in output RTL
    DBG_20_addSignalNamesToData = (HlsAndRtlNetlistPassAddSignalNamesToData, None)  # signal names are directly in output RTL
    DBG_21_finalHwschedule = (HlsNetlistAnalysisPassDumpSchedulingJson, "21.final.hwschedule.json")  # node scheduling which will be used to generate circuit
    DBG_22_netlistChannelMergeTrace = (None, "22.netlistChannelMergeTrace.txt")  # trace of c
    DBG_22_handshakeSCCs = (RtlArchAnalysisPassDumpHsSCCsDot, "22.hanshakeSCCs.dot")
    DBG_23_finalNetlist = (HlsNetlistAnalysisPassDumpNodesDot, "22.final.netlist.dot")  # basic blocks disolved to netlist
    DBG_23_finalNetlistTxt = (HlsNetlistAnalysisPassDumpNodesTxt, "22.final.netlist.txt")  # same as DBG_11_netlist just in txt
    DBG_23_arch = (RtlArchAnalysisPassDumpArchDot, "22.arch.dot")  # relations between arch elements in whole generated architecutre
    DBG_24_sync = (HlsAndRtlNetlistPassDumpStreamNodes, "22.sync.txt")  # control expressions of IO, FSMs and pipelines
    DBG_25_regFileHierarchy = (RtlArchPassTransplantArchElementsToSubunits, None)  # extract registers in pipeline stage or fsm to separate component

    ALL = None
    NONE = {}
    # all without DBG_20_addSignalNamesToSync, DBG_24_regFileHierarchy because it changes optimization behavior

    # :note: ALL_RELIABLE refers to passes which do not require intense circuit analysis. This often fails on a broken circuit.
    #        Reliable debug options do not contain expensive debug options and are meant for detection of the bugs. The expensive debug options
    #        are used for deeper circuit analysis or circuit rewrites for improving readability.

    # :note: reliable refers to a passes which do not require intense circuit analysis which often fails on broken circuit
    #        that said reliable debug options are meant for detection of the bugs and does not contain expensive debug options
    #        which are used for deeper circuit analysis or circuit rewrites for improving of readability
    ALL_RELIABLE = {
        DBG_0_pyFrontedBytecode,
        DBG_0_pyFrontedBeginCfg,
        DBG_0_pyFrontedFinalCfg,
        DBG_0_preSsaOpt,
        DBG_1_frontend,
        DBG_2_preLlvm,
        DBG_3_mir,
        DBG_4_mirCfg,
        DBG_5_netlistConsttructionTrace,
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
        DBG_22_netlistChannelMergeTrace,
        DBG_22_handshakeSCCs,
        DBG_23_finalNetlist,
        DBG_23_finalNetlistTxt,
        DBG_23_arch,
        DBG_24_sync,
    }
    DEFAULT = NONE

    # bundles of debug features to debug problems in a specific phase of compilation
    DBG_FRONTEND = {
        DBG_0_pyFrontedBytecodeTrace,
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
        DBG_5_netlistConsttructionTrace,
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
        DBG_20_addSignalNamesToSync,
        DBG_21_finalHwschedule,
    }
    DBG_ARCH_SYNC = {
        DBG_3_mir,
        DBG_14_netlistSyncDomains,
        DBG_20_netlistSyncIslandsTrace,
        DBG_20_netlistSyncIslands,
        DBG_20_addSignalNamesToSync,
        DBG_21_finalHwschedule,
        DBG_22_netlistChannelMergeTrace,
        DBG_22_handshakeSCCs,
        DBG_23_finalNetlist,
        DBG_23_finalNetlistTxt,
        DBG_23_arch,
        DBG_24_sync,
    }

    def __init__(self, debugDir:Optional[Union[str, Path]], filter_: Optional[Set[DebugId]]):
        """
        :attention: if debugDir is None no debug option will be enabled
        """
        self.dir = None if debugDir is None else Path(debugDir)
        self.filter = filter_
        self.firstRun = True
        self.runConsystencyChecks = True

    def isActivated(self, item: DebugId):
        return self.filter is None or item in self.filter

    def runDebugIfEnabled(self, id_: Union[DebugId, Type], applyArgs: tuple,
                          clsOverride: Optional[Type]=None,
                          applyFnGetter=lambda p: p.runOnHlsNetlist,
                          constructorArgs: tuple=(),
                          constructorKwargs: dict={}):
        debugDir = self.dir
        isDebugId = isinstance(id_, tuple)
        if debugDir is not None and (not isDebugId or self.isActivated(id_)):
            if self.firstRun:
                if debugDir and not debugDir.exists():
                    debugDir.mkdir()
                self.firstRun = False

            if not isDebugId:
                assert clsOverride is None
                cls = id_
            elif clsOverride is None:
                cls = id_[0]
            else:
                cls = clsOverride

            if not isDebugId:
                obj = cls(*constructorArgs, **constructorKwargs)
            else:
                _, fileNameSuffix = id_
                if fileNameSuffix is not None:
                    outStreamGetter = outputFileGetter(debugDir, fileNameSuffix)
                    obj = cls(outStreamGetter, *constructorArgs, **constructorKwargs)
                else:
                    obj = cls(*constructorArgs, **constructorKwargs)

            applyFn = applyFnGetter(obj)
            applyFn(*applyArgs)

    # def runAssertIfEnabled(self, cls: Type, args:tuple, constructorArgs: tuple=(),
    #                      constructorKwargs: dict={}):
    #    if self.dir is not None:
    #        obj = cls(*constructorArgs, **constructorKwargs)
    #        if issubclass(cls, SsaPass):
    #            obj.runOnSsaModule(*args)
    #        else:
    #            obj.runOnHlsNetlist(*args)
