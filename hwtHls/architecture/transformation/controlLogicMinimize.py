
from typing import Union, Set, Generator, Callable

from hwt.hdl.operator import Operator
from hwt.hdl.operatorDefs import COMPARE_OPS, AllOps
from hwt.hdl.statements.assignmentContainer import HdlAssignmentContainer
from hwt.hdl.statements.ifContainter import IfContainer
from hwt.hdl.statements.statement import HdlStatement
from hwt.hdl.value import HValue
from hwt.pyUtils.uniqList import UniqList
from hwt.serializer.utils import RtlSignal_sort_key
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwt.synthesizer.rtlLevel.signalUtils.exceptions import SignalDriverErr
from hwtHls.architecture.archElement import ArchElement
from hwtHls.architecture.connectionsOfStage import ConnectionsOfStage, \
    extractControlSigOfInterfaceTuple
from hwtHls.architecture.transformation.rtlNetlistPass import RtlNetlistPass
from hwtHls.netlist.abc.abcAigToRtlNetlist import AbcAigToRtlNetlist
from hwtHls.netlist.abc.optScripts import abcCmd_resyn2, abcCmd_compress2
from hwtHls.netlist.abc.rtlNetlistToAbcAig import RtlNetlistToAbcAig
from hwtHls.netlist.context import HlsNetlistCtx


class RtlNetlistPassControlLogicMinimize(RtlNetlistPass):
    """
    Run ABC logic optimizer on every branch condition, channel flag and every control signal in arch elements 
    """
    @classmethod
    def _collect1bOpTree(cls, o: RtlSignal, inputs: UniqList[RtlSignal], inTreeOutputs: Set[RtlSignal]):
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
        if not isinstance(d, Operator):
            inputs.append(o)
            return False

        d: Operator
        if d.operator in COMPARE_OPS:
            if d.operands[0]._dtype.bit_length() != 1:
                inputs.append(o)
                return False

        elif d.operator == AllOps.TERNARY:
            assert o._dtype.bit_length() != 1, o

        elif d.operator not in (AllOps.AND, AllOps.OR, AllOps.XOR, AllOps.NOT):
            # exclude this operator from logic optimizations
            inputs.append(o)
            return False

        for i in d.operands:
            if not isinstance(i, HValue):
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
            if not isinstance(src, HValue):
                yield src
        else:
            for subStm in stm._iter_stms_for_output(sig):
                yield from cls.iterDriverSignalsRec(subStm, sig)

    @classmethod
    def iterDriverSignals(cls, sig: Union[RtlSignal, Interface]) -> Generator[RtlSignal, None, None]:
        if isinstance(sig, Interface):
            sig = sig._sig
        d = sig.singleDriver()
        if isinstance(d, HdlStatement):
            yield from cls.iterDriverSignalsRec(d, sig)
        else:
            assert sig._dtype.bit_length() == 1, sig
            yield sig

    @classmethod
    def collectControlDrivingTree(cls, sig: Union[RtlSignal, Interface, int, HValue],
                                  allControlIoOutputs: UniqList[RtlSignal],
                                  inputs: UniqList[RtlSignal],
                                  inTreeOutputs: Set[RtlSignal]):
        if isinstance(sig, (int, HValue)):
            return

        for s in cls.iterDriverSignals(sig):
            if s not in allControlIoOutputs and cls._collect1bOpTree(s, inputs, inTreeOutputs):
                allControlIoOutputs.append(s)

    @classmethod
    def collectAllControl(cls, netlist: HlsNetlistCtx,
                          collect: Callable[[
                                    Union[RtlSignal, Interface, int, HValue],  # sig
                                    UniqList[RtlSignal],  # allControlIoOutputs
                                    UniqList[RtlSignal],  # inputs
                                    Set[RtlSignal]  # inTreeOutputs
                                    ], None
                                  ]):
        allControlIoOutputs: UniqList[RtlSignal] = UniqList()
        inputs: UniqList[RtlSignal] = []
        inTreeOutputs: Set[RtlSignal] = set()
        for elm in netlist.allocator._archElements:
            elm: ArchElement
            for con in elm.connections:
                con: ConnectionsOfStage
                # [todo] con.stageDataVld
                if isinstance(con.syncNodeAck, RtlSignal):
                    if con.syncNodeAck.hidden:
                        src = con.syncNodeAck
                    else:
                        src = con.syncNodeAck.singleDriver().src
                    collect(src, allControlIoOutputs, inputs, inTreeOutputs)

                if con.sync_node:
                    for m in con.sync_node.masters:
                        _, rd = extractControlSigOfInterfaceTuple(m)
                        collect(rd, allControlIoOutputs, inputs, inTreeOutputs)

                    for s in con.sync_node.slaves:
                        vld, _ = extractControlSigOfInterfaceTuple(s)
                        collect(vld, allControlIoOutputs, inputs, inTreeOutputs)
            
            if elm._dbgAddNamesToSyncSignals:
                for s in sorted(elm._dbgExplicitlyNamedSyncSignals, key=RtlSignal_sort_key):
                    assert s._dtype.bit_length() == 1
                    while True:
                        d = s.singleDriver()
                        if isinstance(d, HdlAssignmentContainer):
                            s = d.src  # skip all copies
                        elif isinstance(d, Operator):
                            collect(s, allControlIoOutputs, inputs, inTreeOutputs)
                            break
                        else:
                            break

        # [todo] restrict to only statements generated from this HlsScope/thread
        for stm in netlist.parentUnit._ctx.statements:
            for c in cls.iterConditions(stm):
                assert c._dtype.bit_length() == 1, stm
                collect(c, allControlIoOutputs, inputs, inTreeOutputs)
        return allControlIoOutputs, inputs

    def apply(self, hls: "HlsScope", netlist: HlsNetlistCtx):
        allControlIoOutputs, inputs = self.collectAllControl(netlist, self.collectControlDrivingTree)

        if allControlIoOutputs:
            toAbcAig = RtlNetlistToAbcAig()
            abcFrame, abcNet, abcAig = toAbcAig.translate(inputs, allControlIoOutputs)
            abcAig.Cleanup()

            abcNet = abcCmd_resyn2(abcNet)
            abcNet = abcCmd_compress2(abcNet)

            toHlsNetlist = AbcAigToRtlNetlist(abcFrame, abcNet, abcAig)
            newOutputs = toHlsNetlist.translate()
            assert len(allControlIoOutputs) == len(newOutputs)
            for o, newO in zip(allControlIoOutputs, newOutputs):
                if o is not newO:
                    o: RtlSignal
                    assert newO._dtype.bit_length() == 1, (o, o._dtype, "->", newO, newO._dtype)

                    for ep in o.endpoints:
                        if isinstance(ep, Operator):
                            # was already replaced when it was replaced in statement
                            pass
                            # ep: Operator
                            # ep._replace_input((o, newO))
                        elif isinstance(ep, HdlStatement):
                            ep: HdlStatement
                            if newO._dtype.negated:
                                newO = ~newO
                            newO = newO._isOn()
                            ep._replace_input((o, newO))
                        else:
                            raise NotImplementedError(ep, o)

            abcFrame.DeleteAllNetworks()
