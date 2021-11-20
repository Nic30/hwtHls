from typing import Set

from hwt.code import And
from hwt.hdl.value import HValue
from hwtHls.hlsStreamProc.exprBuilder import SsaExprBuilder
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.phi import SsaPhi
from hwtHls.ssa.translation.fromAst.astToSsa import AstToSsa


class SsaPassExpandControlSelfloops():
    """
    Effectively transforms

    .. code-block:: Python


        something_other_pre()
        while True:
            x = 10
            while x != 0:
                x -= 1
            something_other_post()

    to

    .. code-block:: Python

        something_other_pre()
        x = 10
        while True:
            if x == 0:
                something_other_post()
                x = 10
            x -= 1


    and

    .. code-block:: Python

        something_other_pre()
        x = 10
        while x != 0:
            x -= 1
        something_other_post()

    to

    .. code-block:: Python

        something_other_pre()
        x = 10
        while True:
            if x == 0:
                break
            x -= 1
        something_other_post()


    and

    .. code-block:: Python

        something_other_pre()
        while True:
            x = read()
            while x != 0:
                x -= 1
            something_other_post()

    to

    .. code-block:: Python

        something_other_pre()
        x = read()
        while True:
            if x == 0:
                something_other_post()
                x = read()
                continue
            x -= 1

    """

    def apply(self, to_ssa: AstToSsa):
        seen: SsaBasicBlock = set()
        to_ssa.start = self._visit_SsaBasicBlock(to_ssa.start, seen)

    def _visit_SsaBasicBlock(self, block: SsaBasicBlock, seen: Set[SsaBasicBlock]):
        seen.add(block)

        # if contains selfloop and the body of loop has multiple blocks
        if block in block.predecessors and len(block.predecessors) > 1:

            # we must define all variables before first use
            # this means that if there is some variable comming from a self loop
            # se need to preset it

            # will contain all except things related to original selfloop (uses tmp var. instead orig ind. var.)
            cond_block = block
            #  cond_block               <--
            #    | |-> post_cond_block    |
            #  merge_cond_block        ----
            #    |
            #  body            # original successor of cond block

            # will contain selfloop related instructions (uses tmp var. instead orig ind. var.)
            post_cond_block = SsaBasicBlock(block.ctx, f"{cond_block.label}_p")
            # will will merge tmp variables from cond/cond_m into original ind. var.
            merge_cond_block = SsaBasicBlock(block.ctx, f"{cond_block.label}_m")

            # * induction variables are Phis which do change value in selfloop transition
            for phi in cond_block.phis:
                phi: SsaPhi
                is_ind_var = False
                for (v, src_block) in phi.operands:
                    if src_block is block:
                        is_ind_var = True
                        break

                if is_ind_var:
                    # * move this phi to merge_cond_block
                    merge_cond_block.phis.append(phi)
                    phi.block = merge_cond_block

                    # * crate a new phi in cond_block that will handle selection from predecessors except cond_block itself
                    c_block_phi_ops = []
                    # * create a variable in post_cond_block which will represent the value which should be optained in the case of selfloop
                    p_block_val = None
                    for v, src_block in phi.operands:
                        if src_block is cond_block:
                            p_block_val = v
                            if not isinstance(v, HValue):
                                raise NotImplementedError("Need to check if value can cause 0 iterations", phi, v)
                        else:
                            if isinstance(v, SsaPhi):
                                v: SsaPhi
                                v.users.remove(phi)
                            c_block_phi_ops.append((v, src_block))

                    if len(c_block_phi_ops) > 1:
                        c_block_phi = SsaPhi(block.ctx, phi._dtype, origin=phi.origin)
                        cond_block.appendPhi(c_block_phi)
                        c_block_phi.appendOperand(v, src_block)
                    else:
                        # has just one predecessor and phi is not required, we use value directly
                        assert c_block_phi_ops
                        c_block_phi = c_block_phi_ops[0][0]

                    assert p_block_val is not None, phi

                    # * update parameters so it select between variant from cond_block and post_cond_block
                    phi.operands = ()
                    phi.appendOperand(c_block_phi, cond_block)
                    phi.appendOperand(p_block_val, post_cond_block)

                    # [todo] update all instruction in this block to use c_block_phi instead
                    for instr in cond_block.body:
                        instr.replaceInput(phi, c_block_phi)

            # remove moved phis from cond_block
            cond_block.phis = [
                phi for phi in cond_block.phis
                if phi not in merge_cond_block.phis
            ]
            # transfer original successors to a merge_cond_block
            self_loop_cond = None
            for i, (c, suc_block) in enumerate(cond_block.successors.targets):
                suc_block: SsaBasicBlock
                suc_block.predecessors.remove(cond_block)
                if suc_block is cond_block:
                    # And(~c for prev_conds)
                    eb = SsaExprBuilder(self._createHlsTmpVariable, cond_block)
                    conds = [~eb.var(v) for v, _ in cond_block.successors.targets[:i]]
                    self_loop_cond = And(*conds).var
                    continue
                else:
                    # :note: predecessors auto updated
                    c = None  # [TODO] must check if is always satisfied after loop restart
                    merge_cond_block.successors.addTarget(c, suc_block)

            assert cond_block.successors.targets[-1][1] is cond_block
            cond_block.successors.targets.clear()

            assert self_loop_cond is not None, ("Condition which causes self loop was not found", cond_block.label)
            # * because there can be cases where the body block shoul not be entered if post_cond_block did not set
            #   the value required by original cond_block

            cond_block.successors.addTarget(self_loop_cond, post_cond_block)
            cond_block.successors.addTarget(None, merge_cond_block)

            # update successors of cond_block and merge_cond_block (and pred. of its succ.)
            # to match what is witten in phis
            post_cond_block.successors.addTarget(None, merge_cond_block)
            block = cond_block

        for suc in block.successors.iter_blocks():
            if suc not in seen:
                self._visit_SsaBasicBlock(suc, seen)

        return block

