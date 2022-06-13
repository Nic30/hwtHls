from hwt.hdl.operatorDefs import AllOps, OpDefinition
from hwt.hdl.types.bits import Bits
from hwt.hdl.types.defs import SLICE
from hwt.pyUtils.arrayQuery import balanced_reduce
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, link_hls_nodes


def hls_op_not(netlist: "HlsNetlistCtx", a: HlsNetNodeOut) -> HlsNetNodeOperator:
    res = HlsNetNodeOperator(netlist, AllOps.NOT, 1, a._dtype)
    netlist.nodes.append(res)
    link_hls_nodes(a, res._inputs[0])
    return res._outputs[0]


def hls_op_or(netlist: "HlsNetlistCtx", a: HlsNetNodeOut, b: HlsNetNodeOut) -> HlsNetNodeOperator:
    return _hls_op_bin(netlist, AllOps.OR, a, b)


def hls_op_or_variadic(netlist: "HlsNetlistCtx", *ops: HlsNetNodeOut):
    return balanced_reduce(ops, lambda a, b: hls_op_or(netlist, a, b))


def hls_op_and(netlist: "HlsNetlistCtx", a: HlsNetNodeOut, b: HlsNetNodeOut) -> HlsNetNodeOperator:
    return _hls_op_bin(netlist, AllOps.AND, a, b)


def hls_op_and_variadic(netlist: "HlsNetlistCtx", *ops: HlsNetNodeOut):
    return balanced_reduce(ops, lambda a, b: hls_op_and(netlist, a, b))


def _hls_op_bin(netlist: "HlsNetlistCtx", op: OpDefinition, a: HlsNetNodeOut, b: HlsNetNodeOut) -> HlsNetNodeOperator:
    res = HlsNetNodeOperator(netlist, op, 2, a._dtype)
    netlist.nodes.append(res)
    link_hls_nodes(a, res._inputs[0])
    link_hls_nodes(b, res._inputs[1])
    return res._outputs[0]


def hls_op_concat(netlist: "HlsNetlistCtx", a: HlsNetNodeOut, b: HlsNetNodeOut) -> HlsNetNodeOperator:
    res = HlsNetNodeOperator(netlist, AllOps.CONCAT, 2, Bits(a._dtype.bit_length() + b._dtype.bit_length()))
    netlist.nodes.append(res)
    link_hls_nodes(a, res._inputs[0])
    link_hls_nodes(b, res._inputs[1])
    return res._outputs[0]


def hls_op_concat_variadic(netlist: "HlsNetlistCtx", *ops: HlsNetNodeOut):
    """
    :param ops: operands to concatenate, higher bits first 
    """
    assert ops
    res = None
    for o in reversed(ops):
        if res is None:
            res = o
        else:
            res = hls_op_concat(netlist, o, res)
    return res


def hls_op_const_index_slice(netlist: "HlsNetlistCtx", a: HlsNetNodeOut, high: int, low: int):
    assert high > low, (high, low)
    i = HlsNetNodeConst(netlist, SLICE.from_py(slice(high, low, -1)))
    netlist.nodes.append(i)
    res = HlsNetNodeOperator(netlist, AllOps.INDEX, 2, Bits(high - low))
    link_hls_nodes(a, res._inputs[0])
    link_hls_nodes(i, res._inputs[1])
    return res._outputs[0]
    
