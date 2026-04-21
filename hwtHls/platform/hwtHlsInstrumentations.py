from copy import deepcopy
from datetime import time
from io import StringIO
from pathlib import Path
import sys
from time import perf_counter_ns
from typing import Optional, Union, TypeVar, Callable

from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.node import NODE_ITERATION_TYPE
from hwtHls.netlist.translation.dumpNodesDot import HwtHlsNetlistToGraphviz
from hwtHls.platform.debugBundle import HlsDebugBundle, DebugId
from hwtHls.platform.fileUtils import outputFileGetter
from hwtHls.ssa.analysisCache import AnalysisCache, PassT, AnalysisPass


class DebugPassManagerLogger():

    def __init__(self, out: StringIO):
        self.out = out

    @staticmethod
    def getPassManagerDebugLogFile(platform: "DefaultHlsPlatform") -> Optional[StringIO]:
        for llvmArg in platform._llvmCliArgs:
            if llvmArg[0] == "debug-pass-manager":
                return sys.stderr
        return None

    def beforeAnalysis(self, analysisId, analysis, ir):
        self.out.write(f"Running analysis: {analysisId.__name__} on {ir}\n")

    def beforePass(self, passId, pass_, ir):
        self.out.write(f"Running pass: {passId.__name__} on {ir}\n")

    def onInvalidateAnalysis(self, analysisId, analysis, ir):
        self.out.write(f"Invalidating analysis: {analysisId.__name__} on {ir}\n")


class TimePassesHandler():
    """
    Based on llvm::TimePassesHandler
    """

    class Timer():

        def __init__(self, label):
            self.label = label
            self.totalTime = 0  # [ns]
            self.startTime: Optional[int] = None

        def start(self):
            assert self.startTime is None, self
            self.startTime = perf_counter_ns()

        def stop(self):
            assert self.startTime is not None, self
            self.totalTime += perf_counter_ns() - self.startTime
            self.startTime = None

        def isRunning(self):
            return self.startTime is not None

        def __repr__(self):
            return f"<Timer 0x{id(self):x} for {self.label}>"

    def __init__(self):
        self.timingData: dict[Union[AnalysisPass, PassT], time] = {}
        self.activeTimerStack: list[Timer] = []

    def stopLastTimer(self):
        if self.activeTimerStack:
            lastTimer = self.activeTimerStack[-1]
            if lastTimer.isRunning():
                lastTimer.stop()

    def startLastTimer(self):
        if self.activeTimerStack:
            lastTimer = self.activeTimerStack[-1]
            assert not lastTimer.isRunning()
            lastTimer.start()

    def beforeAnalysis(self, analysisId, analysis, ir):
        self.stopLastTimer()
        timer = self.timingData.get(analysisId, None)
        if timer is None:
            timer = self.timingData[analysisId] = self.Timer(analysisId)
        self.activeTimerStack.append(timer)
        timer.start()

    def afterAnalysis(self, analysisId, analysis, ir):
        timer = self.activeTimerStack.pop()
        assert timer.label == analysisId, (timer.label, analysisId)
        timer.stop()
        self.startLastTimer()

    def beforePass(self, passId, pass_, ir):
        self.stopLastTimer()
        timer = self.timingData.get(passId, None)
        if timer is None:
            timer = self.timingData[passId] = self.Timer(passId)
        self.activeTimerStack.append(timer)
        timer.start()

    def afterPass(self, passId, pass_, ir):
        timer = self.activeTimerStack.pop()
        assert timer.label == passId, (timer.label, passId)
        timer.stop()
        self.startLastTimer()

    def dump(self, out: StringIO):
        w = out.write
        for k, t in sorted(self.timingData.items(), key=lambda kv:-kv[1].totalTime):
            t: TimePassesHandler.Timer
            w(f"{t.totalTime / 1e9:03.3f}    {k.__name__:s}\n")  # ns -> s


class DumpHlsNetlistDotHandler():

    def __init__(self, dbgDir: Path, dumpBefore=False, dumpAfter=False, dumpChanged=False):
        self.dbgCntr = 0
        self.dbgDir = dbgDir
        self.dumpAfter = dumpAfter
        self.dumpChanged = dumpChanged
        self.dumpBefore = dumpBefore
        self.origNetlistStack: list[HlsNetlistCtx] = []

    def dump(self, dbgId: DebugId, pass_, netlist: HlsNetlistCtx):
        d = self.dbgDir / netlist.dbgSubdir
        d.mkdir(parents=True, exist_ok=True)
        filename = d / dbgId[1].format(self.dbgCntr, pass_.__class__.__name__)
        with open(filename, "w") as out:
            nodes = netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.PREORDER)
            toGraphviz = HwtHlsNetlistToGraphviz(netlist.label, nodes, True, False, True)
            toGraphviz.construct()
            out.write(toGraphviz.dumps())

    def beforePass(self, passId, pass_, ir):
        if not isinstance(ir, HlsNetlistCtx):
            return

        if self.dumpBefore:
            self.dump(HlsDebugBundle.DBG_3_0_netlistDumpBefore, pass_, ir)

        if self.dumpChanged:
            self.origNetlistStack.append(deepcopy(ir))

    def afterPass(self, passId, pass_, ir):
        if not isinstance(ir, HlsNetlistCtx):
            return

        if self.dumpAfter:
            self.dump(HlsDebugBundle.DBG_3_0_netlistDumpAfter, pass_, ir)

        if self.dumpChanged:
            origIr = self.origNetlistStack.pop()
            raise NotImplementedError(passId)

        self.dbgCntr += 1


class HwtHlsInstrumentations():

    def __init__(self, platform: "DefaultHlsPlatform", ac: AnalysisCache):
        self.platform = platform
        self.timePassHandler: Optional[TimePassesHandler] = None
        self.dumpHlsNetlistDotHandler: Optional[DumpHlsNetlistDotHandler] = None
        self.addedCallbacks: set[Callable[[type, Union[AnalysisPass, PassT], TypeVar("irT")]]] = set()
        self.ac = ac
        self.installInstrumentationCallbacks()

    def installInstrumentationCallbacks(self):
        ac: AnalysisCache = self.ac
        dbg = self.platform._debug
        if dbg.isActivated(HlsDebugBundle.DBG_5_0_hwtHlsStats):
            # assert self.timePassLogger is None, "Before new callbacks the previous results should have been stored"
            tph = self.timePassHandler
            if tph is None:
                tph = self.timePassHandler = TimePassesHandler()
            ac.callbacksBeforeAnalysis.append(tph.beforeAnalysis)
            ac.callbacksAfterAnalysis = [tph.afterAnalysis, ] + ac.callbacksAfterAnalysis
            ac.callbacksBeforePass.append(tph.beforePass)
            ac.callbacksAfterPass = [tph.afterPass, ] + ac.callbacksAfterPass
            self.addedCallbacks.update([tph.beforeAnalysis, tph.afterAnalysis,
                                        tph.beforePass, tph.afterPass])

        dumpAfter = dbg.isActivated(HlsDebugBundle.DBG_3_0_netlistDumpAfter)
        dumpBefore = dbg.isActivated(HlsDebugBundle.DBG_3_0_netlistDumpBefore)
        dumpChanged = dbg.isActivated(HlsDebugBundle.DBG_3_0_netlistDumpChanged)
        if dumpAfter or dumpBefore or dumpChanged:
            d = self.dumpHlsNetlistDotHandler
            if d is None:
                d = self.dumpHlsNetlistDotHandler = DumpHlsNetlistDotHandler(dbg.dir, dumpBefore=dumpBefore, dumpAfter=dumpAfter, dumpChanged=dumpChanged)
            ac.callbacksBeforePass.append(d.beforePass)
            ac.callbacksAfterPass = [d.afterPass, ] + ac.callbacksAfterPass
            self.addedCallbacks.update([d.beforePass, d.afterPass])

        debugPMlog = DebugPassManagerLogger.getPassManagerDebugLogFile(self.platform)
        # log = toSsa._dbgLogPassExec
        if debugPMlog is not None:
            dpm = DebugPassManagerLogger(debugPMlog)
            ac.callbacksBeforeAnalysis.append(dpm.beforeAnalysis)
            ac.callbacksInvalidateAnalysis = [dpm.onInvalidateAnalysis, ] + ac.callbacksInvalidateAnalysis
            ac.callbacksBeforePass.append(dpm.beforePass)
            self.addedCallbacks.update([dpm.beforeAnalysis, dpm.onInvalidateAnalysis,
                                        dpm.beforePass])

    def finalizeInstrumentationCallbacks(self):
        if self.timePassHandler is not None:
            outStreamGetter = outputFileGetter(self.platform._debug.dir, HlsDebugBundle.DBG_5_0_hwtHlsStats[1])
            outF, _ = outStreamGetter(self.ac.dbgSubdir)
            with outF as _outF:
                self.timePassHandler.dump(_outF)

            self.timePassHandler = None

        addedCbs = self.addedCallbacks
        if self.addedCallbacks:
            ac: AnalysisCache = self.ac
            ac.callbacksBeforeAnalysis[:] = (cb for cb in tuple(ac.callbacksBeforeAnalysis) if cb not in addedCbs)
            ac.callbacksAfterAnalysis[:] = (cb for cb in tuple(ac.callbacksAfterAnalysis) if cb not in addedCbs)
            ac.callbacksBeforePass[:] = (cb for cb in tuple(ac.callbacksBeforePass) if cb not in addedCbs)
            ac.callbacksAfterPass[:] = (cb for cb in tuple(ac.callbacksAfterPass) if cb not in addedCbs)
            addedCbs.clear()

