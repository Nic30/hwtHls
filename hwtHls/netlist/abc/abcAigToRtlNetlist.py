from typing import Dict, Tuple

from hwt.hdl.operatorDefs import AllOps, OpDefinition
from hwt.hdl.types.defs import BIT
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.netlist.abc.abcCpp import Abc_Ntk_t, Abc_Aig_t, Abc_Frame_t, Abc_Obj_t, Abc_ObjType_t


class AbcAigToRtlNetlist():
    """
    :attention: original RtlSignal inputs must be store in data of each Abc primary input 
    """

    def __init__(self, f: Abc_Frame_t, net: Abc_Ntk_t, aig: Abc_Aig_t):
        self.f = f
        self.net = net
        self.aig = aig
        self.translationCache: Dict[Tuple[Abc_Obj_t, bool], RtlSignal] = {}

    def _recognizeNonAigOperator(self, o: Abc_Obj_t, negated: bool):
        """
        Check if object is in format:

        xor: (p0 & ~p1) | (p1 & ~p0)
        mux: (pC & p1) | (~pC & p0)
        or:  ~(~p0 & ~p1)
        not: ~(p0 & p0)
        not: (~p0 & ~p0)
        """
        o0n = o.FaninC0()
        o1n = o.FaninC1()
        topIsOr = negated and o0n and o1n
        topP0, topP1 = o.IterFanin()
        if not topIsOr:
            if topP0 == topP1 and ((negated and not o0n and not o1n) or (not negated and o0n and o1n)):
                return AllOps.NOT, topP0
            return None

        if not topP0.IsPi() and not topP1.IsPi():
            P0o0n = topP0.FaninC0()
            P0o1n = topP0.FaninC1()
            P1o0n = topP1.FaninC0()
            P1o1n = topP1.FaninC1()
            
            if (P0o0n + P0o1n) == 1 and (P1o0n + P1o1n) == 1:
                p0, p1 = topP0.IterFanin()
                if P0o0n:
                    p0, p1 = p1, p0
    
                P1o0, P1o1 = topP1.IterFanin()
                if P1o0n:
                    P1o0, P1o1 = P1o1, P1o0
     
                if p0 == P1o1 and p1 == P1o0:
                    return AllOps.XOR, p0, p1
    
            elif not P0o0n and not P0o1n and (P1o0n + P1o1n) == 1:
                pc, p1 = topP0.IterFanin()
                P1o0, P1o1 = topP1.IterFanin()
                if P1o1n:
                    P1o0, P1o1 = P1o1, P1o1
                if pc == P1o0:
                    p0 = P1o1
                    return AllOps.TERNARY, pc, p0, p1
        
        return AllOps.OR, topP0, topP1
    
    def _translate(self, o: Abc_Obj_t, negated: bool):
        key = (o, negated)
        try:
            return self.translationCache[key]
        except KeyError:
            pass

        if o.IsPi():
            res = o.Data()
            if negated:
                res = ~res
        
        elif o.Type == Abc_ObjType_t.ABC_OBJ_CONST1:
            res = BIT.from_py(int(not negated))

        else:
            res = self._recognizeNonAigOperator(o, negated)
            if res is not None:
                op: OpDefinition = res[0]
                res = op._evalFn(*(self._translate(_o, False) for _o in res[1:])) 
            else:
                o0, o1 = o.IterFanin()
                o0 = self._translate(o0, o.FaninC0()) 
                o1 = self._translate(o1, o.FaninC1()) 
                res = o0 & o1

                if negated:
                    res = ~res
                
        self.translationCache[key] = res
        return res

    def translate(self):
        res = []
        for o in self.net.IterPo():
            o: Abc_Obj_t
            res.append(self._translate(*o.IterFanin(), o.FaninC0()))
        return res
