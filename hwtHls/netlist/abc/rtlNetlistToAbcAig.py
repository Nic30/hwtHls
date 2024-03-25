from typing import Dict, Tuple, Union

from hwt.hdl.operator import Operator
from hwt.hdl.operatorDefs import AllOps
from hwt.hdl.value import HValue
from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.netlist.abc.abcCpp import Abc_Ntk_t, Abc_Aig_t, Abc_NtkType_t, Abc_NtkFunc_t,\
    Abc_Frame_t, Abc_Obj_t #, Io_FileType_t


class RtlNetlistToAbcAig():

    def __init__(self,):
        self.translationCache: Dict[RtlSignal, Abc_Obj_t] = {}
        # the reference must be released because object is deleted when the AIG is deleted
        self.c1: Abc_Obj_t = None

    def _translate(self, aig: Abc_Aig_t, o: Union[RtlSignal, HValue]):
        try:
            return self.translationCache[o]
        except KeyError:
            pass
        if isinstance(o, HValue):
            res = self.c1
            if not bool(o):
                res = aig.Not(res)
            return res
        
        d = o.singleDriver()
        assert isinstance(d, Operator), (o, d)
        d: Operator
        op = d.operator
        if len(d.operands) == 1:
            assert d.operator == AllOps.NOT, d
            res = aig.Not(self._translate(aig, d.operands[0]))

        elif len(d.operands) == 2:
            lhs, rhs = (self._translate(aig, i) for i in d.operands)
            if op == AllOps.AND:
                res = aig.And(lhs, rhs)
            elif op == AllOps.OR:
                res = aig.Or(lhs, rhs)
            elif op == AllOps.XOR or op == AllOps.NE:
                res = aig.Xor(lhs, rhs)
            elif op == AllOps.EQ:
                res = aig.Or(aig.And(lhs, rhs), aig.And(aig.Not(lhs), aig.Not(rhs)))
            else:
                raise NotImplementedError(d)
        elif len(d.operands) == 3:
            assert d.operator == AllOps.TERNARY
            c, o0, o1 = (self._translate(aig, i) for i in d.operands)
            res = aig.Mux(c, o0, o1)
        else:
            raise NotImplementedError(d)
            
        self.translationCache[o] = res
        return res
           
    def translate(self, inputs: UniqList[RtlSignal], outputs: UniqList[RtlSignal]) -> Tuple[Abc_Frame_t, Abc_Ntk_t, Abc_Aig_t]:
        f = Abc_Frame_t.GetGlobalFrame()
        net = Abc_Ntk_t(Abc_NtkType_t.ABC_NTK_STRASH, Abc_NtkFunc_t.ABC_FUNC_AIG, 64)
        f.SetCurrentNetwork(net)
        aig: Abc_Aig_t = net.pManFunc
        self.c1 = net.Const1()
        
        for i in inputs:
            abcI = net.CreatePi()
            abcI.SetData(i)
            self.translationCache[i] = abcI
        
        for o in outputs:
            abcO = net.CreatePo()
            abcO.SetData(o)
            v = self._translate(aig, o)
            abcO.AddFanin(v)
        
        aig.Cleanup()
        net.Check()
        # net.Io_Write("abc-directly.0.dot", Io_FileType_t.IO_FILE_DOT)
        return f, net, aig
