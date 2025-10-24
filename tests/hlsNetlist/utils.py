from typing import Union, Tuple
import unittest

from hwt.hdl.operatorDefs import HOperatorDef
from hwt.hdl.types.defs import BIT
from hwt.hdl.types.sliceConst import HSliceConst
from hwtHls.frontend.ioProxyScalar import IoProxyScalar
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.platform.virtual import VirtualHlsPlatform


TestExprTy = Union[int, HlsNetNodeOut, Tuple["TestExprTy", HOperatorDef, "TestExprTy"]]


def exprToTestExprTy(e: HlsNetNodeOut):
    if isinstance(e.obj, HlsNetNodeConst):
        v = e.obj.val
        if isinstance(v, HSliceConst):
            return v.to_py()
        elif v._is_full_valid():
            return int(v)
        else:
            return v
    elif isinstance(e.obj, HlsNetNodeOperator):
        return (e.obj.operator, *(exprToTestExprTy(op) for op in e.obj.dependsOn))
    else:
        return e


class BaseHlsNetlistReduceTC(unittest.TestCase):

    @staticmethod
    def _createNetlist() -> Tuple[HlsNetlistCtx, HlsNetlistBuilder]:
        netlist = HlsNetlistCtx(VirtualHlsPlatform(), None, int(100e6), "test", "test", {})
        return netlist, netlist.builder

    def _r(self, netlist: HlsNetlistCtx, dtype=BIT):
        r = HlsNetNodeRead(netlist, IoProxyScalar(None, None), None, dtype=dtype)
        netlist.addNode(r)
        return r._outputs[0]

    def _w(self, src: HlsNetNodeOut):
        netlist = src.obj.netlist
        w = HlsNetNodeWrite(netlist, IoProxyScalar(None, None), None)
        netlist.addNode(w)
        src.connectHlsIn(w._portSrc)
        return w
