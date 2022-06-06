from typing import Dict, Set, Tuple, List, Union, Optional

from hwt.hdl.value import HValue
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.transformation.utils.blockAnalysis import collect_all_blocks
from hwtHls.ssa.value import SsaValue
from hwtHls.ssa.phi import SsaPhi


class SsaPassThreadMining():
    """
    Walk the instruction in the block and find the independent code thread

    :ivar threads: a dictionary which is mapping an instruction to a thread
    :ivar toCheckLater: list of tuples (src, dst) which could not be resolved because dependency was not yet resolved
    """

    def __init__(self, out_of_pipeline_edges:Set[Tuple[SsaBasicBlock, SsaBasicBlock]]):
        self.threadsPerInstr: Dict[SsaValue, Set[SsaValue]] = {}
        self.threadsPerBlock: Dict[SsaBasicBlock, List[Set[SsaValue]]] = {}
        self.out_of_pipeline_edges = out_of_pipeline_edges
        self.toCheckLater: List[Tuple[SsaValue, SsaValue]] = []

    def mergeThreads(self, t0: Set[SsaValue], t1: Set[SsaValue]):
        "Merge t0 into t1 and replace it in self.threads"
        threads = self.threadsPerInstr
        for i1 in t1:
            threads[i1] = t0
        t0.update(t1)

    def mergeInNextOperand(self,
                           parent: SsaValue, op: Union[SsaValue, HValue],
                           otherMembersOfThread: Optional[Set[SsaValue]]) -> Optional[Set[SsaValue]]:
        if isinstance(op, HValue):
            return otherMembersOfThread

        _otherMembersOfThread = self.threadsPerInstr.get(op, None)
        if _otherMembersOfThread is None:
            self.toCheckLater.append((op, parent))
        elif otherMembersOfThread is None:
            otherMembersOfThread = _otherMembersOfThread
        else:
            self.mergeThreads(otherMembersOfThread, _otherMembersOfThread)
        return otherMembersOfThread

    def apply_SsaBasicBlock(self, block: SsaBasicBlock):
        threads = self.threadsPerInstr
        for phi in block.phis:
            phi: SsaPhi
            otherMembersOfThread = None
            for (c, b) in phi.operands:

                if (b, block) not in self.out_of_pipeline_edges:
                    otherMembersOfThread = self.mergeInNextOperand(phi, c, otherMembersOfThread)

            if otherMembersOfThread is None:
                otherMembersOfThread = set()

            otherMembersOfThread.add(phi)
            threads[phi] = otherMembersOfThread

        for ins in block.body:

            otherMembersOfThread = None
            for o in ins.operands:
                otherMembersOfThread = self.mergeInNextOperand(ins, o, otherMembersOfThread)

            if otherMembersOfThread is None:
                otherMembersOfThread = set()

            otherMembersOfThread.add(ins)
            threads[ins] = otherMembersOfThread

    def finalize(self):
        for src, dst in self.toCheckLater:
            self.mergeThreads(self.threadsPerInstr[src], self.threadsPerInstr[dst])
        self.toCheckLater.clear()

    def apply(self, start: SsaBasicBlock):
        blocks = list(collect_all_blocks(start, set()))
        for b in blocks:
            self.apply_SsaBasicBlock(b)

        self.finalize()
        seen: Set[int] = set()
        for thread in self.threadsPerInstr.values():
            if id(thread) in seen:
                continue
            else:
                seen.add(id(thread))

            for ins in thread:
                ins: SsaValue
                blockThreads: List[Set[SsaValue]] = self.threadsPerBlock.get(ins.block, None)
                if blockThreads is None:
                    blockThreads = []
                    self.threadsPerBlock[ins.block] = blockThreads
                elif thread in blockThreads:
                    continue

                blockThreads.append(thread)
        # there maybe blocks without any instruction
        for b in blocks:
            if not b.phis and not b.body:
                self.threadsPerBlock[b] = []
