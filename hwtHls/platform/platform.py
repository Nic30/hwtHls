from pathlib import Path
from typing import Optional, Union

from hwt.synthesizer.dummyPlatform import DummyPlatform
from hwtHls.netlist.allocator.allocator import HlsAllocator
from hwtHls.netlist.analysis.consystencyCheck import HlsNetlistPassConsystencyCheck
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.scheduler.scheduler import HlsScheduler
from hwtHls.netlist.transformation.aggregateBitwiseOpsPass import HlsNetlistPassAggregateBitwiseOps
from hwtHls.netlist.transformation.dce import HlsNetlistPassDCE
from hwtHls.netlist.transformation.mergeExplicitSync import HlsNetlistPassMergeExplicitSync
from hwtHls.netlist.translation.dumpStreamNodes import RtlNetlistPassDumpStreamNodes
from hwtHls.netlist.translation.toTimeline import HlsNetlistPassShowTimeline
from hwtHls.netlist.translation.toTimelineArchLevel import HlsNetlistPassShowTimelineArchLevel
from hwtHls.platform.fileUtils import outputFileGetter
from hwtHls.ssa.analysis.consystencyCheck import SsaPassConsystencyCheck
from hwtHls.ssa.analysis.dumpMIR import SsaPassDumpMIR
from hwtHls.ssa.transformation.axiStreamReadLowering.axiStreamReadLoweringPass import SsaPassAxiStreamReadLowering
from hwtHls.ssa.transformation.extractPartDrivers.extractPartDriversPass import SsaPassExtractPartDrivers
from hwtHls.ssa.translation.fromAst.astToSsa import AstToSsa
from hwtHls.ssa.translation.llvmToMirAndMirToHlsNetlist.llvmToMirAndMirToHlsNetlist import SsaPassLlvmToMirAndMirToNetlist
from hwtHls.ssa.translation.toGraphwiz import SsaPassDumpToDot
from hwtHls.ssa.translation.toLl import SsaPassDumpToLl
from hwtHls.ssa.translation.toLlvm import SsaPassToLlvm


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

    def runSsaPasses(self, hls: "HlsStreamProc", toSsa: AstToSsa):
        debugDir = self._debugDir
        if not debugDir.exists():
            debugDir.mkdir()
        if debugDir:
            SsaPassDumpToDot(outputFileGetter(debugDir, ".0.dot"), extractPipeline=False).apply(hls, toSsa)
        
        SsaPassConsystencyCheck().apply(hls, toSsa)
        SsaPassAxiStreamReadLowering().apply(hls, toSsa)
        if debugDir:
            SsaPassDumpToDot(outputFileGetter(debugDir, ".1.dot"), extractPipeline=False).apply(hls, toSsa)
        SsaPassExtractPartDrivers().apply(hls, toSsa)
        if debugDir:
            SsaPassDumpToDot(outputFileGetter(debugDir, ".2.dot"), extractPipeline=False).apply(hls, toSsa)

        SsaPassToLlvm().apply(hls, toSsa)
        if debugDir:
            SsaPassDumpToLl(outputFileGetter(debugDir, ".3.ll")).apply(hls, toSsa)
            SsaPassDumpMIR(outputFileGetter(debugDir, ".5.ll")).apply(hls, toSsa)

        # SsaPassConsystencyCheck().apply(hls, toSsa)
   
    def runSsaToNetlist(self, hls: "HlsStreamProc", toSsa: AstToSsa) -> HlsNetlistCtx:
        return SsaPassLlvmToMirAndMirToNetlist().apply(hls, toSsa)

    def runHlsNetlistPasses(self, hls: "HlsStreamProc", netlist: HlsNetlistCtx):
        debugDir = self._debugDir
        if debugDir:
            HlsNetlistPassConsystencyCheck().apply(hls, netlist)
            
        HlsNetlistPassDCE().apply(hls, netlist)
        # if debugDir:
        #   HlsNetlistPassDumpToDot(debugDir / "top_p0.dot").apply(hls, pipeline)
           
        HlsNetlistPassMergeExplicitSync().apply(hls, netlist)
        HlsNetlistPassAggregateBitwiseOps().apply(hls, netlist)
        if debugDir:
            # HlsNetlistPassConsystencyCheck().apply(hls, pipeline)
            # HlsNetlistPassDumpToDot(debugDir / "top_p1.dot").apply(hls, pipeline)
            HlsNetlistPassShowTimeline(outputFileGetter(debugDir, ".8.schedule.html"),
                                           expandCompositeNodes=self._debugExpandCompositeNodes).apply(hls, netlist)

    def runRtlNetlistPasses(self, hls: "HlsStreamProc", netlist: HlsNetlistCtx):
        debugDir = self._debugDir
        if debugDir:
            RtlNetlistPassDumpStreamNodes(outputFileGetter(debugDir, ".9.sync.txt")).apply(hls, netlist)
            HlsNetlistPassShowTimelineArchLevel(outputFileGetter(debugDir, ".10.archschedule.html")).apply(hls, netlist)

