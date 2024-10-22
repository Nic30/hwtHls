"""
HlsNetlist is used for scheduling and architectural features extraction and optimization.
This netlist is usually generated from LLVM MIR but it can be also constructed directly.
The netlist itself does not depends on any object from LLVM MIR.

The process of translation of LLVM MIR to HlsNetlist is described in :class:`from hwtHls.ssa.translation.llvmMirToNetlist.mirToNetlist.HlsNetlistAnalysisPassMirToNetlist
`

The HlsNetlist is composed of node instances :mod:`hwtHls.netlist.nodes` which do have input/output ports
which can be connected together (1:N).
The connection information is stored in node properties and can be accessed from both directions (src->dst, dst->src).
"""
