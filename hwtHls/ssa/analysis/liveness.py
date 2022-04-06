# Computing Liveness Sets for SSA-Form Programs
# Algorithm 4 Computing liveness sets by exploring paths from variable uses.
from typing import Dict, Set, Union, Optional, Tuple

from hwt.hdl.value import HValue
from hwt.pyUtils.uniqList import UniqList
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.instr import SsaInstr
from hwtHls.ssa.phi import SsaPhi
from hwtHls.ssa.value import SsaValue
from hwtHls.ssa.transformation.utils.blockAnalysis import collect_all_blocks

# * Boissinot, B., Hack, S., Grund, D., de Dinechin, B. D., & Rastello, F. (2008). Fast Liveness Checking for SSA-Form Programs. CGO.
# * Domaine, & Brandner, Florian & Boissinot, Benoit & Darte, Alain & Dinechin, Benoît & Rastello, Fabrice. (2011).
#   Computing Liveness Sets for SSA-Form Programs.
# * https://github.com/lijiansong/clang-llvm-tutorial/blob/master/live-variable-analysis/Liveness.md


def collect_direct_provieds_and_requires(block: SsaBasicBlock):
    provides: UniqList[SsaValue] = UniqList()
    requires: UniqList[Tuple[SsaValue, SsaBasicBlock]] = UniqList()

    for phi in block.phis:
        phi: SsaPhi
        provides.append(phi)
        for (v, b) in phi.operands:
            if isinstance(v, HValue):
                continue

            requires.append((v, b))

    for i in block.body:
        i: SsaInstr
        provides.append(i)
        for v in i.iterInputs():
            if isinstance(v, HValue):
                continue

            if v not in provides:
                requires.append((v, None))
    
    for c, _ in block.successors.targets:
        if c is not None and c not in provides:
            requires.append((c, None))

    return provides, requires


EdgeLivenessDict = Dict[SsaBasicBlock, Dict[SsaBasicBlock, Set[SsaValue]]]


def recursively_add_edge_requirement_var(provides: Dict[SsaBasicBlock, UniqList[SsaValue]],
                                         src: SsaBasicBlock,
                                         dst: SsaBasicBlock,
                                         v: Union[SsaValue, SsaPhi],
                                         live: EdgeLivenessDict):
    if isinstance(v, HValue):
        return

    _live = live[src][dst]

    if v in _live:
        return

    assert isinstance(v, SsaValue), v

    _live.add(v)
    if v not in provides[src]:
        for pred in src.predecessors:
            recursively_add_edge_requirement_var(provides, pred, src, v, live)


def ssa_liveness_edge_variables(start: SsaBasicBlock) -> EdgeLivenessDict:
    live: EdgeLivenessDict = {}
    blocks = list(collect_all_blocks(start, set()))
    provides: Dict[SsaBasicBlock, UniqList[SsaValue]] = {}
    requires: Dict[SsaBasicBlock, UniqList[Tuple[SsaValue, Optional[SsaBasicBlock]]]] = {}
    # initialization
    for block in blocks:
        provides[block], requires[block] = collect_direct_provieds_and_requires(block)
        live[block] = {suc: set() for suc in block.successors.iterBlocks()}

    # transitive enclosure of requires relation
    for block in blocks:
        for req, req_if_predecessor_is in requires[block]:
            if req_if_predecessor_is is None:
                # requires from all predecessors
                for pred in block.predecessors:
                    recursively_add_edge_requirement_var(provides, pred, block, req, live)
            else:
                recursively_add_edge_requirement_var(provides, req_if_predecessor_is, block, req, live)

    return live
