from typing import Set

from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.translation.fromAst.astToSsa import AstToSsa


class SsaPassRemoveTrivialBlocks():
    """
    Trivial block is the one which has 0 or 1 successor and has no body.

    Its phi is safe to merge into phis of successor and all edges are safe to rerouted to a successor and this block can be removed.
    """

    def _visit(self, block: SsaBasicBlock, seen: Set[SsaBasicBlock]):
        """
        :ivar block: basic block which is potentially removed
        """
        seen.add(block)
        targets = block.successors.targets
        blockHasSingleSuccessor = (len(targets) == 1 and targets[0][0] is None)
        blockSuccessorOfSelf = targets[0][1] is block

        # check the case were we can not remove this block because the phis of new_block (block successor)
        # need unique blocks as inputs
        # block_pred -> block (to removove) -> new_block -> new_block_suc
        # we need to check that new_block does not have block_pred in phis (as we will need to copy them there)
        phiCollisions = False
        if blockHasSingleSuccessor:
            new_block: SsaBasicBlock = targets[0][1]
            for phi in new_block.phis:
                for _, b in phi.operands:
                    if b in block.predecessors:
                        phiCollisions = True
                        break

        if blockHasSingleSuccessor and not blockSuccessorOfSelf and not block.body and not phiCollisions:
            # replace block with its only successor
            new_block.origins.extend(block.origins)
            new_block.predecessors.remove(block)
            # copy content of self into successor
            purely_new_predecessors = []
            for pred in block.predecessors:
                pred: SsaBasicBlock
                pred_targets = pred.successors.targets
                for i, (c, suc_block) in enumerate(pred_targets):
                    if suc_block is block:
                        pred_targets[i] = (c, new_block)
                if pred is block:
                    pred = new_block
                new_block.predecessors.append(pred)
                purely_new_predecessors.append(pred)

            for phi in new_block.phis:
                assert phi.block is new_block
                phi.replacePredecessorBlockByMany(block, purely_new_predecessors)
            new_block.successors.replaceTargetBlock(block, new_block)

            if block is self.start:
                self.start = new_block

            return self._visit(new_block, seen)
        else:
            # copy because successor may change due removing
            successors = tuple(block.successors.iter_blocks())
            for s in successors:
                if s not in seen:
                    self._visit(s, seen)
            return block

    def visit(self, block: SsaBasicBlock):
        self.start = block
        seen = set()
        return self._visit(block, seen)

    def apply(self, to_ssa: AstToSsa):
        to_ssa.start = self.visit(to_ssa.start)
