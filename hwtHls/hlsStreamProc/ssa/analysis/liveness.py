# Computing Liveness Sets for SSA-Form Programs
# Algorithm 4 Computing liveness sets by exploring paths from variable uses.
from typing import Dict, Set, Union, Optional, Tuple, List

from hwt.hdl.value import HValue
from hwt.pyUtils.uniqList import UniqList
from hwtHls.hlsStreamProc.ssa.basicBlock import SsaBasicBlock
from hwtHls.hlsStreamProc.ssa.instr import SsaInstr
from hwtHls.hlsStreamProc.ssa.phi import SsaPhi, TmpVariable
from hwtHls.hlsStreamProc.statements import HlsStreamProcRead


# * Boissinot, B., Hack, S., Grund, D., de Dinechin, B. D., & Rastello, F. (2008). Fast Liveness Checking for SSA-Form Programs. CGO.
# * Domaine, & Brandner, Florian & Boissinot, Benoit & Darte, Alain & Dinechin, Benoît & Rastello, Fabrice. (2011).
#   Computing Liveness Sets for SSA-Form Programs.
# * https://github.com/lijiansong/clang-llvm-tutorial/blob/master/live-variable-analysis/Liveness.md
def collect_blocks(start: SsaBasicBlock):
    seen: Set[SsaBasicBlock] = set()
    to_search: UniqList[SsaBasicBlock] = UniqList((start,))
    while to_search:
        block: SsaBasicBlock = to_search.pop()
        if block in seen:
            continue
        seen.add(block)
        yield block
        for suc in block.successors.iter_blocks():
            if suc not in seen:
                to_search.append(suc)


def collect_direct_provieds_and_requires(block: SsaBasicBlock):
    provides = UniqList()
    requires = UniqList()

    for phi in block.phis:
        phi: SsaPhi
        provides.append(phi.dst)
        for (v, b) in phi.operands:
            if isinstance(v, HValue):
                continue
            elif isinstance(v, SsaPhi):
                v = v.dst
            requires.append((v, b))

    for i in block.body:
        i: SsaInstr
        provides.append(i.dst)
        for v in i.iterInputs():
            if isinstance(v, (HValue, HlsStreamProcRead)):
                continue
            elif isinstance(v, SsaPhi):
                v = v.dst
            if v not in provides:
                requires.append((v, None))

    return provides, requires


EdgeLivenessDict = Dict[SsaBasicBlock, Dict[SsaBasicBlock, Set[TmpVariable]]]


def recursively_add_edge_requirement_var(provides: Dict[SsaBasicBlock, UniqList[TmpVariable]],
                                         src: SsaBasicBlock,
                                         dst: SsaBasicBlock,
                                         v: Union[TmpVariable, SsaPhi],
                                         live: EdgeLivenessDict):
    _live = live[src][dst]
    if isinstance(v, SsaPhi):
        v = v.dst
    if isinstance(v, HValue) or v in _live:
        return

    _live.add(v)
    if v not in provides[src]:
        # print(v)
        for pred in src.predecessors:
            recursively_add_edge_requirement_var(provides, pred, src, v, live)


def ssa_liveness_edge_variables(start: SsaBasicBlock) -> EdgeLivenessDict:
    live: EdgeLivenessDict = {}
    blocks = list(collect_blocks(start))
    provides: Dict[SsaBasicBlock, UniqList[TmpVariable]] = {}
    requires: Dict[SsaBasicBlock, UniqList[Tuple[TmpVariable, Optional[SsaBasicBlock]]]] = {}
    # initialization
    for block in blocks:
        provides[block], requires[block] = collect_direct_provieds_and_requires(block)
        live[block] = {suc: set() for suc in block.successors.iter_blocks()}
    # for block in blocks:
    #    print(block)
    #    print("  provides", provides[block])
    #    print("  requires", requires[block])

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

# The variable used as input phi does not need to be live-out of all predecessors
# it is live_out only for those which are blocks which are selected by phi in that case

# Computing Liveness Sets for SSA-Form Programs: Algorithm 4: Computing liveness sets by exploring paths from variable uses.
# def phi_defines(block: SsaBasicBlock, v: Union[SsaPhi, TmpVariable]):
#    for phi in block.phis:
#        if v is phi or v is phi.dst:
#            return True
#    return False
#
#
# LivenessDict = Dict[SsaBasicBlock, Set[Union[TmpVariable, SsaPhi]]]
#
#
# def _ssa_liveness(start: SsaBasicBlock):
#    live_in: LivenessDict = {}
#    live_out:LivenessDict = {}
#    for B in collect_blocks(start):
#        B_live_out = live_out.setdefault(B, set())
#        # Consider all blocks successively
#        for suc in B.successors.iter_blocks():
#            for phi in suc.phis:  # Used in the φ of a successor block
#                phi: SsaPhi
#                for (v, b) in phi.operands:
#                    if b is not B or isinstance(v, HValue):
#                        # propagateonly to those variables which are selected by the branch
#                        continue
#                    B_live_out.add(v)
#                    dfs_find_uses(live_in, live_out, suc, v)
#
#        for instr in B.body:
#            for v in instr.iterInputs():
#                if isinstance(v, HValue):
#                    continue
#                dfs_find_uses(live_in, live_out, B, v)  # Traverse the block to find all uses
#
#        for (v, suc) in B.successors.targets:
#            if v is None or isinstance(v, HValue):
#                # skip non variables
#                continue
#
#            dfs_find_uses(live_in, live_out, B, v)
#
#    return live_in, live_out
#
#
# def body_defines(B: SsaBasicBlock, v: Union[SsaPhi, TmpVariable]):
#    for i in B.body:
#        if i.dst is v:
#            return True
#    return False
#
#
# # Computing Liveness Sets for SSA-Form Programs: Algorithm 5 Exploring all paths from a variable’s use to its definition.
# def dfs_find_uses(live_in:LivenessDict, live_out:LivenessDict, B:SsaBasicBlock, v:Union[SsaPhi, TmpVariable]):
#    if phi_defines(B, v) or body_defines(B, v):
#        return  # defined in this block
#
#    B_live_in = live_in.setdefault(B, set())
#    if v in B_live_in:
#        return  # Propagation already done, stop
#
#    B_live_in.add(v)
#    for P in B.predecessors:  # Propagate backward
#        live_out.setdefault(P, set()).add(v)
#        dfs_find_uses(live_in, live_out, P, v)
#
# # Algorithm 6 Computing liveness sets per variable using def-use chains.
# def Compute_LiveSets_SSA_ByVar(CFG):
#    for each variable v:
#        for each use of v in a block B:
#            if v used at exit of B: # Used in the φ of a successor block
#                live_out(B).add(v)
#            dfs_mark_liveness(B, v)
