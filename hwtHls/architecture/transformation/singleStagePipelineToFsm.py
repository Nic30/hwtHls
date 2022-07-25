from hwtHls.architecture.allocator import HlsAllocator
from hwtHls.architecture.archElementFsm import ArchElementFsm
from hwtHls.architecture.archElementPipeline import ArchElementPipeline
from hwtHls.architecture.transformation.rtlArchPass import RtlArchPass
from hwtHls.netlist.analysis.fsm import IoFsm
from hwtHls.netlist.scheduler.clk_math import start_clk


class RtlArchPassSingleStagePipelineToFsm(RtlArchPass):

    def apply(self, hls: "HlsScope", allocator: HlsAllocator):
        newArchElements = []
        netlist = allocator.netlist
        namePrefix = allocator.namePrefix
        onlySingleElem = len(allocator._archElements) == 1

        fsmIdOffset = 0
        for e in allocator._archElements:
            if isinstance(e, ArchElementFsm):
                fsmIdOffset += 1
        clkPeriod = netlist.normalizedClkPeriod
        for e in allocator._archElements:
            if isinstance(e, ArchElementPipeline):
                e: ArchElementPipeline
                if len(e.stages) == 1:
                    fsm = IoFsm(None)
                    n0 = e.allNodes[0]
                    fsm.stateClkI = {0: start_clk(min(n0.scheduledIn) if n0.scheduledIn else min(n0.scheduledOut), clkPeriod)}
                    fsm.states= [e.allNodes, ]
                    fsm.transitionTable = {0: {0: True}}
                    e = ArchElementFsm(netlist, namePrefix if onlySingleElem else f"{namePrefix:s}fsm{fsmIdOffset:d}_", fsm)
                    fsmIdOffset += 1

            newArchElements.append(e)
        allocator._archElements = newArchElements
