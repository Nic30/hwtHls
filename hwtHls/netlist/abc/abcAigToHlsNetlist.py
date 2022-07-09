from typing import Dict, Tuple

from hwt.hdl.operatorDefs import AllOps, OpDefinition
from hwt.hdl.types.defs import BIT
from hwtHls.netlist.abc.abcCpp import Abc_Ntk_t, Abc_Aig_t, Abc_Frame_t, Abc_Obj_t, Abc_ObjType_t
from hwtHls.netlist.abc.abcAigToRtlNetlist import AbcAigToRtlNetlist
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.builder import HlsNetlistBuilder


class AbcAigToHlsNetlist(AbcAigToRtlNetlist):
    """
    :attention: original RtlSignal inputs must be store in data of each Abc primary input 
    """

    def __init__(self, f: Abc_Frame_t, net: Abc_Ntk_t, aig: Abc_Aig_t, builder: HlsNetlistBuilder):
        super(AbcAigToHlsNetlist, self).__init__(f, net, aig)
        self.builder = builder
        self.translationCache: Dict[Tuple[Abc_Obj_t, bool], HlsNetNodeOut] = {}

    def _translate(self, o: Abc_Obj_t, negated: bool):
        key = (o, negated)
        try:
            return self.translationCache[key]
        except KeyError:
            pass

        if o.IsPi():
            res = o.Data()
            if negated:
                res = self.builder.buildNot(res)
        elif o.Type == Abc_ObjType_t.ABC_OBJ_CONST1:
            res = BIT.from_py(int(not negated))
        else:
            res = self._recognizeNonAigOperator(o, negated)
            if res is not None:
                op: OpDefinition = res[0]
                ops = (self._translate(_o, False) for _o in res[1:])
                if op == AllOps.TERNARY:
                    self.builder.buildMux(BIT, tuple(ops))
                else:
                    res = self.builder.buildOp(op, BIT, *ops) 
            else:
                o0, o1 = o.IterFanin()
                o0 = self._translate(o0, o.FaninC0()) 
                o1 = self._translate(o1, o.FaninC1()) 
                res = self.builder.buildAnd(o0, o1)
                if negated:
                    res = self.builder.buildNot(res)
            
        self.translationCache[key] = res
        return res
