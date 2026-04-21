from pathlib import Path
from typing import Tuple, Type, Optional, Union, Set

from hdlConvertorAst.translate.common.name_scope import NameScope
from hwtHls.architecture.transformation.addRtlSigNames import HlsAndRtlNetlistPassAddSignalNamesToSync, \
    HlsAndRtlNetlistPassAddSignalNamesToData
from hwtHls.architecture.transformation.archElementsToSubunits import RtlArchPassTransplantArchElementsToSubunits
from hwtHls.architecture.transformation.syncLowering import HlsArchPassSyncLowering
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
from hwtHls.ssa.translation.dumpIR import SsaPassDumpIR
from hwtHls.ssa.translation.dumpMIR import SsaPassDumpMIR
from hwtHls.ssa.translation.dumpMirCfg import SsaPassDumpMirCfg

DebugId = Tuple[Type, Optional[str]]


class LLVM_CLI_COMMON_OPTS:
    # :note: for common options see StandardInstrumentations.cpp in LLVM
    # common pass names :note: you can use DEBUG_PASS_MANAGER to print names
    #  the name is what Pass.name() returns, :see: PassInfoMixin::name
    #     "hwtfpga-pretonetlist-combiner"
    #     "vreg-if-converter"
    #     "loop-simplify"
    #     "simplifycfg"
    #     "hwtHls::HwtHlsSimplifyCFGPass"
    # :note: LLVM MIR GISel combiners have options to disable/allow rules like
    #   "hwtfpgapreregallocgicombiner-disable-rule"/"hwtfpgapreregallocgicombiner-only-enable-rule"
    DEBUG_PASS_MANAGER = ("debug-pass-manager", 0, "", "")  # print used passes until machinemoduleinfo
    DEBUG_PASS_ARGUMENTS = ("debug-pass", 0, "", "Arguments")  # print used passes starting from machinemoduleinfo
    DEBUG_PASS_STRUCTURE = ("debug-pass", 0, "", "Structure")  # same as Arguments but pretty formated
    # see https://github.com/llvm/llvm-project/blob/main/llvm/lib/IR/PrintPasses.cpp
    PRINT_MODULE_SCOPE = ("print-module-scope", 0, "", "true")  # When printing IR for print-[before|after]{-all} always print a module IR
    PRINT_AFTER_ALL = ("print-after-all", 0, "", "true")
    PRINT_BEFORE_ALL = ("print-before-all", 0, "", "true")
    PRINT_CHANGED = ("print-changed", 0, "", "")
    PRINT_CHANGED_DOT_CFG = ("print-changed", 0, "", "dot-cfg")  # :attention: blocks without name will cause crash https://github.com/llvm/llvm-project/pull/148582

    STATS = ("stats", 0, "", "")  # print values of llvm statistics defined by STATISTIC(<id>, <string>)

    @classmethod
    def filterPrintFuncs(cls, functionNames: list[str]):
        """
        filter dumps to a specific functions
        :note: this work for print-* options, and it does not for example for debug-pass-manager
        """
        assert not isinstance(functionNames, str), functionNames
        return ("filter-print-funcs", 1, "", ",".join(functionNames))

    @classmethod
    def printBefore(cls, passName: str):
        """
        dump before each pass
        """
        return ("print-before", 0, "", passName)

    @classmethod
    def printAfter(cls, passName:str):
        """
        dump after each pass
        """
        return ("print-after", 0, "", passName)

    VERIFY_EACH = ("verify-each", 0, "", "")  # run verification after each pass

    @classmethod
    def passRemarksOutput(cls, filename:str="opt.yaml"):
        """
        Specifies remark file which contains info about optimization decisions
        """
        return ("pass-remarks-output", 0, "", filename)

    STATS_JSON = ("stats-json", 0, "", "true")  # specifies that stats/time output is in json format
    TIME_PASSES = ("time-passes", 0, "", "true")  # profile times of passes and analysis, for new PassManager use time-trace
    TIME_PHASES = ("time-phases", 0, "", "")  # [todo] rm
    # TIME_TRACE = ("time-trace", 0, "", "true") # log time of each pass (for new PassManager)

    @classmethod
    def infoOutputFile(cls, filename:str):  # specify filename for time-passes and alike
        return ("info-output-file", 0, "", filename)

    @classmethod
    def debugOnly(cls, passName: str):
        """
        Activates print of messages defined with LLVM_DEBUG and alike.

        :note: available only in llvm debug build
        """
        return ("debug-only", 0, "", passName)

    VREGIFCVT_TRACE = ("vregifcvt-trace", 0, "", "true")

    # ("view-dag-combine1-dags", 0, "", "true"),
    # ("view-legalize-types-dags", 0, "", "true"),
    # ("view-dag-combine-lt-dags", 0, "", "true"),
    # ("view-legalize-dags", 0, "", "true"),
    # ("view-dag-combine2-dags", 0, "", "true"),
    # ("view-isel-dags", 0, "", "true"),
    # ("view-sched-dags", 0, "", "true"),
    # ("view-sunit-dags", 0, "", "true"),
    # ("print-after-isel", 0, "", "true"),
    # ("print-lsr-output", 0, "", "true"),
    # ("debug-only", 0, "", "vreg-if-converter"), # :note: available only in llvm debug build
    # ("debug-only", 0, "", "loop-simplify"), # :note: available only in llvm debug build
    # ("debug", 0, "", "1"),


class NameScopeForDebugFiles(NameScope):

    @classmethod
    def _sanitize_name(self, suggested_name: str) -> str:
        return suggested_name


class HlsDebugBundle():
    """
    This class specifies common debug options which may be used on Platform.
    
    Debug outputs are stored in folder DEFAULT_DEBUG_DIR / parentHwModule._name + HlsScope._label (dbgRootDir)
    Each HlsThread in scope then generates its own subdir (for DBG_0_* to DBG_1_*)
    In this subdir the subdir for MIR function (thread) is generated (for DBG_2_*)
    Independent compilation phases for netlist (untill DBG_4_0_addSignalNamesToSync) aso store to this directory.
    DBG_4_* and following produce results in dbgRootDir as those steps are running on aggregated netlist from all threads.
    
    :note: if the number N in DBG_N_* is the same it means that these debug options are working with the same input
    
    :ivar nameScope: name scope for debug files to prevent name collisions if the module/thread of the same name
        is build multiple times in a single translation unit
    """
    DEFAULT_DEBUG_DIR = "tmp"

    DBG_0_0_hierachyPath = (None, "00.00.hierarchyPath.txt")  # dump path in hierarchy and HwParams of parents
    DBG_0_0_pyFrontedBytecodeTrace = (None, "00.00.bytecode.trace.txt")  # trace file for operations in during pybytecode translation
    DBG_0_0_pyFrontedBytecode = (None, "00.00.bytecode.{0}.txt")  # bytecode for every translated function
    DBG_0_0_pyFrontedBeginCfg = (None, "00.00.cfg.begin.{0}.dot")  # initial CFG after parsing of bytecode
    DBG_0_0_pyFrontedPreprocCfg = (None, "00.00.cfg.{0}.dot")  # step by step CFG during preprocessor evaluation
    DBG_0_1_pyFrontedFinalCfg = (None, "00.01.cfg.final.{0}.dot")  # final CFG after preprocessor execution
    # ssa
    # :note: you can use platform._llvmCliArgs to add LLVM debug options
    DBG_1_0_preLlvm = (SsaPassDumpIR, "01.02.preLlvm.ll")  # translated to LLVM IR
    # mir
    DBG_2_0_mir = (SsaPassDumpMIR, "02.00.mir.ll")  # translated and optimized to LLVM MIR by LLVM
    DBG_2_0_mirCfg = (SsaPassDumpMirCfg, "02.00.mirCfg.dot")  # Control Flow Graph of MIR
    DBG_2_1_netlistConstructionTrace = (None, "02.01.netlistConstructionTrace.txt")  # trace of netlist construction (typically from LLVM MIR)
    DBG_2_1_blockSync = (HlsNetlistAnalysisPassDumpBlockSync, "02.01.blockSync.dot")  # synchronization features of basic blocks
    DBG_2_1_submoduleBuildLogMir = (None, "02.01.submoduleBuildLogMir.txt")  # log which direct children submodules are build to resolve synchronization during MirToNetlist
    DBG_2_2_preSync = (HlsNetlistAnalysisPassDumpNodesDot, "02.02.preSync.dot")  # io of basic blocks before implementation of sync
    DBG_2_3_postRst = (HlsNetlistAnalysisPassDumpNodesDot, "02.03.postRst.dot")  # basic block io after implementation of reset value extraction
    DBG_2_4_postLoop = (HlsNetlistAnalysisPassDumpNodesDot, "02.04.postLoop.dot")  # basic block io after implementation of loops
    DBG_2_5_postSync = (HlsNetlistAnalysisPassDumpBlockSync, "02.05.postSync.dot")  # basic block io after implementation of complete control flow sync
    DBG_2_6_llvmStats = (None, "02.06.llvmStats.txt")  # specify the statistics and timer reports file for LLVM reports
    #                                                    (== you also need LLVM_CLI_COMMON_OPTS.TIME_PASSES or similar to produce any reports)
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
    DBG_3_3_netlistAggregated = (HlsNetlistAnalysisPassDumpNodesDot, "03.03.netlistAggregated.dot")  # dump netlist after selected nodes were aggregated to scheduling primitives
    DBG_3_4_submoduleBuildLogPreSchedule = (None, "03.03.submoduleBuildLogPreSchedule.txt")  # log which direct children submodules are build to resolve scheduling
    DBG_4_0_hwscheduleDumpAfterPhases = (None, "04.00.hwscheduleDumpAfterPhases")  # dump netlist after phases during HlsNetlistAnalysisPassRunScheduler
    DBG_4_0_hwscheduleCheckCycles = (None, "04.00.hwscheduleCheckCycles")  # check for cycles in HlsNetlist DAG in HlsNetlistAnalysisPassRunScheduler
    DBG_4_0_hwscheduleTrace = (None, "04.00.hwscheduleTrace.txt")  # trace scheduling process during HlsNetlistAnalysisPassRunScheduler
    DBG_4_0_hwschedulePrintPhaseBoundaries = (None, "04.00.hwschedulePrintPhaseBoundaries")  # print bondaries of the scheduling phases in HlsNetlistAnalysisPassRunScheduler
    DBG_4_0_hwscheduleErr = (HlsNetlistAnalysisPassDumpSchedulingJson, "04.00.err.hwschedule.json")  # try dump scheduling if scheduler failed
    DBG_4_0_hwschedule = (HlsNetlistAnalysisPassDumpSchedulingJson, "04.00.hwschedule.json")  # node scheduling after first scheduling attempt
    DBG_4_0_submoduleBuildLogPostSchedule = (None, "04.00.submoduleBuildLogPostSchedule.txt")  # log which direct children submodules are build
    # arch gen
    DBG_4_0_addSignalNamesToSync = (HlsAndRtlNetlistPassAddSignalNamesToSync, None)  # signal names are directly in output RTL
    DBG_4_0_addSignalNamesToData = (HlsAndRtlNetlistPassAddSignalNamesToData, None)  # signal names are directly in output RTL
    DBG_4_1_finalHwschedule = (HlsNetlistAnalysisPassDumpSchedulingJson, "04.01.final.hwschedule.json")  # node scheduling which will be used to generate circuit

    DBG_4_2_netlistChannelMergeTrace = (None, "04.02.netlistChannelMergeTrace.txt")  # trace of channel merging
    DBG_4_3_handshakeSCCs = (RtlArchAnalysisPassDumpHsSCCsDot, "04.03.hanshakeSCCs.dot")  # handshake SCCs for sync debugging
    DBG_4_3_netlistBeforSyncLoweingDot = (HlsNetlistAnalysisPassDumpNodesDot, "04.03.netlist.beforeSyncLowering.dot")  # scheduled simplified netlist
    DBG_4_3_netlistBeforSyncLoweingTxt = (HlsNetlistAnalysisPassDumpNodesTxt, "04.03.netlist.beforeSyncLowering.txt")  # same as DBG_4_3_netlistBeforSyncLoweingDot just in txt
    DBG_4_4_syncLoweringAbc = ((HlsArchPassSyncLowering, "abc"), None)
    DBG_4_4_syncLoweringNodes = ((HlsArchPassSyncLowering, "nodes"), None)

    DBG_4_4_finalNetlist = (HlsNetlistAnalysisPassDumpNodesDot, "04.04.final.netlist.dot")  # basic blocks dissolved to netlist
    DBG_4_4_finalNetlistTxt = (HlsNetlistAnalysisPassDumpNodesTxt, "04.04.final.netlist.txt")  # same as DBG_4_4_finalNetlist just in txt
    DBG_4_4_archBasic = (RtlArchAnalysisPassDumpArchDot, "04.04.archBasic.dot")  # graf of arch elements connections in generated architecture without supplementary logic and generated functional units
    DBG_4_4_archCoarse = (RtlArchAnalysisPassDumpArchDot, "04.04.archCoarse.dot")  # graf of arch elements connections in generated architecture without supplementary logic
    DBG_4_4_archDetail = (RtlArchAnalysisPassDumpArchDot, "04.04.archDetail.dot")  # graf of arch elements connections in generated architecture
    DBG_4_5_sync = (HlsAndRtlNetlistPassDumpStreamNodes, "04.05.sync.txt")  # control expressions of IO, FSMs and pipelines
    DBG_4_5_regFileHierarchy = (RtlArchPassTransplantArchElementsToSubunits, None)  # extract registers in pipeline stage or fsm to separate component
    DBG_5_0_hwtHlsStats = (None, "05.06.hwtHlsStats.txt")  # equivalent of DBG_2_6_llvmStats for HwtHls non-llvm passes

    ALL = None
    NONE = {}
    ALL_RELIABLE_FAST = {
        DBG_0_0_hierachyPath,
        DBG_0_0_pyFrontedBytecode,
        DBG_0_0_pyFrontedBytecodeTrace,
        DBG_0_0_pyFrontedBeginCfg,
        DBG_0_1_pyFrontedFinalCfg,
        DBG_1_0_preLlvm,
        DBG_2_0_mir,
        DBG_2_0_mirCfg,
        DBG_2_1_netlistConstructionTrace,
        DBG_2_1_blockSync,
        DBG_2_1_submoduleBuildLogMir,
        DBG_2_6_llvmStats,
        DBG_3_1_netlistSimplifiedErr,
        DBG_3_4_submoduleBuildLogPreSchedule,
        DBG_4_0_hwscheduleErr,
        DBG_4_0_submoduleBuildLogPostSchedule,
        DBG_4_2_netlistChannelMergeTrace,
        DBG_4_3_handshakeSCCs,
        DBG_4_4_archBasic,
        DBG_4_5_sync,
        DBG_5_0_hwtHlsStats,
    }
    # :note: ALL_RELIABLE refers to passes which do not require intense circuit analysis.
    #        Passes which do require intense circuit analysis often fails on a broken circuit.
    #        Reliable debug options do not contain expensive debug options and
    #        are meant for detection of the bugs. While the expensive debug options
    #        are used for deeper circuit analysis or circuit rewrites for improving readability.
    # :note: all without DBG_4_0_addSignalNamesToSync, DBG_24_regFileHierarchy because it changes optimization behavior
    ALL_RELIABLE = {
        DBG_0_0_hierachyPath,
        DBG_0_0_pyFrontedBytecode,
        DBG_0_0_pyFrontedBytecodeTrace,
        DBG_0_0_pyFrontedBeginCfg,
        DBG_0_1_pyFrontedFinalCfg,
        DBG_1_0_preLlvm,
        DBG_2_0_mir,
        DBG_2_0_mirCfg,
        DBG_2_1_netlistConstructionTrace,
        DBG_2_1_blockSync,
        DBG_2_1_submoduleBuildLogMir,
        DBG_2_2_preSync,
        DBG_2_3_postRst,
        DBG_2_4_postLoop,
        DBG_2_5_postSync,
        DBG_2_6_llvmStats,
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
        DBG_3_4_submoduleBuildLogPreSchedule,
        DBG_4_0_hwscheduleErr,
        DBG_4_0_hwschedule,
        DBG_4_0_submoduleBuildLogPostSchedule,
        DBG_4_1_finalHwschedule,
        DBG_4_2_netlistChannelMergeTrace,
        DBG_4_3_handshakeSCCs,
        DBG_4_3_netlistBeforSyncLoweingDot,
        DBG_4_3_netlistBeforSyncLoweingTxt,
        DBG_4_4_finalNetlist,
        DBG_4_4_finalNetlistTxt,
        DBG_4_4_archBasic,
        DBG_4_4_archCoarse,
        DBG_4_4_archDetail,
        DBG_4_5_sync,
        DBG_5_0_hwtHlsStats,
    }
    DEFAULT = NONE

    # bundles of debug features to debug problems in a specific phase of compilation
    DBG_FRONTEND = {
        DBG_0_0_pyFrontedBytecodeTrace,
        DBG_0_0_pyFrontedBytecode,
        DBG_0_0_pyFrontedBeginCfg,
        DBG_0_0_pyFrontedPreprocCfg,
        DBG_0_1_pyFrontedFinalCfg,
        DBG_1_0_preLlvm,
    }
    # bundle for debugging of translation of LLVM to HlsNetlist
    DBG_NETLIST_GEN = {
        DBG_2_0_mir,
        DBG_2_0_mirCfg,
        DBG_2_1_netlistConstructionTrace,
        DBG_2_1_submoduleBuildLogMir,
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
        DBG_4_0_hwscheduleDumpAfterPhases,
        DBG_4_0_hwscheduleCheckCycles,
        DBG_4_0_hwscheduleTrace,
        DBG_4_0_hwschedulePrintPhaseBoundaries,
        DBG_4_0_hwscheduleErr,
        DBG_4_0_hwschedule,
        DBG_4_0_addSignalNamesToSync,
        DBG_4_1_finalHwschedule,
    }
    # bundle for debugging on architectural level
    DBG_ARCH_SYNC = {
        DBG_0_0_hierachyPath,
        DBG_2_0_mir,
        DBG_2_1_submoduleBuildLogMir,
        DBG_3_2_netlistSyncDomains,
        DBG_3_4_submoduleBuildLogPreSchedule,
        DBG_4_0_submoduleBuildLogPostSchedule,
        DBG_4_0_addSignalNamesToSync,
        DBG_4_1_finalHwschedule,
        DBG_4_2_netlistChannelMergeTrace,
        DBG_4_3_handshakeSCCs,
        DBG_4_3_netlistBeforSyncLoweingDot,
        DBG_4_3_netlistBeforSyncLoweingTxt,
        DBG_4_4_syncLoweringNodes,
        DBG_4_4_syncLoweringAbc,
        DBG_4_4_finalNetlist,
        DBG_4_4_finalNetlistTxt,
        DBG_4_4_archBasic,
        DBG_4_4_archCoarse,
        DBG_4_4_archDetail,
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
        self.nameScope = NameScopeForDebugFiles(None, "", False)

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
