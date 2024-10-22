from typing import Tuple, Union, Optional

from hwt.hdl.operatorDefs import HwtOps
from hwt.pyUtils.setList import SetList
from hwtHls.architecture.analysis.nodeParentSyncNode import ArchSyncNodeTy
from hwtHls.netlist.abc.abcCpp import Abc_Frame_t, Abc_Ntk_t, Abc_NtkType_t, \
    Abc_NtkFunc_t, Abc_Aig_t
from hwtHls.netlist.abc.hlsNetlistToAbcAig import HlsNetlistToAbcAig
from hwtHls.netlist.nodes.aggregate import HlsNetNodeAggregatePortIn, \
    HlsNetNodeAggregatePortOut
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn
from pyMathBitPrecise.bit_utils import ValidityError
from hwtHls.architecture.transformation._syncLowering.syncLogicSearcher import SyncLogicSearcher


class SyncLogicHlsNetlistToAbc(HlsNetlistToAbcAig):

    def __init__(self, clkPeriod: int, name: str):
        HlsNetlistToAbcAig.__init__(self)
        # flags which are primary inputs to handshake logic, e.g. buffer.full
        self.clkPeriod = clkPeriod

        f = Abc_Frame_t.GetGlobalFrame()
        self.abcFrame: Abc_Frame_t = f
        net = Abc_Ntk_t(Abc_NtkType_t.ABC_NTK_STRASH, Abc_NtkFunc_t.ABC_FUNC_AIG, 64)
        net.setName(name)
        self.net: Abc_Ntk_t = net
        f.SetCurrentNetwork(net)
        # aig: Abc_Aig_t = net.pManFunc
        self.c1 = net.Const1()
        self.syncLogicNodes: SetList[Tuple[Union[HlsNetNodeOperator, HlsNetNodeAggregatePortIn, HlsNetNodeAggregatePortOut], int]] = None

    def _translateDriveOfOptionalIn(self, aig: Abc_Aig_t, clkI: int, inPort: Optional[HlsNetNodeIn]):
        if inPort is None:
            return None
        return self._translate(aig, (inPort.obj.dependsOn[inPort.in_i], clkI))

    def _translate(self, aig: Abc_Aig_t, item: Union[Tuple[HlsNetNodeOut, int],
                                                     ArchSyncNodeTy]):
        try:
            return self.translationCache[item]
        except KeyError:
            pass

        o, clkI = item
        d = o.obj
        # if item definition is coming from previous clock cycle
        # or driving node was not marked as handshake logic, this will be new primary input
        defTime = d.scheduledOut[o.out_i]
        beginOfClkWindow = clkI * self.clkPeriod
        if defTime < beginOfClkWindow or (d, clkI) not in self.syncLogicNodes:
            syncNode = (o.obj.parent, clkI)
            _syncNode = SyncLogicSearcher._getEarliestTimeIfValueIsPersistent(o, syncNode)[0]
            if _syncNode != syncNode:
                # case for outputs which are persistent trough multiple clock windows, translationCache contains record only for the 0, 1 clock window after def
                return self._translate(aig, (o, _syncNode[1]))
            raise AssertionError("This is primary input which should already be found and pre-populated in translationCache", item)
            # return self._onAbcAddPrimaryInput(o, clkI)
        else:
            # else this is some logic in this clock window
            if isinstance(d, HlsNetNodeConst):
                try:
                    v = int(d.val)
                except ValidityError:
                    v = 0  # convert 'X' to 0
                if v == 1:
                    res = self.c1
                else:
                    res = aig.Not(self.c1)

            elif isinstance(d, HlsNetNodeAggregatePortIn):
                o = d.depOnOtherSide()
                return self._translate(aig, (o, clkI))
            else:
                assert isinstance(d, HlsNetNodeOperator), (d, o)
                d: HlsNetNodeOperator
                op = d.operator
                inCnt = len(d._inputs)
                if inCnt == 1:
                    assert d.operator == HwtOps.NOT, d
                    res = aig.Not(self._translate(aig, (d.dependsOn[0], clkI)))

                elif inCnt == 2:
                    lhs, rhs = (self._translate(aig, (i, clkI)) for i in d.dependsOn)
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
                        o0, c, o1 = (self._translate(aig, (i, clkI)) for i in d.dependsOn)
                        res = aig.Mux(c, o0, o1)  # ABC notation is in in this order, p1, p0 means if c=1 or c=0
                    else:
                        assert inCnt % 2 == 1, d
                        prevVal = None
                        # mux must be build from end so first condition ends up at the top of expression (bottom of code)
                        for v, c in reversed(tuple(d._iterValueConditionDriverPairs())):
                            v = self._translate(aig, (v, clkI))
                            if c is not None:
                                c = self._translate(aig, (c, clkI))

                            if prevVal is None:
                                assert c is None
                                prevVal = v
                            else:
                                prevVal = aig.Mux(c, v, prevVal)

                        res = prevVal
                else:
                    raise NotImplementedError(d)

        assert item not in self.translationCache, o
        self.translationCache[item] = res
        return res
