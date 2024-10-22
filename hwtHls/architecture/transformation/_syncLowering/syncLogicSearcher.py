from typing import Tuple, Callable, List, Dict, Union

from hwt.hdl.operatorDefs import HwtOps
from hwt.pyUtils.setList import SetList
from hwtHls.architecture.analysis.handshakeSCCs import \
    ReadOrWriteType, AllIOsOfSyncNode
from hwtHls.architecture.analysis.nodeParentSyncNode import ArchSyncNodeTy
from hwtHls.netlist.nodes.aggregate import HlsNetNodeAggregatePortIn, \
    HlsNetNodeAggregatePortOut
from hwtHls.netlist.nodes.archElementFsm import ArchElementFsm
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.mux import HlsNetNodeMux
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.schedulableNode import SchedTime
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.scheduler.clk_math import beginOfClk, beginOfNextClk
from hwtHls.netlist.nodes.fsmStateWrite import HlsNetNodeFsmStateWrite
from hwtHls.netlist.nodes.channelUtils import CHANNEL_ALLOCATION_TYPE


class SyncLogicSearcher():
    """
    Sync logic collection:
    * for io node collect input flag expressions (extraCond, skipWhen, mayFlush, forceEn)
      * consume expression until some non ABC compatible node is reached or clock boundary is reached.
      * :note: 1b "and", "or", "xor", "==", "!=", "mux" are abc compatible
      * :note: search must stop at clock window boundary because logic is driven from register
        on that boundary, before that boundary it is a different value.
    * add all ready, valid, readyNB, validNB if it is not guaranteed to be driven from register
    * collect all abc compatible user nodes for every expression and follow expression in both sides
      to collect whole cluster of ABC compatible nodes
    * build expressions for:
      * enable of sync nodes
      * enable of io node
      * mayFlush, forceEn of io nodes if required
    
    :note: The combination loop may happen because expression for valid/ready contain source sync node enable
        Which could be computed from enable of this node.
    """
    ABC_COMPATIBLE_OPS = (HwtOps.NOT, HwtOps.AND, HwtOps.OR, HwtOps.XOR)
    ABC_COMPATIBLE_OPS_IF_1b = (HwtOps.EQ, HwtOps.NE, HwtOps.TERNARY)

    def __init__(self, clkPeriod: SchedTime, scc: SetList[ArchSyncNodeTy], onPrimaryInputFound: Callable[[HlsNetNodeOut, ArchSyncNodeTy], None]):
        self.clkPeriod = clkPeriod
        self.scc = scc
        self.primaryInputs: SetList[Tuple[HlsNetNodeOut, ArchSyncNodeTy]] = SetList()
        self.primaryInputsReplacedByNegationOf: Dict[Tuple[HlsNetNodeOut, int], Tuple[HlsNetNodeOut, int]] = {}
        self.primaryOutputs: SetList[Tuple[HlsNetNodeOut, ArchSyncNodeTy]] = SetList()
        self.nodes: SetList[Tuple[Union[HlsNetNodeOperator, HlsNetNodeAggregatePortIn, HlsNetNodeAggregatePortOut], int]] = SetList()
        self._onPrimaryInputFound = onPrimaryInputFound

    @classmethod
    def _isAbcCompatible(cls, n: HlsNetNode):
        if isinstance(n, HlsNetNodeConst):
            return True
        elif isinstance(n, HlsNetNodeOperator):
            if n.operator in cls.ABC_COMPATIBLE_OPS:
                return True
            elif n.operator in cls.ABC_COMPATIBLE_OPS_IF_1b and n.dependsOn[0]._dtype.bit_length() == 1:
                return True
            else:
                return False
        # if this is the aggregate port collect it as well
        elif isinstance(n, HlsNetNodeAggregatePortIn):
            return True
        elif isinstance(n, HlsNetNodeAggregatePortOut):
            return True

        assert not isinstance(n, HlsNetNodeMux), ("HlsNetNodeMux was expected to be HlsNetNodeOperator with operator TERNARY", n)
        return False

    @classmethod
    def _isInputWhichWillBeAlsoConsumed(cls, inp: HlsNetNodeIn):
        n = inp.obj
        if isinstance(n, HlsNetNodeExplicitSync):
            return inp in (n.extraCond, n.skipWhen, n._forceEnPort)
        else:
            return False

    def _collectDefToUse(self, toSearchDefToUse: SetList[HlsNetNodeOut], toSearchUseToDef: SetList[HlsNetNodeOut],
                         syncNode: ArchSyncNodeTy, beginTime: SchedTime, endTime: SchedTime):
        """
        Search up in expression tree (input leafs on bottom)
        
        :note: items in toSearchDefToUse does not need to have node object in self.nodes and are not automatically added to it
        """
        nodes = self.nodes
        while toSearchDefToUse:
            o = toSearchDefToUse.pop()
            oIsInNodes = (o.obj, syncNode[1]) in nodes
            defTime = o.obj.scheduledOut[o.out_i]
            isDefinedInThisClk = beginTime <= defTime and defTime < endTime
            oMayBecomePrimaryOut = isDefinedInThisClk and (oIsInNodes or self._isOutputComputedBySyncLogic(o))
            # check if any user can be collected to this cluster of nodes which will then be translated to ABC
            for use in o.obj.usedBy[o.out_i]:
                useObj: HlsNetNode = use.obj
                useObjWithClkIndex = (useObj, syncNode[1])
                if useObjWithClkIndex in nodes:
                    continue  # already previously collected

                useTime = useObj.scheduledIn[use.in_i]
                if useTime < beginTime or useTime >= endTime:
                    if oMayBecomePrimaryOut:
                        self.primaryOutputs.append((o, syncNode))
                    continue  # this is an user of this output outside of this clock window, make output a primary output

                if not self._isAbcCompatible(useObj):
                    if oMayBecomePrimaryOut and not self._isInputWhichWillBeAlsoConsumed(use):
                        # only if the use is not driving any node which will be also consumed
                        # add it as a primary node
                        self.primaryOutputs.append((o, syncNode))
                    continue  # not compatible with ABC -> make this primary input of collected graph

                nodes.append(useObjWithClkIndex)
                for depOfUseObj in useObj.dependsOn:
                    self._addToSearchUseToDef(depOfUseObj, toSearchUseToDef, syncNode, beginTime, endTime)

                # continue search on outputs of current output user
                for useOutPort, useOutTime in zip(useObj._outputs, useObj.scheduledOut):
                    assert useOutTime >= beginTime and useOutTime <= endTime, useOutPort
                    toSearchDefToUse.append(useOutPort)

        return toSearchUseToDef

    def _isOutputComputedBySyncLogic(self, o: HlsNetNodeOut):
        node = o.obj
        if isinstance(node, HlsNetNodeRead):
            w = node.associatedWrite
            if w is not None and w.getParentSyncNode() in self.scc and (o is node._valid or o is node._validNB):
                if w._getBufferCapacity() == 0:
                    return True

        elif isinstance(node, HlsNetNodeWrite):
                r = node.associatedRead
                if r is not None and r.getParentSyncNode() in self.scc and (o is node._ready or o is node._readyNB):
                    return True

        return False

    @staticmethod
    def _getEarliestTimeIfValueIsPersistent(o: HlsNetNodeOut, syncNode: ArchSyncNodeTy) -> Tuple[ArchSyncNodeTy, int]:
        """
        Some outputs may have persistenceRanges items in future. For those we want to pick
        earliest time when the value is defined to prevent duplications.
        """
        elm, clkI = syncNode
        if isinstance(elm, ArchElementFsm):
            elm: ArchElementFsm
            clkPeriod = elm.netlist.normalizedClkPeriod
            n = o.obj
            defClkI = n.scheduledOut[o.out_i] // clkPeriod
            lastClkWhenIsPersistent = elm._endClkI
            # instead of value from clkI take the value from first clock window when the value become persistent
            if isinstance(n, HlsNetNodeRead):
                n: HlsNetNodeRead
                w = n.associatedWrite
                if w is not None and w.allocationType == CHANNEL_ALLOCATION_TYPE.REG:
                    if w.isBackedge():
                        # if this is a backedge and the value is used after write, there must be a copy
                        # to keep original values for later code
                        wClkI = w.scheduledZero // clkPeriod
                        if clkI > wClkI:
                            return (elm, wClkI + 1), lastClkWhenIsPersistent
                        else:
                            lastClkWhenIsPersistent = wClkI

                    # use value directly from read
                    return (elm, defClkI), lastClkWhenIsPersistent

            # use value from next clk if it is < clkI
            if defClkI + 1 < clkI:
                return (elm, defClkI + 1), lastClkWhenIsPersistent
            else:
                return syncNode, lastClkWhenIsPersistent

        return syncNode, syncNode[1]

    def _addToSearchUseToDef(self, dep: HlsNetNodeOut, toSearchUseToDef: SetList[HlsNetNodeOut],
                              syncNode: ArchSyncNodeTy,
                              beginTime: SchedTime, endTime: SchedTime):
        """
        search if any dependency of this node can be also collected to ABC compatible cluster
        :returns: True if dep was already collected and no further probing is required else False  
        """
        nodes = self.nodes
        depObj: HlsNetNode = dep.obj
        depObjWithClkIndex = (depObj, syncNode[1])
        assert depObj.scheduledOut is not None, ("Dependency node was supposed to be scheduled", depObj)

        if depObjWithClkIndex in nodes:
            return True  # already collected

        if not self._isAbcCompatible(depObj):
            syncNode = self._getEarliestTimeIfValueIsPersistent(dep, syncNode)[0]
            if self.primaryInputs.append((dep, syncNode)):
                self._onPrimaryInputFound(dep, syncNode)
            return False  # already collected

            # if not self._isOutputComputedBySyncLogic(dep):
            #    return False  # abc not compatible node -> primary input

        depTime = depObj.scheduledOut[dep.out_i]
        if depTime < beginTime or depTime >= endTime:
            syncNode = self._getEarliestTimeIfValueIsPersistent(dep, syncNode)[0]
            if self.primaryInputs.append((dep, syncNode)):
                self._onPrimaryInputFound(dep, syncNode)

            return False  # dep is defined in other clock window -> primary input

        # continue search on inputs of current input
        toSearchUseToDef.append(dep)
        return False

    def _collectUseToDef(self, toSearchUseToDef: SetList[HlsNetNodeOut], toSearchDefToUse: SetList[HlsNetNodeOut],
                         syncNode: ArchSyncNodeTy, beginTime: SchedTime, endTime: SchedTime):
        """
        Search down in expression tree (input leafs on bottom)
        
        :attention: Object in toSearchUseToDef can be only node which are ABC compatible.
            if node is in nodes, it is not searched. The node itself is added to nodes.
        """
        nodes = self.nodes
        while toSearchUseToDef:
            o: HlsNetNodeOut = toSearchUseToDef.pop()
            oObj: HlsNetNode = o.obj

            oObjWithClkIndex = (oObj, syncNode[1])
            if oObjWithClkIndex in nodes:
                continue  # it was already collected

            nodes.append(oObjWithClkIndex)
            toSearchDefToUse.extend(oObj._outputs)
            for oObjDep in oObj.dependsOn:
                self._addToSearchUseToDef(oObjDep, toSearchUseToDef, syncNode, beginTime, endTime)

        return toSearchDefToUse

    def _collectAnyDir(self, toSearchUseToDef: SetList[HlsNetNodeOut],
                       toSearchDefToUse: SetList[HlsNetNodeOut],
                       syncNode: ArchSyncNodeTy, beginTime: SchedTime, endTime: SchedTime):
        while toSearchDefToUse or toSearchUseToDef:
            if toSearchDefToUse:
                self._collectDefToUse(toSearchDefToUse, toSearchUseToDef, syncNode, beginTime, endTime)
            if toSearchUseToDef:
                self._collectUseToDef(toSearchUseToDef, toSearchDefToUse, syncNode, beginTime, endTime)

    def collectFromInput(self, syncNode: ArchSyncNodeTy, inp: HlsNetNodeIn):
        time = inp.obj.scheduledIn[inp.in_i]
        clkPeriod = self.clkPeriod
        beginTime: SchedTime = beginOfClk(time, clkPeriod)
        endTime: SchedTime = beginOfNextClk(time, clkPeriod)
        toSearchDefToUse: SetList[HlsNetNodeOut] = SetList()
        toSearchUseToDef: SetList[HlsNetNodeOut] = SetList()

        dep: HlsNetNodeOut = inp.obj.dependsOn[inp.in_i]
        assert dep is not None, ("Input was supposed to be connected", inp)

        if self._addToSearchUseToDef(dep, toSearchUseToDef, syncNode, beginTime, endTime):
            return  # already collected

        toSearchDefToUse.append(dep)

        self._collectAnyDir(toSearchUseToDef, toSearchDefToUse, syncNode, beginTime, endTime)

    def collectFromOutput(self, syncNode: ArchSyncNodeTy, out: HlsNetNodeOut):
        time = out.obj.scheduledOut[out.out_i]
        clkPeriod = self.clkPeriod
        beginTime: SchedTime = beginOfClk(time, clkPeriod)
        endTime: SchedTime = beginOfNextClk(time, clkPeriod)
        toSearchUseToDef: SetList[HlsNetNodeOut] = SetList()

        if self._addToSearchUseToDef(out, toSearchUseToDef, syncNode, beginTime, endTime):
            return  # already collected

        toSearchDefToUse: SetList[HlsNetNodeOut] = SetList((out,))
        self._collectAnyDir(toSearchUseToDef, toSearchDefToUse, syncNode, beginTime, endTime)

    def collectFlagDefsFromIONodes(self, allSccIOs: AllIOsOfSyncNode):
        """
        Collect sync logic expressions into syncLogicSearch and readyNB/validNB computed by sync logic 
        """
        readyValidComputedBySyncLogic: List[Tuple[HlsNetNodeOut, int]] = []
        for (_, ioNode, syncNode, ioTy) in allSccIOs:
            ioNode: HlsNetNodeExplicitSync
            syncNode: ArchSyncNodeTy
            ioTy: ReadOrWriteType
            clkI = syncNode[1]

            for flag in [ioNode.extraCond, ioNode.skipWhen]:
                if flag is not None:
                    self.collectFromInput(syncNode, flag)

            if ioTy == ReadOrWriteType.CHANNEL_W:
                if ioNode._getBufferCapacity() == 0:
                    assert ioNode._forceEnPort is None, (ioNode, "forceEnPort port should not be used for 0 capacity buffers")

            isChannel = ioTy.isChannel()
            # if this is a channel we add this as a primary input and we also create a primary output
            # with an expression which will replace this later
            # if this is not channel the ready/valid will not be rewritten as is a primary input
            # of this handshake logic
            if ioTy.isRead():
                if ioNode._rtlUseValid:
                    vldNB = ioNode.getValidNB()
                    vld = ioNode._valid
                    w = ioNode.associatedWrite
                    if isChannel and w._getBufferCapacity() == 0:
                        readyValidComputedBySyncLogic.append((vldNB, clkI))
                    if vld is not None:
                        self.collectFromOutput(syncNode, vld)
                    if vldNB is not None:
                        self.collectFromOutput(syncNode, vldNB)
                else:
                    assert ioNode._validNB is None, ioNode
                    assert ioNode._valid is None, ioNode

            else:
                forceEn = ioNode._forceEnPort
                if forceEn is not None:
                    self.collectFromInput(syncNode, forceEn)

                if ioNode._rtlUseReady:
                    rdNB = ioNode.getReadyNB()
                    rd = ioNode._ready
                    if isChannel:
                        readyValidComputedBySyncLogic.append((rdNB, clkI))
                    if ioNode._getBufferCapacity() > 0:
                        if ioNode._shouldUseReadValidNBInsteadOfFullPort():
                            r = ioNode.associatedRead
                            rSyncNode = r.getParentSyncNode()
                            rValidNB = r.getValidNB()
                            # :note: must not search for uses of rValidNB because rSyncNode may not be in this SCC
                            if self.primaryInputs.append((rValidNB, rSyncNode)):
                                self._onPrimaryInputFound(rValidNB, rSyncNode)
                        else:
                            self.collectFromOutput(syncNode, ioNode.getFullPort())

                    if rd is not None:
                        self.collectFromOutput(syncNode, rd)
                    if rdNB is not None:
                        self.collectFromOutput(syncNode, rdNB)
                else:
                    assert ioNode._readyNB is None, ioNode
                    assert ioNode._ready is None, ioNode

        return readyValidComputedBySyncLogic

    def collectFromSCCEnable(self, scc: SetList[ArchSyncNodeTy]):
        # collect primary inputs from stage enable
        for syncNode in scc:
            elm, clkI = syncNode
            if isinstance(elm, ArchElementFsm):
                en, _ = elm.getStageEnable(clkI)

                self.collectFromOutput(syncNode, en)

    def collectFromFsmStateNextWrite(self, scc: SetList[ArchSyncNodeTy]):
        for syncNode in scc:
            elm, clkI = syncNode
            if isinstance(elm, ArchElementFsm):
                stWrite: HlsNetNodeFsmStateWrite = elm.connections[clkI].fsmStateWriteNode
                for i in stWrite._inputs:
                    self.collectFromInput(syncNode, i)

    def pruneAggegatePortsInSyncNodes(self):
        """
        There may be HlsNetNodeAggregatePortOut which are driven directly from some primary input (in same time).
        Such nodes should not be extracted as it would be pointless and they can be directly
        used to export the value.
        :note: Such nodes would would cause a creation of new ports for link to new parentElm and back and also from
        new parentElm back to itself.
        """
        toRm = set()
        for item in self.nodes:
            n, clkI = item
            if isinstance(n, HlsNetNodeAggregatePortOut):
                dep = n.dependsOn[0]
                if (dep, (dep.obj.parent, clkI)) in self.primaryInputs:
                    toRm.add(item)
        if toRm:
            self.nodes[:] = (item for item in self.nodes if item not in toRm)

