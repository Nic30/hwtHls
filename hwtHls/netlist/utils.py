from hwt.hdl.operatorDefs import AllOps, OpDefinition
from hwtHls.netlist.codeOps import HlsOperation
from hwtHls.netlist.codeOpsPorts import HlsOperationOut, link_hls_nodes, HlsOperationIn
from hwtHls.hlsPipeline import HlsPipeline


def hls_op_not(hls: HlsPipeline, a: HlsOperationOut) -> HlsOperation:
    res = HlsOperation(hls, AllOps.NOT, 1, 1)
    hls.nodes.append(res)
    link_hls_nodes(a, HlsOperationIn(res, 0))
    return HlsOperationOut(res, 0)


def hls_op_or(hls: HlsPipeline, a: HlsOperationOut, b: HlsOperationOut) -> HlsOperation:
    return _hls_op_bin(hls, AllOps.OR, a, b)


def hls_op_and(hls: HlsPipeline, a: HlsOperationOut, b: HlsOperationOut) -> HlsOperation:
    return _hls_op_bin(hls, AllOps.AND, a, b)


def _hls_op_bin(hls: HlsPipeline, op: OpDefinition, a: HlsOperationOut, b: HlsOperationOut) -> HlsOperation:
    res = HlsOperation(hls, op, 2, 1)
    hls.nodes.append(res)
    link_hls_nodes(a, HlsOperationIn(res, 0))
    link_hls_nodes(b, HlsOperationIn(res, 1))
    return HlsOperationOut(res, 0)
