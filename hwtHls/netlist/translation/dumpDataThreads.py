from io import StringIO
from typing import List, Set, Dict

from hwtHls.llvm.llvmIr import MachineBasicBlock, MachineFunction
from hwtHls.netlist.analysis.dataThreadsForBlocks import HlsNetlistAnalysisPassDataThreadsForBlocks
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from hwtHls.platform.fileUtils import OutputStreamGetter


class HlsNetlistPassDumpDataThreads(HlsNetlistPass):

    def __init__(self, outStreamGetter: OutputStreamGetter):
        self.outStreamGetter = outStreamGetter

    def _printThreads(self, mf: MachineFunction, threads: HlsNetlistAnalysisPassDataThreadsForBlocks, out: StringIO):
        # :note: we first collect the nodes to have them always in deterministic order
        threadList: List[Set[HlsNetNode]] = []
        seenThreadIds: Set[int] = set()
        blocksForThreadId: Dict[int, List[MachineBasicBlock]] = {}
        for mb in mf:
            mb: MachineBasicBlock
            for t in threads.threadsPerBlock[mb]:
                t: Set[HlsNetNode]
                tId = id(t)
                if tId not in seenThreadIds:
                    seenThreadIds.add(tId)
                    threadList.append(t)
                blocks = blocksForThreadId.get(tId, None)
                if blocks is None:
                    blocks = blocksForThreadId[tId] = []
                blocks.append(mb)

        for tI, t in enumerate(threadList):
            out.write(f"########### Thread {tI:d} ###########\n"
                      "blocks:\n")
            for mb in blocksForThreadId[id(t)]:
                mb: MachineBasicBlock
                out.write(f"    bb.{mb.getNumber():d}_{mb.getName().str():s}\n")
            out.write("nodes:\n")
            for n in sorted(t, key=lambda n: n._id):
                n: HlsNetNode
                out.write(f"    {n}\n")
            out.write("\n")

    def apply(self, hls: "HlsScope", netlist: HlsNetlistCtx):
        from hwtHls.ssa.translation.llvmMirToNetlist.mirToNetlist import HlsNetlistAnalysisPassMirToNetlist
        threads = netlist.getAnalysis(HlsNetlistAnalysisPassDataThreadsForBlocks)
        mf: MachineFunction = netlist.getAnalysis(HlsNetlistAnalysisPassMirToNetlist).mf
        out, doClose = self.outStreamGetter(netlist.label)
        try:
            self._printThreads(mf, threads, out)
        finally:
            if doClose:
                out.close()

