from itertools import islice
from typing import Dict, Tuple, Generator

from hwt.code import Or, And, Xor
from hwt.constants import NOT_SPECIFIED
from hwt.hdl.operatorDefs import HwtOps, HOperatorDef
from hwt.hdl.types.defs import BIT
from hwt.pyUtils.arrayQuery import grouper
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.netlist.abc.abcCpp import Abc_Ntk_t, Abc_Aig_t, Abc_Frame_t, Abc_Obj_t, \
    Abc_ObjType_t, recognizeMux2, recognizeMux3  # , Io_FileType_t


class AbcAigToRtlNetlist():
    """
    :attention: original RtlSignal inputs must be store in data of each ABC primary input
    :note: PI stands for Primary Input
    
    
    .. figure:: _static/abc_aig_patterns_basic.png
    
       Some of the AIG patterns which are translated back to its operand

    """

    def __init__(self, f: Abc_Frame_t, net: Abc_Ntk_t, aig: Abc_Aig_t, ioMap: Dict[str, RtlSignal]):
        self.f = f
        self.net = net
        self.aig = aig
        self.ioMap = ioMap
        self.translationCache: Dict[Tuple[Abc_Obj_t, bool], RtlSignal] = {}

    @classmethod
    def _collectOrMembers(cls, o: Abc_Obj_t):
        """
        Recursively collect all inputs which connected using "and" and are not and itself.
        :attention: it must be checked before that the top o is not just AND to
            avoid rewriting AND using NOT ORs

        :note: in AIG "a | b" is "~(~a & ~b)"
            "a | (b | c)" is ~(~a & (~b & ~c)) 
        """
        o0n = o.FaninC0()
        o1n = o.FaninC1()
        o0, o1 = o.IterFanin()
        o0isPi = o0.IsPi()
        o1isPi = o1.IsPi()

        # if is negated or is primary input end search otherwise drill down
        if o0n or o0isPi:
            yield (o0, not o0n)
        else:
            yield from cls._collectOrMembers(o0)

        if o1n or o1isPi:
            yield (o1, not o1n)
        else:
            yield from cls._collectOrMembers(o1)

    # @classmethod
    # def _collectAndMembers(cls, o: Abc_Obj_t):
    #    """
    #    Collect members (a, b, c) from patterns like (~a | ~b | ~c)
    #    to translate it to ~(a & b & c)
    #    """
    #    o0n = o.FaninC0()
    #    o1n = o.FaninC1()
    #    o0, o1 = o.IterFanin()
    #    o0isPi = o0.IsPi()
    #    o1isPi = o1.IsPi()
    #
    #
    # @classmethod
    # def _collectAndNotMembers(cls, o: Abc_Obj_t):
    #    """
    #    Collect members (a, b, c) from patterns like (~a & ~b & ~c)
    #    to translate it to ~(a | b | c)
    #    """

    def _recognizeNonAigOperator(self, o: Abc_Obj_t, negated: bool):
        """
        Check if object is in format:

        xor: (p0 & ~p1) | (p1 & ~p0)
        mux: (pC & p1) | (~pC & p0)
             (~pC | pT) & (pC | pF)
             ...
        or:  ~(~p0 & ~p1), ~(~p0 & ~p1 & ~p2 ...)
        not: ~(p0 & p0)
        not: (~p0 & ~p0)

        * prioritize not and before or of negated 
        * (~p0 | ~p1) -> ~(p0 & p1)
        * (~p0 & ~p1) -> ~(p0 | p1)
        """
        assert not o.IsComplement(), o
        m = recognizeMux3(negated, o)
        tr = self._translate
        if m is not None:
            res = (HwtOps.TERNARY, (tr(m.v0, m.v0n), tr(m.c0, m.c0n),
                                    tr(m.v1, m.v1n), tr(m.c1, m.c1n),
                                    tr(m.v2, m.v2n)))
            if m.isNegated:
                return (HwtOps.NOT, res)
            else:
                return res

        m = recognizeMux2(negated, o)
        if m is not None:
            res = (HwtOps.TERNARY, (tr(m.v0, m.v0n), tr(m.c0, m.c0n),
                                    tr(m.v1, m.v1n)))
            if m.isNegated:
                return (HwtOps.NOT, res)
            else:
                return res

        o0n = o.FaninC0()
        o1n = o.FaninC1()
        topIsOr = negated and o0n and o1n
        topP0, topP1 = o.IterFanin()

        if not topIsOr:
            # not: ~(p0 & p0)
            # not: (~p0 & ~p0)
            if topP0 == topP1 and ((negated and not o0n and not o1n) or
                                   (not negated and o0n and o1n)):
                return HwtOps.NOT, (tr(topP0, False),)

            # or: ~(~p0 & ~p1 & ~p2 ...)
            orMembers = tuple(self._collectOrMembers(o))
            if orMembers:
                allArePis = all(op.IsPi() for op, _ in orMembers)
                if len(orMembers) > 2 or allArePis:
                    if negated:
                        if all(n for _, n in orMembers):
                            # (~p0 | ~p1) -> ~(p0 & p1)
                            return HwtOps.NOT, (HwtOps.AND, tuple(tr(p, int(not n))
                                                                  for p, n in orMembers))
                        else:
                            return HwtOps.OR, tuple(tr(p, n)
                                                    for p, n in orMembers)
                    elif not allArePis or all(not n for _, n in orMembers):
                        # (~p0 & ~p1) -> ~(p0 | p1)
                        return HwtOps.NOT, (HwtOps.OR, tuple(tr(p, n)
                                                             for p, n in orMembers))

            return None

        # :note: top may be "or"
        if o0n and o1n and not topP0.IsPi() and not topP1.IsPi():
            P0o0n = topP0.FaninC0()
            P0o1n = topP0.FaninC1()
            P1o0n = topP1.FaninC0()
            P1o1n = topP1.FaninC1()
            P1o0, P1o1 = topP1.IterFanin()

            if (P0o0n + P0o1n) == 1 and (P1o0n + P1o1n) == 1:
                p0, p1 = topP0.IterFanin()
                if P0o0n:
                    p0, p1 = p1, p0

                P1o0, P1o1 = topP1.IterFanin()
                if P1o0n:
                    P1o0, P1o1 = P1o1, P1o0

                if p0 == P1o1 and p1 == P1o0:
                    # xor: (p0 & ~p1) | (p1 & ~p0)
                    return HwtOps.XOR, (tr(p0, False), tr(p1, False))

            elif not P0o0n and not P0o1n and (P1o0n + P1o1n) == 1:
                pc, p1 = topP0.IterFanin()  # both not negated
                P1o0, P1o1 = topP1.IterFanin()
                if not P1o0n:
                    # swap to have negated input on left side of second operand
                    P1o0, P1o1 = P1o1, P1o0
                    P1o0n, P1o1n = P1o1n, P1o0n

                if pc == P1o0:  # is in format ((~)pC & P0o1) | ((~)pC & P1o1)  (there is just 1 ~pC in expression)
                    if pc == P1o1:
                        # or: (pC & p1) | (~pC & pC) -> (pC & p1)
                        res = HwtOps.AND, (tr(pc, False), tr(p1, False))
                        if negated:
                            return res
                        else:
                            # ~(pC & p1)
                            return HwtOps.NOT, res

        if o0n and o1n:
            # or:  ~(~p0 & ~p1)
            res = HwtOps.OR, (tr(topP0, False), tr(topP1, False))
            if negated:
                return res
            else:
                # or:  ~~(~p0 & ~p1) = ~(p0 | p1)
                return HwtOps.NOT, res

    def _translate(self, o: Abc_Obj_t, negated: bool):
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
            res = BIT.from_py(int(not negated))

        else:
            res = self._recognizeNonAigOperator(o, negated)
            if res is not None:
                # some expr recognized from AIG pattern
                op, ops = res
                negated = False
                # pop NOTs from expression
                while op is HwtOps.NOT and isinstance(ops[0], HOperatorDef):
                    negated = not negated
                    op, ops = ops

                if op is HwtOps.OR and len(ops) != 2:
                    res = Or(*ops)
                elif op is HwtOps.AND and len(ops) != 2:
                    res = And(*ops)
                elif op is HwtOps.XOR and len(ops) != 2:
                    res = Xor(*ops)
                elif op is HwtOps.TERNARY:
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
                    res = op._evalFn(*ops)
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
