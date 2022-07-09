
from typing import Union, Set

from hwt.hdl.operator import Operator
from hwt.hdl.operatorDefs import COMPARE_OPS, AllOps
from hwt.hdl.statements.assignmentContainer import HdlAssignmentContainer
from hwt.hdl.statements.ifContainter import IfContainer
from hwt.hdl.statements.statement import HdlStatement
from hwt.hdl.value import HValue
from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.architecture.architecturalElement import AllocatorArchitecturalElement
from hwtHls.architecture.connectionsOfStage import ConnectionsOfStage, \
    extractControlSigOfInterfaceTuple
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.transformation.rtlNetlistPass import RtlNetlistPass
from hwtHls.netlist.abc.rtlNetlistToAbcAig import RtlNetlistToAbcAig
from hwtHls.netlist.abc.abcAigToRtlNetlist import AbcAigToRtlNetlist


class RtlNetlistPassControlLogicMinimize(RtlNetlistPass):

    @classmethod
    def _collect1bOpTree(cls, o: RtlSignal, inputs: UniqList[RtlSignal], inTreeOutputs: Set[RtlSignal]):
        """
        :returns: True if it is a non trivial output (output is trivial if driven by const or non-translated node,
            if the output is trivial it can not be optimized further)
        """
        if o in inTreeOutputs:
            # already discovered
            return True

        d = o.singleDriver()
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

        elif d.operator == AllOps.INDEX:
            inputs.append(o)
            return False

        for i in d.operands:
            if not isinstance(i, HValue):
                cls._collect1bOpTree(i, inputs, inTreeOutputs)
                inTreeOutputs.add(i)
            
        return True

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
    def iterConditions(cls, stm: HdlStatement):
        if isinstance(stm, HdlAssignmentContainer):
            return
        elif isinstance(stm, IfContainer):
            stm: IfContainer
            yield stm.cond
            for c, subStms in stm.elIfs:
                yield c
                for subStm in subStms:
                    yield from cls.iterConditions(subStm)
    
        else:
            for subStm in stm._iter_stms():
                yield from cls.iterConditions(subStm)

    @classmethod
    def iterDriverSignalsRec(cls, stm: HdlStatement, sig: RtlSignal):
        if isinstance(stm, HdlAssignmentContainer):
            src = stm.src
            if not isinstance(src, HValue):
                yield src
        else:
            for subStm in stm._iter_stms_for_output(sig):
                yield from cls.iterDriverSignalsRec(subStm, sig)

    @classmethod
    def iterDriverSignals(cls, sig: Union[RtlSignal, Interface]):
        if isinstance(sig, Interface):
            sig = sig._sig
        d = sig.singleDriver()
        if isinstance(d, HdlStatement):
            yield from cls.iterDriverSignalsRec(d, sig)
      
    def apply(self, hls: "HlsScope", netlist: HlsNetlistCtx):
        allControlIoOutputs: UniqList[RtlSignal] = UniqList()
        inputs: UniqList[RtlSignal] = []
        inTreeOutputs: Set[RtlSignal] = set()
        for elm in netlist.allocator._archElements:
            elm: AllocatorArchitecturalElement
            for con in elm.connections:
                con: ConnectionsOfStage
                if con.sync_node:
                    for m in con.sync_node.masters:
                        _, rd = extractControlSigOfInterfaceTuple(m)
                        self.collectControlDrivingTree(rd, allControlIoOutputs, inputs, inTreeOutputs)
                    for s in con.sync_node.slaves:
                        vld, _ = extractControlSigOfInterfaceTuple(s)
                        self.collectControlDrivingTree(vld, allControlIoOutputs, inputs, inTreeOutputs)
                
        # [todo] restrict to only statements generated from this HlsScope/thread
        for stm in netlist.parentUnit._ctx.statements:
            for c in self.iterConditions(stm):
                self.collectControlDrivingTree(c, allControlIoOutputs, inputs, inTreeOutputs)
        _collect = self._collect1bOpTree

        if allControlIoOutputs:
            toAbcAig = RtlNetlistToAbcAig()
            abcFrame, abcNet, abcAig = toAbcAig.translate(inputs, allControlIoOutputs)
            abcAig.Cleanup()
            toHlsNetlist = AbcAigToRtlNetlist(abcFrame, abcNet, abcAig)
            newOutputs = toHlsNetlist.translate()
            assert len(allControlIoOutputs) == len(newOutputs)
            for o, newO in zip(allControlIoOutputs, newOutputs):
                if o is not newO:
                    o: RtlSignal
                    for ep in o.endpoints:
                        if isinstance(ep, Operator):
                            # was already replaced when it was replaced in statement
                            pass
                            # ep: Operator
                            # ep._replace_input(o, newO)
                        elif isinstance(ep, HdlStatement):
                            ep: HdlStatement
                            ep._replace_input(o, newO)
                        else:
                            raise NotImplementedError(ep, o)

            abcFrame.DeleteAllNetworks()
