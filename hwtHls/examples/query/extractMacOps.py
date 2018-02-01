from typing import Tuple

from hwt.hdl.operator import Operator
from hwt.hdl.operatorDefs import AllOps, OpDefinition
from hwt.interfaces.std import VectSignal
from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.param import Param
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwt.synthesizer.uniqList import UniqList
from hwt.synthesizer.unit import Unit
from hwtHls.examples.query.rtlNetlistManipulator import RtlNetlistManipulator
from hwtHls.hls import Hls
from hwtHls.platform.virtual import VirtualHlsPlatform


class QuerySignal():
    def __init__(self, label: str=None):
        self.label = label
        self.drivers = UniqList()
        self.endpoints = UniqList()
        self._usedOps = {}

    def setLabel(self, label: str):
        self.label = label

    def naryOp(self, operator, *otherOps):
        """
        Try lookup operator with this parameters in _usedOps
        if not found create new one and soter it in _usedOps
        """
        k = (operator, otherOps)
        try:
            return self._usedOps[k]
        except KeyError:
            pass

        o = QueryOperator.signalWrapped(operator, (self, *otherOps))
        self._usedOps[k] = o
        return o

    def __add__(self, other):
        return self.naryOp(AllOps.ADD, other)

    def __mul__(self, other):
        return self.naryOp(AllOps.MUL, other)

    def __call__(self, other):
        raise NotImplementedError()

    def __repr__(self):
        if self.label:
            return self.label
        else:
            return object.__repr__(self)


class QueryAssignment():
    def __init__(self, dst, src):
        #self.cond = UniqList()
        #self.indexes = None
        self.dst = dst
        self.src = src


class QueryOperator():
    def __init__(self, operator: OpDefinition, operands: Tuple[QuerySignal]):
        self.operator = operator
        self.operands = operands
        self.op_order_depends = operator in {
            AllOps.CONCAT, AllOps.DIV, AllOps.DOT,
            AllOps.DOWNTO, AllOps.LE, AllOps.LT,
            AllOps.GE, AllOps.GT, AllOps.MOD, AllOps.POW,
            AllOps.RISING_EDGE, AllOps.FALLIGN_EDGE,
            AllOps.SUB, AllOps.TERNARY, AllOps.TO
        }

    @staticmethod
    def signalWrapped(opertor: OpDefinition, ops: Tuple[QuerySignal]):
        s = QuerySignal()
        o = QueryOperator(opertor, ops)
        s.drivers.append(o)
        return s


def MAC_qurey():
    a = QuerySignal("a")
    b = QuerySignal("b")
    c = QuerySignal("c")
    d = QuerySignal("d")

    out = (a * b) + (c * d)
    out.setLabel("out")

    return out


class HwSelect():
    def __init__(self, ctx: Unit):
        self.ctx = ctx

    def match_operator_drivers(self, op: Operator, qop: QueryOperator, res: dict):
        if op.operator != qop.operator:
            return False
        # if not qop.op_order_depends:
        #    raise NotImplementedError()

        for oper, qoper in zip(op.operands, qop.operands):
            if not self.match_signal_drivers(oper, qoper, res):
                return False

        return True

    def match_signal_drivers(self, sig: RtlSignal, q: QuerySignal, res: dict):
        if not q.drivers:
            if q.label:
                res[q.label] = sig
            return True

        if len(sig.drivers) == len(q.drivers):
            if len(sig.drivers) != 1:
                # [TODO] need to check all combinations of driver oders
                raise NotImplementedError()

            for d, dq in zip(sig.drivers, q.drivers):
                if isinstance(dq, QueryOperator):
                    if isinstance(d, Operator) and self.match_operator_drivers(d, dq, res):
                        continue
                    else:
                        return False
                else:
                    raise NotImplementedError()

            if q.label:
                res[q.label] = sig
            return True

    def select(self, query):
        q = query()
        for sig in self.ctx.signals:
            res = {}
            if self.match_signal_drivers(sig, q, res):
                yield res


class MacExtractingHls(Hls):
    def _discoverAllNodes(self):
        m = RtlNetlistManipulator(self.ctx)
        for mac in HwSelect(self.ctx).select(MAC_qurey):
            print(mac)
        nodes = Hls._discoverAllNodes(self)
        return nodes


class GroupOfMacOps(Unit):
    def _config(self):
        self.CLK_FREQ = Param(int(25e6))
        self.INPUT_CNT = Param(4)

    def _declr(self):
        addClkRstn(self)
        assert int(self.INPUT_CNT) % 2 == 0

        self.dataIn0 = [VectSignal(32, signed=False)
                        for _ in range(int(self.INPUT_CNT))]
        self._registerArray("dataIn0", self.dataIn0)

        self.dataIn1 = [VectSignal(32, signed=False)
                        for _ in range(int(self.INPUT_CNT))]
        self._registerArray("dataIn1", self.dataIn1)

        self.dataOut0 = VectSignal(64, signed=False)
        self.dataOut1 = VectSignal(64, signed=False)

    def _impl(self):
        with MacExtractingHls(self, freq=self.CLK_FREQ) as hls:
            a, b, c, d = [hls.read(intf)
                          for intf in self.dataIn0]
            e = a * b + c * d
            hls.write(e, self.dataOut0)

            a, b, c, d = [hls.read(intf)
                          for intf in self.dataIn1]
            e = a * b + c * d
            hls.write(e, self.dataOut1)


if __name__ == "__main__":
    from hwt.synthesizer.utils import toRtl
    import unittest
    u = GroupOfMacOps()

    print(toRtl(u, targetPlatform=VirtualHlsPlatform()))
