from typing import Set, Dict

from hwt.hdl.operatorDefs import OpDefinition
from hwt.hdl.value import HValue
from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.hlsStreamProc.ssa.basicBlock import SsaBasicBlock
from hwtHls.hlsStreamProc.ssa.instr import SsaInstr, ValOrVal
from hwtHls.hlsStreamProc.ssa.phi import SsaPhi, HlsTmpVariable
from hwtHls.hlsStreamProc.statements import HlsStreamProcWrite, HlsStreamProcRead

_ValOrVal = (HlsTmpVariable, RtlSignal, HValue, SsaPhi)


class SsaConsystencyCheck():

    def visit_collect(self, bb: SsaBasicBlock, blocks: UniqList[SsaBasicBlock],
                      phis: UniqList[SsaPhi],
                      variables: Dict[HlsTmpVariable, SsaBasicBlock]):
        blocks.append(bb)
        for phi in bb.phis:
            phi: SsaPhi
            assert phi not in phis, ("phi has to be defined only once", phi, bb)
            assert phi.block is bb, ("phi has parent block correct", phi, phi.block, bb)
            phis.append(phi)
            assert phi.dst not in variables, ("Each phi has to use unique value", phi, variables[phi.dst])
            variables[phi.dst] = phi
            for _, src_block in  phi.operands:
                assert src_block in bb.predecessors, (phi, src_block, bb.predecessors)

        for stm in bb.body:
            if isinstance(stm, SsaInstr):
                stm: SsaInstr
                assert stm.dst not in variables, ("Each variable must be assigned just once", stm, variables[stm.dst])
                variables[stm.dst] = stm

        for _bb in bb.predecessors:
            if _bb not in blocks:
                self.visit_collect(_bb, blocks, phis, variables)

        for (_, _bb) in bb.successors.targets:
            if _bb not in blocks:
                self.visit_collect(_bb, blocks, phis, variables)

    def _check_variable_definition_for_use(self, var: ValOrVal,
                                           phis: UniqList[SsaPhi],
                                           variables: Dict[HlsTmpVariable, SsaBasicBlock]):
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
                    variables: Dict[HlsTmpVariable, SsaBasicBlock],
                    seen: Set[SsaBasicBlock]):
        assert bb in blocks
        seen.add(bb)
        for stm in bb.body:
            if isinstance(stm, SsaInstr):
                stm: SsaInstr
                src = stm.src
                if isinstance(src, tuple):
                    assert len(src) == 2, ("Invalid number of operator aguments", src)

                    assert isinstance(src[0], OpDefinition), src
                    for op in src[1]:
                        self._check_variable_definition_for_use(op, phis, variables)
                else:
                    self._check_variable_definition_for_use(src, phis, variables)
            elif isinstance(stm, HlsStreamProcWrite):
                stm: HlsStreamProcWrite
                self._check_variable_definition_for_use(stm.src, phis, variables)
            else:
                raise NotImplementedError(stm)

        for (_, _bb) in bb.successors.targets:
            assert _bb in blocks, (_bb, "Missing reference on block")
            if _bb not in seen:
                self.visit_check(_bb, blocks, phis, variables, seen)

        for _bb in bb.predecessors:
            assert _bb in blocks, (_bb, "Missing reference on block")
            assert bb in _bb.successors.iter_blocks(), ("Missing successor", _bb, bb)
            if _bb not in seen:
                self.visit_check(_bb, blocks, phis, variables, seen)

    def visit(self, bb: SsaBasicBlock):
        blocks: UniqList[SsaBasicBlock] = UniqList()
        phis: UniqList[SsaPhi] = UniqList()
        variables: Dict[HlsTmpVariable, SsaBasicBlock] = {}
        self.visit_collect(bb, blocks, phis, variables)
        seen = set()
        self.visit_check(bb, blocks, phis, variables, seen)
