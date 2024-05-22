from typing import Dict, Tuple, Union, Sequence

from hwt.hdl.operator import HOperatorNode
from hwt.hdl.operatorDefs import HwtOps
from hwt.hdl.const import HConst
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.netlist.abc.abcCpp import Abc_Ntk_t, Abc_Aig_t, Abc_NtkType_t, Abc_NtkFunc_t, \
    Abc_Frame_t, Abc_Obj_t  # , Io_FileType_t


class RtlNetlistToAbcAig():

    def __init__(self,):
        self.translationCache: Dict[RtlSignal, Abc_Obj_t] = {}
        # the reference must be released because object is deleted when the AIG is deleted
        self.c1: Abc_Obj_t = None

    def _translate(self, aig: Abc_Aig_t, o: Union[RtlSignal, HConst]):
        try:
            return self.translationCache[o]
        except KeyError:
            pass
        if isinstance(o, HConst):
            res = self.c1
            if not bool(o):
                res = aig.Not(res)
            return res

        d = o.singleDriver()
        assert isinstance(d, HOperatorNode), (o, d)
        d: HOperatorNode
        op = d.operator
        if len(d.operands) == 1:
            assert d.operator == HwtOps.NOT, d
            res = aig.Not(self._translate(aig, d.operands[0]))

        elif len(d.operands) == 2:
            lhs, rhs = (self._translate(aig, i) for i in d.operands)
            if op == HwtOps.AND:
                res = aig.And(lhs, rhs)
            elif op == HwtOps.OR:
                res = aig.Or(lhs, rhs)
            elif op == HwtOps.XOR or op == HwtOps.NE:
                res = aig.Xor(lhs, rhs)
            elif op == HwtOps.EQ:
                res = aig.Or(aig.And(lhs, rhs), aig.And(aig.Not(lhs), aig.Not(rhs)))
            else:
                raise NotImplementedError(d)
        elif len(d.operands) == 3:
            assert d.operator == HwtOps.TERNARY
            c, o0, o1 = (self._translate(aig, i) for i in d.operands)
            res = aig.Mux(c, o0, o1)
        else:
            raise NotImplementedError(d)

        self.translationCache[o] = res
        return res

    def translate(self, inputs: Sequence[RtlSignal], outputs: Sequence[RtlSignal])\
            ->Tuple[Abc_Frame_t, Abc_Ntk_t, Abc_Aig_t, Dict[str, Tuple[Abc_Obj_t, RtlSignal]]]:
        f = Abc_Frame_t.GetGlobalFrame()
        net = Abc_Ntk_t(Abc_NtkType_t.ABC_NTK_STRASH, Abc_NtkFunc_t.ABC_FUNC_AIG, 64)
        f.SetCurrentNetwork(net)
        aig: Abc_Aig_t = net.pManFunc
        self.c1 = net.Const1()
        # :note: we can not store Abc_Obj_t because the object could be discarded after first operation with network
        #        we can not use index because IO may reorder and we can not use Id because it also changes
        ioMap: Dict[str, Tuple[str, RtlSignal]] = {}
        for i in inputs:
            abcI = net.CreatePi()
            ioMap[abcI.Name()] = i
            # abcI.SetData(i)
            self.translationCache[i] = abcI

        for o in outputs:
            abcO = net.CreatePo()
            ioMap[abcO.Name()] = o
            # abcO.SetData(o)
            v = self._translate(aig, o)
            abcO.AddFanin(v)

        aig.Cleanup()  # removes dangling nodes
        net.Check()
        # net.Io_Write("abc-directly.0.dot", Io_FileType_t.IO_FILE_DOT)
        return f, net, aig, ioMap
