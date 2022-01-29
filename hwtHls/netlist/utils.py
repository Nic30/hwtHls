from hwt.hdl.operatorDefs import AllOps, OpDefinition
from hwt.hdl.types.defs import BIT
from hwt.pyUtils.arrayQuery import balanced_reduce
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, link_hls_nodes


def hls_op_not(hls: "HlsPipeline", a: HlsNetNodeOut) -> HlsNetNodeOperator:
    res = HlsNetNodeOperator(hls, AllOps.NOT, 1, BIT)
    hls.nodes.append(res)
    link_hls_nodes(a, res._inputs[0])
    return res._outputs[0]


def hls_op_or(hls: "HlsPipeline", a: HlsNetNodeOut, b: HlsNetNodeOut) -> HlsNetNodeOperator:
    return _hls_op_bin(hls, AllOps.OR, a, b)


def hls_op_and(hls: "HlsPipeline", a: HlsNetNodeOut, b: HlsNetNodeOut) -> HlsNetNodeOperator:
    return _hls_op_bin(hls, AllOps.AND, a, b)


def hls_op_and_variadic(hls: "HlsPipeline", *ops: HlsNetNodeOut):
    return balanced_reduce(ops, lambda a, b: hls_op_and(hls, a, b))


def _hls_op_bin(hls: "HlsPipeline", op: OpDefinition, a: HlsNetNodeOut, b: HlsNetNodeOut) -> HlsNetNodeOperator:
    res = HlsNetNodeOperator(hls, op, 2, BIT)
    hls.nodes.append(res)
    link_hls_nodes(a, res._inputs[0])
    link_hls_nodes(b, res._inputs[1])
    return res._outputs[0]
