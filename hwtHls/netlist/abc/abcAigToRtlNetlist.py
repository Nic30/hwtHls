from itertools import islice
from typing import Dict, Tuple, Generator, Union, Literal

from hwt.code import Or, And, Xor
from hwt.constants import NOT_SPECIFIED
from hwt.hdl.commonConstants import b0, b1
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.pyUtils.arrayQuery import grouper
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.netlist.abc.abcCpp import Abc_Ntk_t, Abc_Aig_t, Abc_Frame_t, Abc_Obj_t, \
    Abc_ObjType_t, AbcPatternRecognizer  # , Io_FileType_t


class AbcAigToRtlNetlist(AbcPatternRecognizer):
    """
    :attention: original RtlSignal inputs must be store in data of each ABC primary input
    :note: PI stands for Primary Input
    
    
    .. figure:: _static/abc_aig_patterns_basic.png
    
       Some of the AIG patterns which are translated back to its operand

    """

    def __init__(self, frame: Abc_Frame_t, net: Abc_Ntk_t, aig: Abc_Aig_t, ioMap: Dict[str, RtlSignal]):
        AbcPatternRecognizer.__init__(self)
        self.frame = frame
        self.net = net
        self.aig = aig
        self.ioMap = ioMap
        self.translationCache: Dict[Tuple[Abc_Obj_t, bool], Union[RtlSignal, HBitsConst]] = {}
    
    @classmethod
    def _popNegationFromRecognizedOp(cls, res: AbcPatternRecognizer.RecognizedOpResult):
        op = res.op
        ops = res.operands()
        negated = False
        Ops = cls.RecognizedOps
        # pop NOTs from expression
        while op is Ops.NOT and ops[0].op != Ops.NOP:
            negated = not negated
            op = ops[0].op
            ops = ops[0].operands()
        
        for o in ops:
            assert o.op == Ops.NOP
        ops = [o.val for o in ops]
        return negated, op, ops
    
    def _translate(self, o: Abc_Obj_t, negated: bool) -> Union[RtlSignal, Literal[b0, b1]]:
        assert not o.IsComplement(), o
        key = (o, negated)
        try:
            return self.translationCache[key]
        except KeyError:
            pass

        if o.IsPi():
            res = self.ioMap[o.Name()]
            # res = o.Data()
            if negated:
                res = ~res

        elif o.IsPo():
            raise AssertionError("Should be processed in translate()")

        elif o.Type == Abc_ObjType_t.ABC_OBJ_CONST1:
            res = b0 if negated else b1

        else:
            res = self._recognizeNonAigOperator(o, negated)
            if res is not None:
                # some expr recognized from AIG pattern
                Ops = self.RecognizedOps
                negated, op, ops = self._popNegationFromRecognizedOp(res)
                if op is Ops.NOT:
                    assert len(ops) == 1
                    res = ~ops[0]
                elif op is Ops.AND:
                    res = And(*ops)
                elif op is Ops.OR:
                    res = Or(*ops)
                elif op is Ops.XOR:
                    res = Xor(*ops)
                elif op is Ops.TERNARY:
                    if len(ops) == 3:
                        v0, c, v1 = ops
                        res = c._ternary(v0, v1)
                    else:
                        # take last 3 as a base and prepend mux for every c, v pair
                        v0, c, v1 = ops[-3:]
                        res = c._ternary(v0, v1)
                        assert (len(ops) - 3) % 2 == 0
                        for v, c in grouper(2, islice(ops, 0, len(ops) - 3), padvalue=NOT_SPECIFIED):
                            res = c._ternary(v, res)
                else:
                    raise ValueError(op)
            else:
                # default AIG to expr conversion
                o0, o1 = o.IterFanin()
                o0 = self._translate(o0, o.FaninC0())
                o1 = self._translate(o1, o.FaninC1())
                res = o0 & o1

            if negated:
                res = ~res

        self.translationCache[key] = res
        return res

    def translate(self) -> Generator[Tuple[RtlSignal, RtlSignal], None, None]:
        # self.net.Io_Write("abc-directly.dot", Io_FileType_t.IO_FILE_DOT)
        ioMap = self.ioMap
        for o in self.net.IterPo():
            o: Abc_Obj_t
            yield (ioMap[o.Name()], self._translate(*o.IterFanin(), o.FaninC0()))
