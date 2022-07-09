from typing import Dict, Tuple, Optional

from hwt.hdl.operator import Operator
from hwt.hdl.operatorDefs import AllOps
from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.netlist.abc.abcCpp import Abc_Ntk_t, Abc_Aig_t, Abc_NtkType_t, Abc_NtkFunc_t, Abc_Frame_t, Abc_Obj_t, Abc_ObjType_t
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.abc.rtlNetlistToAbcAig import RtlNetlistToAbcAig
from hwtHls.netlist.nodes.const import HlsNetNodeConst


class HlsNetlistToAbcAig(RtlNetlistToAbcAig):

    def __init__(self,):
        self.translationCache: Dict[RtlSignal, Abc_Obj_t] = {}

    def _translate(self, aig: Abc_Aig_t, o: HlsNetNodeOut):
        try:
            return self.translationCache[o]
        except KeyError:
            pass

        d = o.obj
        if isinstance(d, HlsNetNodeConst):
            v = int(d.val)
            if v == 1:
                res = self.c1
            else:
                res = aig.Not(self.c1)

        else:
            assert isinstance(d, HlsNetNodeOperator), d
            d: HlsNetNodeOperator
            op = d.operator
            if len(d._inputs) == 1:
                assert d.operator == AllOps.NOT, d
                res = aig.Not(self._translate(aig, d.dependsOn[0]))
    
            elif len(d._inputs) == 2:
                lhs, rhs = (self._translate(aig, i) for i in d.dependsOn)
                if op == AllOps.AND:
                    res = aig.And(lhs, rhs)
                elif op == AllOps.OR:
                    res = aig.Or(lhs, rhs)
                elif op == AllOps.XOR:
                    res = aig.Xor(lhs, rhs)
                else:
                    raise NotImplementedError(d)
    
            elif len(d._inputs) == 3:
                assert d.operator == AllOps.TERNARY
                o0, c, o1 = (self._translate(aig, i) for i in d.dependsOn)
                res = aig.Mux(c, o1, o0) # ABC notation is in in this order
    
            else:
                raise NotImplementedError(d)
            
        self.translationCache[o] = res
        return res
           
    def translate(self, inputs: UniqList[HlsNetNodeOut], outputs: UniqList[HlsNetNodeOut]) -> Tuple[Abc_Frame_t, Abc_Ntk_t, Abc_Aig_t]:
        return super(HlsNetlistToAbcAig, self).translate(inputs, outputs)
