
from typing import Union, Set, Generator, Callable, Sequence

from hwt.hdl.operator import HOperatorNode
from hwt.hdl.operatorDefs import COMPARE_OPS, HwtOps
from hwt.hdl.statements.assignmentContainer import HdlAssignmentContainer
from hwt.hdl.statements.ifContainter import IfContainer
from hwt.hdl.statements.statement import HdlStatement
from hwt.hdl.types.defs import BIT, BOOL
from hwt.hdl.const import HConst
from hwt.pyUtils.setList import SetList
from hwt.serializer.utils import RtlSignal_sort_key
from hwt.hwIO import HwIO
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwt.synthesizer.rtlLevel.exceptions import SignalDriverErr
from hwtHls.architecture.connectionsOfStage import ConnectionsOfStage
from hwtHls.architecture.syncUtils import HwIO_getSyncTuple
from hwtHls.architecture.transformation.rtlNetlistPass import RtlNetlistPass
from hwtHls.netlist.abc.abcAigToRtlNetlist import AbcAigToRtlNetlist
from hwtHls.netlist.abc.abcCpp import Abc_Frame_t, Abc_Ntk_t, Abc_Aig_t  # , Io_FileType_t
from hwtHls.netlist.abc.optScripts import abcCmd_resyn2, abcCmd_compress2
from hwtHls.netlist.abc.rtlNetlistToAbcAig import RtlNetlistToAbcAig
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.archElement import ArchElement


class RtlNetlistPassControlLogicMinimize(RtlNetlistPass):
    """
    Run ABC logic optimizer on every branch condition, channel flag and every control signal in arch elements 
    
    :ivar verifyExprEquivalence: flag, True means that every updated expression should be checked for equivalence. 
    """

    def __init__(self, verifyExprEquivalence=False) -> None:
        RtlNetlistPass.__init__(self)
        self.verifyExprEquivalence = verifyExprEquivalence

    @classmethod
    def _collect1bOpTree(cls, o: RtlSignal, inputs: SetList[RtlSignal], inTreeOutputs: Set[RtlSignal]):
        """
        :return: True if it is a non trivial output (output is trivial if driven by const or non-translated node,
            if the output is trivial it can not be optimized further)
        """
        if o in inTreeOutputs:
            # already discovered
            return True
        try:
            d = o.singleDriver()
        except SignalDriverErr:
            d = None

        if not isinstance(d, HOperatorNode):
            inputs.append(o)
            return False

        d: HOperatorNode
        if d.operator in COMPARE_OPS:
            if d.operands[0]._dtype.bit_length() != 1:
                inputs.append(o)
                return False

        elif d.operator == HwtOps.TERNARY:
            assert o._dtype.bit_length() != 1, o

        elif d.operator not in (HwtOps.AND, HwtOps.OR, HwtOps.XOR, HwtOps.NOT):
            # exclude this operator from logic optimizations
            inputs.append(o)
            return False

        for i in d.operands:
            if not isinstance(i, HConst):
                cls._collect1bOpTree(i, inputs, inTreeOutputs)
                inTreeOutputs.add(i)
        return True

    @classmethod
    def iterConditions(cls, stm: HdlStatement):
        if isinstance(stm, HdlAssignmentContainer):
            return
        elif isinstance(stm, IfContainer):
            stm: IfContainer
            yield stm.cond
            for subStm in stm.ifTrue:
                yield from cls.iterConditions(subStm)

            for c, subStms in stm.elIfs:
                yield c
                for subStm in subStms:
                    yield from cls.iterConditions(subStm)
            if stm.ifFalse:
                for subStm in stm.ifFalse:
                    yield from cls.iterConditions(subStm)

        else:
            for subStm in stm._iter_stms():
                yield from cls.iterConditions(subStm)

    @classmethod
    def iterDriverSignalsRec(cls, stm: HdlStatement, sig: RtlSignal) -> Generator[RtlSignal, None, None]:
        if isinstance(stm, HdlAssignmentContainer):
            src = stm.src
            if not isinstance(src, HConst):
                yield src
        else:
            for subStm in stm._iter_stms_for_output(sig):
                yield from cls.iterDriverSignalsRec(subStm, sig)

    @classmethod
    def iterDriverSignals(cls, sig: Union[RtlSignal, HwIO]) -> Generator[RtlSignal, None, None]:
        if isinstance(sig, HwIO):
            sig = sig._sig
        d = sig.singleDriver()
        if isinstance(d, HdlStatement):
            yield from cls.iterDriverSignalsRec(d, sig)
        else:
            assert sig._dtype.bit_length() == 1, sig
            yield sig

    @classmethod
    def collectControlDrivingTree(cls, sig: Union[RtlSignal, HwIO, int, HConst],
                                  allControlIoOutputs: SetList[RtlSignal],
                                  inputs: SetList[RtlSignal],
                                  inTreeOutputs: Set[RtlSignal]):
        if isinstance(sig, (int, HConst)):
            return

        for s in cls.iterDriverSignals(sig):
            if s not in allControlIoOutputs and cls._collect1bOpTree(s, inputs, inTreeOutputs):
                allControlIoOutputs.append(s)

    @classmethod
    def collectAllControl(cls, netlist: HlsNetlistCtx,
                          collect: Callable[[
                                    Union[RtlSignal, HwIO, int, HConst],  # sig
                                    SetList[RtlSignal],  # allControlIoOutputs
                                    SetList[RtlSignal],  # inputs
                                    Set[RtlSignal]  # inTreeOutputs
                                    ], None
                                  ]):
        allControlIoOutputs: SetList[RtlSignal] = SetList()
        inputs: SetList[RtlSignal] = []
        inTreeOutputs: Set[RtlSignal] = set()
        for elm in netlist.nodes:
            elm: ArchElement
            for con in elm.connections:
                if con is None:
                    continue
                con: ConnectionsOfStage

                if con.syncNodeAck is not None:
                    if con.syncNodeAck.hidden:
                        src = con.syncNodeAck
                    else:
                        src = con.syncNodeAck.singleDriver().src
                    collect(src, allControlIoOutputs, inputs, inTreeOutputs)

                if con.syncNode:
                    for m in con.syncNode.masters:
                        _, rd = HwIO_getSyncTuple(m)
                        collect(rd, allControlIoOutputs, inputs, inTreeOutputs)

                    for s in con.syncNode.slaves:
                        vld, _ = HwIO_getSyncTuple(s)
                        collect(vld, allControlIoOutputs, inputs, inTreeOutputs)

            if elm._dbgAddSignalNamesToSync:
                for s in sorted(elm._dbgExplicitlyNamedSyncSignals, key=RtlSignal_sort_key):
                    assert s._dtype.bit_length() == 1
                    while True:
                        d = s.singleDriver()
                        if isinstance(d, HdlAssignmentContainer):
                            s = d.src  # skip all copies
                        elif isinstance(d, HOperatorNode):
                            collect(s, allControlIoOutputs, inputs, inTreeOutputs)
                            break
                        else:
                            break

        # [todo] restrict to only statements generated from this HlsScope/thread
        for stm in netlist.parentHwModule._ctx.statements:
            for c in cls.iterConditions(stm):
                assert c._dtype.bit_length() == 1, stm
                collect(c, allControlIoOutputs, inputs, inTreeOutputs)
        return allControlIoOutputs, inputs

    @staticmethod
    def _runAbc(abcFrame: Abc_Frame_t, abcNet: Abc_Ntk_t, abcAig: Abc_Aig_t):
        for _ in range(2):
            abcNet = abcCmd_resyn2(abcNet)
            abcNet = abcCmd_compress2(abcNet)

        return abcFrame, abcNet, abcAig

    @classmethod
    def _verifyAbcExprEquivalence(cls, inputs: Sequence[Union[RtlSignal, HConst]], expr0: Union[RtlSignal, HConst], expr1: Union[RtlSignal, HConst]):
        toAbcAig = RtlNetlistToAbcAig()
        miter = expr0 ^ expr1
        abcFrame, abcNet, abcAig, _ = toAbcAig.translate(inputs, miter)
        abcAig.Cleanup()
        abcFrame, abcNet, abcAig = cls._runAbc(abcFrame, abcNet, abcAig)
        # 1 means unsat, means that there is not a case where input differs
        miterIsConstant = abcNet.MiterIsConstant()
        assert miterIsConstant == 1, ("Expected to be equivalent", {0: "sat", 1: "unsat", -1: "undecided"}[miterIsConstant], expr0, "is not equivalent to", expr1)

    def runOnHlsNetlist(self, netlist: HlsNetlistCtx):
        allControlIoOutputs, inputs = self.collectAllControl(netlist, self.collectControlDrivingTree)
        if allControlIoOutputs:
            #allControlIoOutputs = [allControlIoOutputs[2], ]
            verifyExprEquivalence = self.verifyExprEquivalence
            toAbcAig = RtlNetlistToAbcAig()
            abcFrame, abcNet, abcAig, ioMap = toAbcAig.translate(inputs, allControlIoOutputs)
            abcAig.Cleanup()
            abcFrame, abcNet, abcAig = self._runAbc(abcFrame, abcNet, abcAig)
            toHlsNetlist = AbcAigToRtlNetlist(abcFrame, abcNet, abcAig, ioMap)
            for o, newO in toHlsNetlist.translate():
                if o is newO:
                    continue
                # add casts in the case of specific Bits type variant
                assert newO._dtype.bit_length() == 1, ("After optimization in ABC the type should remain the same",
                                                       o, o._dtype, "->", newO, newO._dtype)
                isNegatedTy = newO._dtype.negated
                if isNegatedTy:
                    newO = ~newO
                if isNegatedTy or o._dtype == BOOL:
                    newO = newO._isOn()
                if newO._dtype == BOOL and o._dtype == BIT:
                    newO = newO._auto_cast(BIT)
                if o is newO:
                    continue

                for ep in tuple(o.endpoints):
                    if isinstance(ep, HOperatorNode):
                        # was already replaced when it was replaced in statement
                        pass
                        # ep: HOperatorNode
                        # ep._replace_input((o, newO))
                    elif isinstance(ep, HdlStatement):
                        ep: HdlStatement
                        if verifyExprEquivalence:
                            self._verifyAbcExprEquivalence(inputs, o, newO)
                        # print("replacing")
                        # if isinstance(ep, HdlAssignmentContainer):
                        #     print("for: ", ep.dst)
                        # print(o)
                        # print(newO)
                        ep._replace_input((o, newO))
                    else:
                        raise NotImplementedError(ep, o)

            abcFrame.DeleteAllNetworks()
