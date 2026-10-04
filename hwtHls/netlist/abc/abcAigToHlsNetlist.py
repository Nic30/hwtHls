from hwt.hdl.types.defs import BIT
from hwtHls.netlist.abc.abcAigToRtlNetlist import AbcAigToRtlNetlist
from hwtHls.netlist.abc.abcCpp import AbcPatternRecognizer 
from hwtHls.netlist.abc.abcCpp import Abc_Ntk_t, Abc_Aig_t, Abc_Frame_t, Abc_Obj_t, Abc_ObjType_t
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from itertools import islice


class AbcAigToHlsNetlist(AbcAigToRtlNetlist):
    """
    :attention: original RtlSignal inputs must be store in data of each Abc primary input 
    """

    def __init__(self, f: Abc_Frame_t, net: Abc_Ntk_t, aig: Abc_Aig_t, ioMap: dict[str, HlsNetNodeOut], builder: HlsNetlistBuilder):
        super(AbcAigToHlsNetlist, self).__init__(f, net, aig, ioMap)
        self.builder = builder
        self.translationCache: dict[tuple[Abc_Obj_t, bool], HlsNetNodeOut] = {}

    def _translate(self, o: Abc_Obj_t, negated: bool) -> HlsNetNodeOut:
        assert not o.IsComplement(), o
        key = (o, negated)
        try:
            return self.translationCache[key]
        except KeyError:
            pass

        if o.IsPi():
            res = self.ioMap[o.Name()]
            assert res is not None, (o.Name(),)
            # res = o.Data()
            if negated:
                res = self.builder.buildNot(res)
        elif o.Type == Abc_ObjType_t.ABC_OBJ_CONST1:
            res = self.builder.buildConstBit(int(not negated))
        else:
            res = self._recognizeNonAigOperator(o, negated)
            if res is not None:
                res: AbcPatternRecognizer.RecognizedOpResult
                Ops = self.RecognizedOps
                negated, op, ops = self._popNegationFromRecognizedOp(res)
                
                if op is Ops.NOT:
                    assert len(ops) == 1
                    res = self.builder.buildNot(ops[0])
                elif op is Ops.AND:
                    res = self.builder.buildAndVariadic(ops)
                elif op is Ops.OR:
                    res = self.builder.buildOrVariadic(ops)
                elif op is Ops.XOR:
                    res = ops[0]
                    for o in islice(ops, 1, None):
                        res = self.builder.buildXor(res, o)
               
                elif op is Ops.TERNARY:
                    res = self.builder.buildMux(BIT, tuple(ops))
                else:
                    raise ValueError(op)
            else:
                _o0, _o1 = o.IterFanin()
                o0 = self._translate(_o0, o.FaninC0())
                o1 = self._translate(_o1, o.FaninC1())

                assert o0.obj not in self.builder._removedNodes, res
                assert o1.obj not in self.builder._removedNodes, res
                res = self.builder.buildAnd(o0, o1)
                assert res.obj not in self.builder._removedNodes, res

            if negated:
                # :note: on _recognizeNonAigOperator success the negated flag is modified
                res = self.builder.buildNot(res)

            assert res.obj not in self.builder._removedNodes, res

        self.translationCache[key] = res
        return res
