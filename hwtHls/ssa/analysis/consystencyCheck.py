from typing import Set, Dict, Union

from hwt.hdl.operatorDefs import OpDefinition
from hwt.hdl.value import HValue
from hwt.pyUtils.uniqList import UniqList
from hwtHls.hlsStreamProc.statementsIo import HlsStreamProcRead
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.instr import SsaInstr
from hwtHls.ssa.phi import SsaPhi
from hwtHls.ssa.transformation.ssaPass import SsaPass
from hwtHls.ssa.value import SsaValue

_ValOrVal = (HValue, SsaValue)


class SsaPassConsystencyCheck(SsaPass):

    def visit_collect(self, bb: SsaBasicBlock, blocks: UniqList[SsaBasicBlock],
                      phis: UniqList[SsaPhi],
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
                assert isinstance(v, HValue) or v.block is not None, ("PHI operand was removed from SSA but it is still there", phi, v)

        for stm in bb.body:
            if isinstance(stm, SsaInstr):
                stm: SsaInstr
                assert stm not in variables, ("Each variable must be assigned just once", stm, variables[stm])
                variables[stm] = stm

        for _bb in bb.predecessors:
            if _bb not in blocks:
                self.visit_collect(_bb, blocks, phis, variables)

        for (_, _bb) in bb.successors.targets:
            if _bb not in blocks:
                self.visit_collect(_bb, blocks, phis, variables)

    def _check_variable_definition_for_use(self, var: Union[SsaValue, HValue],
                                           phis: UniqList[SsaPhi],
                                           variables: Dict[SsaValue, SsaBasicBlock]):
        if isinstance(var, (HValue, HlsStreamProcRead)):
            pass
        elif isinstance(var, SsaPhi):
            assert var in phis, ("Variable never defined", var)
        else:
            assert isinstance(var, _ValOrVal), var
            assert var in variables, ("Variable never defined", var)

    def visit_check(self, bb: SsaBasicBlock,
                    blocks: UniqList[SsaBasicBlock],
                    phis: UniqList[SsaPhi],
                    variables: Dict[SsaValue, SsaBasicBlock],
                    seen: Set[SsaBasicBlock]):
        assert bb in blocks
        seen.add(bb)
        for stm in bb.body:
            if isinstance(stm, SsaInstr):
                stm: SsaInstr
                assert isinstance(stm.operands, (tuple, list)), stm
                assert isinstance(stm.operator, OpDefinition), stm
                for op in stm.operands:
                    self._check_variable_definition_for_use(op, phis, variables)

            else:
                raise NotImplementedError(stm)

        for (_, _bb) in bb.successors.targets:
            assert _bb in blocks, (_bb, "Missing reference on block")
            if _bb not in seen:
                self.visit_check(_bb, blocks, phis, variables, seen)

        for _bb in bb.predecessors:
            assert _bb in blocks, (_bb, "Missing reference on block")
            assert bb in _bb.successors.iterBlocks(), ("Missing successor", _bb, bb)
            if _bb not in seen:
                self.visit_check(_bb, blocks, phis, variables, seen)

    def apply(self, hls: "HlsStreamProc", to_ssa: "HlsAstToSsa"):
        bb = to_ssa.start
        blocks: UniqList[SsaBasicBlock] = UniqList()
        phis: UniqList[SsaPhi] = UniqList()
        variables: Dict[SsaValue, SsaBasicBlock] = {}
        self.visit_collect(bb, blocks, phis, variables)
        seen = set()
        self.visit_check(bb, blocks, phis, variables, seen)

