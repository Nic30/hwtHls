from typing import Dict, Tuple

from hwt.code import Or
from hwt.hdl.operatorDefs import AllOps
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

    @classmethod
    def _collectOrMembers(cls, o: Abc_Obj_t):
        """
        Recursively collect all inputs which connected using "and" and are not and itself.
        """

        o0n = o.FaninC0()
        o1n = o.FaninC1()
        o0, o1 = o.IterFanin()
        o0isPi = o0.IsPi()
        o1isPi = o1.IsPi()
        if o0n or o0isPi:
            yield (o0, not o0n and o0isPi)
        else:
            yield from cls._collectOrMembers(o0)

        if o1n or o1isPi:
            yield (o1, not o1n and o1isPi)
        else:
            yield from cls._collectOrMembers(o1)

    def _recognizeNonAigOperator(self, o: Abc_Obj_t, negated: bool):
        """
        Check if object is in format:

        xor: (p0 & ~p1) | (p1 & ~p0)
        mux: (pC & p1) | (~pC & p0)
        or:  ~(~p0 & ~p1), ~(~p0 & ~p1 & ~p2 ...)
        not: ~(p0 & p0)
        not: (~p0 & ~p0)

        # [TODO] prioritize not and beore or of negated (~p0 | ~p1) -> ~(p0 & p1)
        """
        o0n = o.FaninC0()
        o1n = o.FaninC1()
        topIsOr = negated and o0n and o1n
        topP0, topP1 = o.IterFanin()
        tr = self._translate
        if not topIsOr:
            # not: ~(p0 & p0)
            # not: (~p0 & ~p0)
            if topP0 == topP1 and ((negated and not o0n and not o1n) or (not negated and o0n and o1n)):
                return AllOps.NOT, (tr(topP0, False),)
            if negated:
                # or: ~(~p0 & ~p1 & ~p2 ...)
                orMembers = tuple(self._collectOrMembers(o))
                if len(orMembers) > 2:
                    return AllOps.OR, tuple(tr(p, n) for p, n in orMembers)
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
                    # xor: (p0 & ~p1) | (p1 & ~p0)
                    return AllOps.XOR, (tr(p0, False), tr(p1, False))

            elif not P0o0n and not P0o1n and (P1o0n + P1o1n) == 1:
                pc, p1 = topP0.IterFanin()
                P1o0, P1o1 = topP1.IterFanin()
                if P1o1n:
                    P1o0, P1o1 = P1o1, P1o1
                if pc == P1o0:
                    if pc == P1o1:
                        # or: (pC & p1) | (~pC & pC)
                        return AllOps.OR, (tr(pc, False), tr(p1, False))

                    p0 = P1o1
                    # mux: (pC & p1) | (~pC & p0)
                    return AllOps.TERNARY, (tr(pc, False), tr(p0, False), tr(p1, False))

        # or:  ~(~p0 & ~p1)
        return AllOps.OR, (tr(topP0, False), tr(topP1, False))

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
                op, ops = res
                if op is AllOps.OR and len(ops) != 2:
                    res = Or(*ops)
                else:
                    res = op._evalFn(*ops)
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
