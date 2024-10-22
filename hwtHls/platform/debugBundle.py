from pathlib import Path
from typing import Tuple, Type, Optional, Union, Set

from hwtHls.architecture.transformation.addRtlSigNames import HlsAndRtlNetlistPassAddSignalNamesToSync, \
    HlsAndRtlNetlistPassAddSignalNamesToData
from hwtHls.architecture.transformation.archElementsToSubunits import RtlArchPassTransplantArchElementsToSubunits
from hwtHls.architecture.translation.dumpArchDot import RtlArchAnalysisPassDumpArchDot
from hwtHls.architecture.translation.dumpHsSCCsDot import RtlArchAnalysisPassDumpHsSCCsDot
from hwtHls.architecture.translation.dumpStreamNodes import HlsAndRtlNetlistPassDumpStreamNodes
from hwtHls.netlist.translation.dumpBlockSync import HlsNetlistAnalysisPassDumpBlockSync
from hwtHls.netlist.translation.dumpNodesDot import HlsNetlistAnalysisPassDumpNodesDot, \
    HlsNetlistAnalysisPassDumpIoClustersDot
from hwtHls.netlist.translation.dumpNodesTxt import HlsNetlistAnalysisPassDumpNodesTxt
from hwtHls.netlist.translation.dumpSchedulingJson import HlsNetlistAnalysisPassDumpSchedulingJson
from hwtHls.netlist.translation.dumpSyncDomainsDot import HlsNetlistAnalysisPassDumpSyncDomainsDot
from hwtHls.platform.fileUtils import outputFileGetter
from hwtHls.ssa.translation.dumpMIR import SsaPassDumpMIR
from hwtHls.ssa.translation.dumpMirCfg import SsaPassDumpMirCfg
from hwtHls.ssa.translation.toGraphviz import SsaPassDumpToDot
from hwtHls.ssa.translation.toLl import SsaPassDumpToLl

DebugId = Tuple[Type, Optional[str]]


class HlsDebugBundle():
    """
    :note: if the number N in DBG_N_* is the same it means that these debug options are working with the same input
    """
    DEFAULT_DEBUG_DIR = "tmp"

    DBG_0_0_pyFrontedBytecodeTrace = (None, "00.00.bytecode.trace.txt")  # trace file for operations in during pybytecode translation
    DBG_0_0_pyFrontedBytecode = (None, "00.00.bytecode.{0}.txt")  # bytecode for every translated function
    DBG_0_0_pyFrontedBeginCfg = (None, "00.00.cfg.begin.{0}.dot")  # initial CFG after parsing of bytecode
    DBG_0_0_pyFrontedPreprocCfg = (None, "00.00.cfg.{0}.dot")  # step by step CFG during preprocessor evaluation
    DBG_0_1_pyFrontedFinalCfg = (None, "00.01.cfg.final.{0}.dot")  # final CFG after preprocessor execution

    # ssa
    DBG_1_0_preSsaOpt = (SsaPassDumpToDot, "01.00.preSsaOpt.dot")  # raw input code
    DBG_1_1_frontend = (SsaPassDumpToDot, "01.01.frontend.dot")  # after frontend transformations
    DBG_1_2_preLlvm = (SsaPassDumpToLl, "01.02.preLlvm.ll")  # translated to LLVM IR
    # mir
    DBG_2_0_mir = (SsaPassDumpMIR, "02.00.mir.ll")  # translated and optimized to LLVM MIR by LLVM
    DBG_2_0_mirCfg = (SsaPassDumpMirCfg, "02.00.mirCfg.dot")  # Control Flow Graph of MIR
    DBG_2_1_netlistConstructionTrace = (None, "02.01.netlistConstructionTrace.txt")  # trace of netlist construction (typically from LLVM MIR)
    DBG_2_1_blockSync = (HlsNetlistAnalysisPassDumpBlockSync, "02.01.blockSync.dot")  # synchronization features of basic blocks
    DBG_2_2_preSync = (HlsNetlistAnalysisPassDumpNodesDot, "02.02.preSync.dot")  # io of basic blocks before implementation of sync
    DBG_2_3_postRst = (HlsNetlistAnalysisPassDumpNodesDot, "02.03.postRst.dot")  # basic block io after implementation of reset value extraction
    DBG_2_4_postLoop = (HlsNetlistAnalysisPassDumpNodesDot, "02.04.postLoop.dot")  # basic block io after implementation of loops
    DBG_2_5_postSync = (HlsNetlistAnalysisPassDumpBlockSync, "02.05.postSync.dot")  # basic block io after implementation of complete control flow sync
    # hls netlist
    DBG_3_0_netlist = (HlsNetlistAnalysisPassDumpNodesDot, "03.00.netlist.dot")  # basic blocks dissolved to netlist
    DBG_3_0_netlistTxt = (HlsNetlistAnalysisPassDumpNodesTxt, "03.00.netlist.txt")  # same as DBG_3_0_netlist just in txt
    DBG_3_0_netlistIoClusters = (HlsNetlistAnalysisPassDumpIoClustersDot, "03.00.netlistIoClusters.dot")  #
    DBG_3_1_netlistSimplifyTrace = (None, "03.01.netlistSimplifyTrace.txt")  # trace of netlist simplifier
    DBG_3_1_netlistSimplifiedErr = (HlsNetlistAnalysisPassDumpNodesDot, "03.01.netlistSimplified.err.dot")  # try to dump netlist if simplified failed
    DBG_3_2_netlistSimplified = (HlsNetlistAnalysisPassDumpNodesDot, "03.02.netlistSimplified.dot")  # dump simplified netlist
    DBG_3_2_netlistSimplifiedTxt = (HlsNetlistAnalysisPassDumpNodesTxt, "03.02.netlistSimplified.txt")  # same as DBG_13_netlistSimplified just in txt
    DBG_3_2_netlistSimplifiedIoClusters = (HlsNetlistAnalysisPassDumpIoClustersDot, "03.02.netlistSimplifiedIoClusters.dot")
    DBG_3_2_netlistSyncDomains = (HlsNetlistAnalysisPassDumpSyncDomainsDot, "03.02.netlistSyncDomains.dot")  # dump association of IO to individual logic node clouds
    DBG_3_3_netlistAggregated = (HlsNetlistAnalysisPassDumpNodesDot, "03.03.netlistAggregated.dot")  # dump netlist after selected nodes were agregated to scheduling primitives
    DBG_4_0_hwscheduleErr = (HlsNetlistAnalysisPassDumpSchedulingJson, "04.00.hwschedule.err.json")  # try dump scheduling if scheduler failed
    DBG_4_0_hwschedule = (HlsNetlistAnalysisPassDumpSchedulingJson, "04.00.hwschedule.json")  # node scheduling after first scheduling atempt
    # arch gen
    DBG_4_0_addSignalNamesToSync = (HlsAndRtlNetlistPassAddSignalNamesToSync, None)  # signal names are directly in output RTL
    DBG_4_0_addSignalNamesToData = (HlsAndRtlNetlistPassAddSignalNamesToData, None)  # signal names are directly in output RTL
    DBG_4_1_finalHwschedule = (HlsNetlistAnalysisPassDumpSchedulingJson, "04.01.final.hwschedule.json")  # node scheduling which will be used to generate circuit

    DBG_4_2_netlistChannelMergeTrace = (None, "04.02.netlistChannelMergeTrace.txt")  # trace of channel merging
    DBG_4_3_handshakeSCCs = (RtlArchAnalysisPassDumpHsSCCsDot, "04.03.hanshakeSCCs.dot")  # handshake SCCs for sync debugging
    DBG_4_3_netlistBeforSyncLoweingDot = (HlsNetlistAnalysisPassDumpNodesDot, "04.03.netlist.beforeSyncLowering.dot")  # scheduled simplified netlist
    DBG_4_3_netlistBeforSyncLoweingTxt = (HlsNetlistAnalysisPassDumpNodesTxt, "04.03.netlist.beforeSyncLowering.txt")  # same as DBG_4_3_netlistBeforSyncLoweingDot just in txt

    DBG_4_4_finalNetlist = (HlsNetlistAnalysisPassDumpNodesDot, "04.04.final.netlist.dot")  # basic blocks dissolved to netlist
    DBG_4_4_finalNetlistTxt = (HlsNetlistAnalysisPassDumpNodesTxt, "04.04.final.netlist.txt")  # same as DBG_4_4_finalNetlist just in txt
    DBG_4_4_arch = (RtlArchAnalysisPassDumpArchDot, "04.04.arch.dot")  # relations between arch elements in whole generated architecutre
    DBG_4_5_sync = (HlsAndRtlNetlistPassDumpStreamNodes, "04.05.sync.txt")  # control expressions of IO, FSMs and pipelines
    DBG_4_5_regFileHierarchy = (RtlArchPassTransplantArchElementsToSubunits, None)  # extract registers in pipeline stage or fsm to separate component

    ALL = None
    NONE = {}
    # all without DBG_4_0_addSignalNamesToSync, DBG_24_regFileHierarchy because it changes optimization behavior

    # :note: ALL_RELIABLE refers to passes which do not require intense circuit analysis. This often fails on a broken circuit.
    #        Reliable debug options do not contain expensive debug options and are meant for detection of the bugs. The expensive debug options
    #        are used for deeper circuit analysis or circuit rewrites for improving readability.

    # :note: reliable refers to a passes which do not require intense circuit analysis which often fails on broken circuit
    #        that said reliable debug options are meant for detection of the bugs and does not contain expensive debug options
    #        which are used for deeper circuit analysis or circuit rewrites for improving of readability
    ALL_RELIABLE = {
        DBG_0_0_pyFrontedBytecode,
        DBG_0_0_pyFrontedBeginCfg,
        DBG_0_1_pyFrontedFinalCfg,
        DBG_1_0_preSsaOpt,
        DBG_1_1_frontend,
        DBG_1_2_preLlvm,
        DBG_2_0_mir,
        DBG_2_0_mirCfg,
        DBG_2_1_netlistConstructionTrace,
        DBG_2_1_blockSync,
        DBG_2_2_preSync,
        DBG_2_3_postRst,
        DBG_2_4_postLoop,
        DBG_2_5_postSync,
        DBG_3_0_netlist,
        DBG_3_0_netlistTxt,
        DBG_3_0_netlistIoClusters,
        DBG_3_1_netlistSimplifyTrace,
        DBG_3_1_netlistSimplifiedErr,
        DBG_3_2_netlistSimplified,
        DBG_3_2_netlistSimplifiedTxt,
        DBG_3_2_netlistSimplifiedIoClusters,
        DBG_3_2_netlistSyncDomains,
        DBG_3_3_netlistAggregated,
        DBG_4_0_hwscheduleErr,
        DBG_4_0_hwschedule,
        DBG_4_1_finalHwschedule,
        DBG_4_2_netlistChannelMergeTrace,
        DBG_4_3_handshakeSCCs,
        DBG_4_3_netlistBeforSyncLoweingDot,
        DBG_4_3_netlistBeforSyncLoweingTxt,
        DBG_4_4_finalNetlist,
        DBG_4_4_finalNetlistTxt,
        DBG_4_4_arch,
        DBG_4_5_sync,
    }
    DEFAULT = NONE

    # bundles of debug features to debug problems in a specific phase of compilation
    DBG_FRONTEND = {
        DBG_0_0_pyFrontedBytecodeTrace,
        DBG_0_0_pyFrontedBytecode,
        DBG_0_0_pyFrontedBeginCfg,
        DBG_0_0_pyFrontedPreprocCfg,
        DBG_0_1_pyFrontedFinalCfg,
        DBG_1_0_preSsaOpt,
        DBG_1_1_frontend
    }
    # bundle for debugging of translation of LLVM to HlsNetlist
    DBG_NETLIST_GEN = {
        DBG_2_0_mir,
        DBG_2_0_mirCfg,
        DBG_2_1_netlistConstructionTrace,
        DBG_2_1_blockSync,
        DBG_2_2_preSync,
        DBG_2_3_postRst,
        DBG_2_4_postLoop,
        DBG_2_5_postSync,
        DBG_3_0_netlist,
    }
    # bundle for debugging of netlist optimizations
    DBG_NETLIST_OPT = {
        DBG_3_0_netlist,
        DBG_3_0_netlistTxt,
        DBG_3_0_netlistIoClusters,
        DBG_3_1_netlistSimplifyTrace,
        DBG_3_1_netlistSimplifiedErr,
        DBG_3_2_netlistSimplified,
        DBG_3_2_netlistSimplified,
        DBG_3_2_netlistSyncDomains,
    }
    # bundle for debugging of scheduler
    DBG_SCHEDULING = {
        DBG_3_3_netlistAggregated,
        DBG_4_0_hwscheduleErr,
        DBG_4_0_hwschedule,
        DBG_4_0_addSignalNamesToSync,
        DBG_4_1_finalHwschedule,
    }
    # bundle for debugging on architectural level
    DBG_ARCH_SYNC = {
        DBG_2_0_mir,
        DBG_3_2_netlistSyncDomains,
        DBG_4_0_addSignalNamesToSync,
        DBG_4_1_finalHwschedule,
        DBG_4_2_netlistChannelMergeTrace,
        DBG_4_3_handshakeSCCs,
        DBG_4_3_netlistBeforSyncLoweingDot,
        DBG_4_3_netlistBeforSyncLoweingTxt,
        DBG_4_4_finalNetlist,
        DBG_4_4_finalNetlistTxt,
        DBG_4_4_arch,
        DBG_4_5_sync,
    }

    def __init__(self, debugDir:Optional[Union[str, Path]], filter_: Optional[Set[DebugId]]):
        """
        :attention: if debugDir is None no debug option will be enabled
        """
        self.dir = None if debugDir is None else Path(debugDir)
        self.filter = filter_
        self.firstRun = True
        self.runConsistencyChecks = True

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
