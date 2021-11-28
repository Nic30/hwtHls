from hwt.hdl.operatorDefs import AllOps, OpDefinition
from hwtHls.netlist.nodes.ops import HlsOperation
from hwtHls.netlist.nodes.ports import HlsOperationOut, link_hls_nodes
from hwt.pyUtils.arrayQuery import balanced_reduce


def hls_op_not(hls: "HlsPipeline", a: HlsOperationOut) -> HlsOperation:
    res = HlsOperation(hls, AllOps.NOT, 1, 1)
    hls.nodes.append(res)
    link_hls_nodes(a, res._inputs[0])
    return res._outputs[0]


def hls_op_or(hls: "HlsPipeline", a: HlsOperationOut, b: HlsOperationOut) -> HlsOperation:
    return _hls_op_bin(hls, AllOps.OR, a, b)


def hls_op_and(hls: "HlsPipeline", a: HlsOperationOut, b: HlsOperationOut) -> HlsOperation:
    return _hls_op_bin(hls, AllOps.AND, a, b)


def hls_op_and_variadic(hls: "HlsPipeline", *ops: HlsOperationOut):
    return balanced_reduce(ops, lambda a, b: hls_op_and(hls, a, b))


def _hls_op_bin(hls: "HlsPipeline", op: OpDefinition, a: HlsOperationOut, b: HlsOperationOut) -> HlsOperation:
    res = HlsOperation(hls, op, 2, 1)
    hls.nodes.append(res)
    link_hls_nodes(a, res._inputs[0])
    link_hls_nodes(b, res._inputs[1])
    return res._outputs[0]
