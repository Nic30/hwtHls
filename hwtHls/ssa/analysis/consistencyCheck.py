from typing import Set, Dict, Union

from hwt.hdl.operatorDefs import HOperatorDef
from hwt.hdl.const import HConst
from hwt.pyUtils.setList import SetList
from hwtHls.frontend.ast.statementsRead import HlsRead
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.instr import SsaInstr
from hwtHls.ssa.phi import SsaPhi
from hwtHls.ssa.transformation.ssaPass import SsaPass
from hwtHls.ssa.value import SsaValue
from hwt.pyUtils.typingFuture import override


_ValOrVal = (HConst, SsaValue)


class SsaPassConsistencyCheck(SsaPass):

    def visit_collect(self, bb: SsaBasicBlock, blocks: SetList[SsaBasicBlock],
                      phis: SetList[SsaPhi],
                      variables: Dict[SsaValue, SsaBasicBlock]):
        blocks.append(bb)
        for phi in bb.phis:
            phi: SsaPhi
            assert phi not in phis, ("PHI has to be defined only once", phi, bb)
            assert phi.block is bb, ("PHI has parent block correct", phi, phi.block, bb)
            phis.append(phi)
            assert phi not in variables, ("Each PHI has to use unique value", phi, variables[phi])
            assert len(phi.operands) == len(bb.predecessors), ("Each PHI has arg. for each predecessor", phi, phi.operands, bb.predecessors)
            variables[phi] = phi
            for v, src_block in  phi.operands:
                assert src_block in bb.predecessors, (phi, src_block, bb.predecessors)
                assert isinstance(v, HConst) or v.block is not None, ("PHI operand was removed from SSA but it is still there", phi, v)

        for stm in bb.body:
            if isinstance(stm, SsaInstr):
                stm: SsaInstr
                assert stm not in variables, ("Each variable must be assigned just once", stm, variables[stm])
                variables[stm] = stm

        for _bb in bb.predecessors:
            if _bb not in blocks:
                self.visit_collect(_bb, blocks, phis, variables)

        for (_, _bb, _) in bb.successors.targets:
            if _bb not in blocks:
                self.visit_collect(_bb, blocks, phis, variables)

    def _check_variable_definition_for_use(self, var: Union[SsaValue, HConst],
                                           phis: SetList[SsaPhi],
                                           variables: Dict[SsaValue, SsaBasicBlock]):
        if isinstance(var, (HConst, HlsRead)):
            pass
        elif isinstance(var, SsaPhi):
            assert var in phis, ("Variable never defined", var)
        else:
            assert isinstance(var, _ValOrVal), (var, "Variable has unsupported value type", var.__class__)
            assert var in variables, ("Variable never defined", var)

    def visit_check(self, bb: SsaBasicBlock,
                    blocks: SetList[SsaBasicBlock],
                    phis: SetList[SsaPhi],
                    variables: Dict[SsaValue, SsaBasicBlock],
                    seen: Set[SsaBasicBlock]):
        assert bb in blocks
        seen.add(bb)
        for stm in bb.body:
            if isinstance(stm, SsaInstr):
                stm: SsaInstr
                assert isinstance(stm.operands, (tuple, list)), stm
                assert isinstance(stm.operator, HOperatorDef), stm
                for op in stm.operands:
                    self._check_variable_definition_for_use(op, phis, variables)

            else:
                raise NotImplementedError(stm)

        for (_, _bb, _) in bb.successors.targets:
            assert _bb in blocks, (_bb, "Missing reference on block")
            if _bb not in seen:
                self.visit_check(_bb, blocks, phis, variables, seen)

        for _bb in bb.predecessors:
            assert _bb in blocks, (_bb, "Missing reference on block")
            assert bb in _bb.successors.iterBlocks(), ("Missing successor", _bb, bb)
            if _bb not in seen:
                self.visit_check(_bb, blocks, phis, variables, seen)

    @override
    def runOnSsaModuleImpl(self, toSsa: "HlsAstToSsa"):
        bb = toSsa.start
        blocks: SetList[SsaBasicBlock] = SetList()
        phis: SetList[SsaPhi] = SetList()
        variables: Dict[SsaValue, SsaBasicBlock] = {}
        self.visit_collect(bb, blocks, phis, variables)
        seen = set()
        self.visit_check(bb, blocks, phis, variables, seen)

