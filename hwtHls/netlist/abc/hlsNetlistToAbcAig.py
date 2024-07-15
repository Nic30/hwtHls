from typing import Dict, Tuple

from hwt.hdl.operatorDefs import HwtOps
from hwt.pyUtils.setList import SetList
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.netlist.abc.abcCpp import Abc_Ntk_t, Abc_Aig_t, Abc_Frame_t, Abc_Obj_t
from hwtHls.netlist.abc.rtlNetlistToAbcAig import RtlNetlistToAbcAig
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from pyMathBitPrecise.bit_utils import ValidityError


class HlsNetlistToAbcAig(RtlNetlistToAbcAig):

    def __init__(self):
        self.translationCache: Dict[RtlSignal, Abc_Obj_t] = {}

    def _translate(self, aig: Abc_Aig_t, o: HlsNetNodeOut):
        try:
            return self.translationCache[o]
        except KeyError:
            pass

        d = o.obj
        if isinstance(d, HlsNetNodeConst):
            try:
                v = int(d.val)
            except ValidityError:
                v = 0
            if v == 1:
                res = self.c1
            else:
                res = aig.Not(self.c1)

        else:
            assert isinstance(d, HlsNetNodeOperator), d
            d: HlsNetNodeOperator
            op = d.operator
            inCnt = len(d._inputs)
            if inCnt == 1:
                assert d.operator == HwtOps.NOT, d
                res = aig.Not(self._translate(aig, d.dependsOn[0]))
    
            elif inCnt == 2:
                lhs, rhs = (self._translate(aig, i) for i in d.dependsOn)
                if op == HwtOps.AND:
                    res = aig.And(lhs, rhs)
                elif op == HwtOps.OR:
                    res = aig.Or(lhs, rhs)
                elif op == HwtOps.XOR:
                    res = aig.Xor(lhs, rhs)
                elif op == HwtOps.EQ:
                    res = aig.Eq(lhs, rhs)
                elif op == HwtOps.NE:
                    res = aig.Ne(lhs, rhs)
                else:
                    raise NotImplementedError(d)
    
            elif inCnt >= 3:
                assert d.operator == HwtOps.TERNARY
                if inCnt == 3:
                    o0, c, o1 = (self._translate(aig, i) for i in d.dependsOn)
                    res = aig.Mux(c, o0, o1)  # ABC notation is in in this order, p1, p0 means if c=1 or c=0
                else:
                    assert inCnt % 2 == 1, d
                    prevVal = None
                    # mux must be build from end so first condition ends up at the top of expression (bottom of code)
                    for v, c in reversed(tuple(d._iterValueConditionDriverPairs())):
                        v = self._translate(aig, v)
                        if c is not None:
                            c = self._translate(aig, c)

                        if prevVal is None:
                            assert c is None
                            prevVal = v
                        else:
                            prevVal = aig.Mux(c, v, prevVal)

                    res = prevVal
            else:
                raise NotImplementedError(d)
        
        assert o not in self.translationCache, o
        self.translationCache[o] = res
        return res
           
    def translate(self, inputs: SetList[HlsNetNodeOut], outputs: SetList[HlsNetNodeOut]) -> Tuple[Abc_Frame_t, Abc_Ntk_t, Abc_Aig_t]:
        return super(HlsNetlistToAbcAig, self).translate(inputs, outputs)
