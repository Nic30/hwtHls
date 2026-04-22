from hwt.pyUtils.typingFuture import override
from hwtHls.netlist.analysis.hlsNetlistAnalysisPass import HlsNetlistAnalysisPass
from hwtHls.platform.fileUtils import outputFileGetter


class HlsNetlistAnalysisPassRunScheduler(HlsNetlistAnalysisPass):

    @override
    def runOnHlsNetlistImpl(self, netlist:"HlsNetlistCtx"):
        from hwtHls.platform.debugBundle import HlsDebugBundle
        DBG = netlist.platform._debug.isActivated
        scheduler: "HlsScheduler" = netlist.scheduler
        if DBG(HlsDebugBundle.DBG_4_0_hwscheduleTrace):
            tracerFile, tracerFileDoClose = outputFileGetter(netlist.platform._debug.dir, HlsDebugBundle.DBG_4_0_hwscheduleTrace[1])(netlist.dbgSubdir)
            scheduler._dbgTraceFile = tracerFile
        else:
            tracerFileDoClose = False

        scheduler._dbgDumpAfterPhases = DBG(HlsDebugBundle.DBG_4_0_hwscheduleDumpAfterPhases)
        scheduler._dbgCheckCycles = DBG(HlsDebugBundle.DBG_4_0_hwscheduleCheckCycles)
        scheduler._dbgPrintPhaseBoundaries = DBG(HlsDebugBundle.DBG_4_0_hwschedulePrintPhaseBoundaries)

        try:
            netlist.scheduler.schedule()
            netlist.flagIsScheduled = True
        finally:
            if tracerFileDoClose:
                tracerFile.close()

    @override
    def invalidate(self, netlist: "HlsNetlistCtx"):
        netlist.flagIsScheduled = False
