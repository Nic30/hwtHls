from typing import Set, Dict, Tuple, Literal, List, Callable, Union

from hwt.pyUtils.setList import SetList
from hwtHls.architecture.analysis.nodeParentSyncNode import ArchSyncNodeTy
from hwtHls.architecture.transformation._syncLowering.syncLogicResolverFlushing import FLAG_FLUSH_TOKEN_AVAILABLE, \
    FLAG_FLUSH_TOKEN_ACQUIRE
from hwtHls.architecture.transformation._syncLowering.syncLogicSearcher import SyncLogicSearcher
from hwtHls.architecture.transformation.utils.syncUtils import createBackedgeInClkWindow
from hwtHls.architecture.transformation.utils.termPropagationContext import ArchElementTermPropagationCtx, \
    HlsNetNodeAggregatePortIn_getInput, ArchSyncNodeTerm, \
    importPortToArchElement
from hwtHls.netlist.abc.abcCpp import Abc_Obj_t
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.hdlTypeVoid import HVoidData
from hwtHls.netlist.nodes.aggregatePorts import HlsNetNodeAggregatePortIn, \
    HlsNetNodeAggregatePortOut
from hwtHls.netlist.nodes.archElementNoImplicitSync import ArchElementNoImplicitSync
from hwtHls.netlist.nodes.backedge import HlsNetNodeWriteBackedge
from hwtHls.netlist.nodes.fsmStateEn import HlsNetNodeStageAck
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn
from hwtHls.netlist.nodes.schedulableNode import SchedTime
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.transformation.simplifyExpr.rehash import _ExprRehasher
from hwtHls.netlist.scheduler.clk_math import endOfClkWindow


HlsNetOutToAbcOutMap_t = Dict[Union[HlsNetNodeOut,
                                    Tuple[HlsNetNode, Literal[FLAG_FLUSH_TOKEN_AVAILABLE, FLAG_FLUSH_TOKEN_ACQUIRE]]],
                              Abc_Obj_t]


class SyncLogicExtractor():
    """
    This class is responsible for extraction of :class:`HlsNetlistCtx` subnet to
    specified parentElm. It handles construction of :class:`HlsNetNodeAggregatePortIn`/:class:`HlsNetNodeAggregatePortout`
    ports and move of selected nodes.

    Subnet extraction problems:
    * if subnet is moved :class:`HlsNetlistBuilder` cache needs to be recomputed
    * registers are implicitly placed on clock window boundaries.
      * this is beneficial because checks needs to check just :class:`HlsNetNodeOut` objects and no not need
        to look trough all potential registers
      * This is problematic because if something is extracted and it is used in later clock windows,
        it is necessary to create port back to original place just before clock window boundary.
        So the register for this value is still created.
        This generates a name alias for a value. Which is problem because the value may cross multiple clock windows
        and each will require new ports and all of them will need to be mapped to original port.
        This may also result in intensive port reconnection (which takes time).

    .. figure:: _static/syncLowering_extractor_example0.png
    
       Example of extraction of port which is used in extracted, non-extracted logic and later clock cycles
    
    :ivar _newPrimaryOutputs: a list of inputs to HlsNetNodeAggreagatePortOut in new element
        which are prepared to propagate primaryOutput value from new element where circuit was extracted into 
    :ivar _primaryOutUpdateDict: dictionary mapping outputs to its new output of input port in "parent"
    """

    def __init__(self, syncLogicSearch: SyncLogicSearcher,
                 parentElm: ArchElementNoImplicitSync,
                 termPropagationCtx: ArchElementTermPropagationCtx,
                 clkPeriod: SchedTime,
                 scheduleDefault: Callable[[ArchSyncNodeTy, HlsNetNodeOut], None]):
        self.syncLogicSearch = syncLogicSearch
        self.syncLogicNodes = syncLogicSearch.nodes
        self.parentElm = parentElm
        self.termPropagationCtx = termPropagationCtx
        self.clkPeriod = clkPeriod
        self._newPrimaryOutputs: List[HlsNetNodeIn] = []
        self._primaryOutUpdateDict: Dict[HlsNetNodeOut, HlsNetNodeOut] = {}
        self._writeFlushTokens: Dict[HlsNetNodeWrite, HlsNetNodeWriteBackedge] = {}
        self._stageAckToAllWriteFlushTokens: Dict[HlsNetNodeStageAck, List[HlsNetNodeWriteBackedge]] = {}
        self._scheduleDefault = scheduleDefault

    def _replaceAllExtractedUsesInClkWindow(self,
                                            o: HlsNetNodeOut,
                                            clkIndex: int,
                                            clkPeriod: SchedTime,
                                            newO: HlsNetNodeOut):
        """
        If o has no special persistence settings this function replaces only
        uses in this clock. If the will be persistenceRanges items. Take them in account
        and replace all uses covered by it. 
        """
        _, lastPersistentClkI  = SyncLogicSearcher._getEarliestTimeIfValueIsPersistent(o, (o.obj.parent, clkIndex))
        clkWindowBegin = clkIndex * clkPeriod
        clkWindowEnd = endOfClkWindow(lastPersistentClkI, clkPeriod)
        for u in tuple(o.obj.usedBy[o.out_i]):
            uObj = u.obj
            t = u.obj.scheduledIn[u.in_i]
            if clkWindowBegin <= t and t < clkWindowEnd and\
                    (uObj, t // clkPeriod) in self.syncLogicNodes:
                u.disconnectFromHlsOut(o)
                newO.connectHlsIn(u, checkParent=False)  # can not check parent because some nodes may not yet be transfered

    @staticmethod
    def _reconstructNetlistBuilderOperatorCache(parent: ArchElementNoImplicitSync):
        builder: HlsNetlistBuilder = parent.builder
        # update builder operatorCache so it reuses nodes
        builder.operatorCache.clear()

        rehasher = _ExprRehasher(SetList(), builder, set())
        rehasher.rehashNodes(parent.subNodes)
        if builder._removedNodes:
            parent.filterNodesUsingRemovedSet(recursive=False)

    def _extractHlsNetNodeAggregatePortIn(self, n: HlsNetNodeAggregatePortIn,
                                          clkIndex: int,
                                          movedOrRemovedSyncLogicNodes: Set[HlsNetNode]):
        """
        Extract :class:`HlsNetNodeAggregatePortIn` to "parentSyncNode" possibly using value driving it or cloning this port
        to avoid obfuscation by redundant hierarchy ports.
        :note: HlsNetNodeAggregatePortIn object is never moved is is cloned.
        """
        # if this is not defined in the same clock when it is exported
        if n.scheduledZero // self.clkPeriod != clkIndex:
            return None  # can not be extracted as a port in this clock, because there is a register before use
            # a new out-in pair should be constructed instead

        # if connected out is also extracted it means that this connection does not need aggregate ports
        # however HlsNetNodeAggregatePortOut may have some other users as well as out of HlsNetNodeAggregatePortIn
        # if this is the case the port must be duplicated

        # if used only by extracted nodes it is possible to move this in to new parent
        # else it must be duplicated
        # while True:
        #    if not isinstance(dep.obj, HlsNetNodeAggregatePortIn):
        #        break
        syncLogicNodes = self.syncLogicNodes
        if not n.usedBy:
            # no uses -> this port does not need any update for users, new port will be created if this is used later,
            parentIn = n.parentIn
            dep = parentIn.obj.dependsOn[parentIn.in_i]
            parentIn.disconnectFromHlsOut(dep)
            movedOrRemovedSyncLogicNodes.add(n)
            self._primaryOutUpdateDict[n._outputs[0]] = dep
            return None
        else:

            dep = n.depOnOtherSide()
            isDrivenFromExtractedLogic = (dep.obj, clkIndex) not in syncLogicNodes
            if isDrivenFromExtractedLogic:
                # replace all extracted use with dep directly
                pass
            else:
                # create a new input node driven from same in dst parent element
                # reroute all replaced uses to it
                outerI, internO = self.parentElm._addInput(dep._dtype, n.name, n.scheduledZero)
                n.getDep().connectHlsIn(outerI, checkCycleFree=False)

                dep = internO
            
            assert len(n._outputs) == 1, n
            inpO = n._outputs[0]
            for user in tuple(n.usedBy[0]):
                uSyncNode = user.obj.getParentSyncNode()
                if uSyncNode not in syncLogicNodes or uSyncNode[1] != clkIndex:
                    # this is not extracted use, keep it as it is
                    continue

                user.disconnectFromHlsOut(inpO)
                dep.connectHlsIn(user, checkCycleFree=False)

            if not n.usedBy:
                parentIn = n.parentIn
                parentIn.disconnectFromHlsOut()
                movedOrRemovedSyncLogicNodes.add(n)

            self._primaryOutUpdateDict[inpO] = dep
            return dep.obj

    def _extractNewPort(self,
                        ioMap: Dict[str, HlsNetNodeOut],
                        hlsNetOutToAbcOut: HlsNetOutToAbcOutMap_t,
                        toAbcTranslationCache: Dict[Tuple[HlsNetNodeOut, int], Abc_Obj_t],
                        srcNode: ArchSyncNodeTy,
                        o: Tuple[HlsNetNodeWrite, Literal[FLAG_FLUSH_TOKEN_AVAILABLE]]):
        """
        part of :meth:`_extractSyncLogicNodesToNewElm` which is responsible for :class:`HlsNetNodeOut` which were generated
        newly generated and are not replacement of anything
        :see: :class:`FLAG_FLUSH_TOKEN_AVAILABLE`
        """
        if len(o) == 2 and o[1] == FLAG_FLUSH_TOKEN_AVAILABLE:
            w, _ = o
            w: HlsNetNodeWrite
            acquirePo = hlsNetOutToAbcOut[(w, FLAG_FLUSH_TOKEN_ACQUIRE)]
            acquireVal: Abc_Obj_t = next(acquirePo.IterFanin())
            parent = self.parentElm
            clkIndex = srcNode[1]
            abcI: Abc_Obj_t = toAbcTranslationCache[(o, clkIndex)]

            if acquireVal.IsConst() and acquirePo.FaninC0():
                # if FLAG_FLUSH_TOKEN_ACQUIRE == 0 this is useless and is replaced with 1
                ioMap[abcI.Name()] = None
                self._writeFlushTokens[w] = None
                return

            tokenR, tokenW = createBackedgeInClkWindow(parent, 0, f"n{w._id}_flushToken", HVoidData, channelInitValue=())

            ioMap[abcI.Name()] = tokenR.getValidNB()
            self._writeFlushTokens[w] = tokenW

            pSyncNode = w.getParentSyncNode()
            pSyncNodeAck = pSyncNode[0].connections[pSyncNode[1]].fsmStateAckNode
            assert pSyncNodeAck is not None, (srcNode)
            otherInSameStage = self._stageAckToAllWriteFlushTokens.get(pSyncNodeAck, None)
            if otherInSameStage is None:
                self._stageAckToAllWriteFlushTokens[pSyncNodeAck] = [tokenW, ]
            else:
                otherInSameStage.append(tokenW)
        else:
            raise  NotImplementedError(o)

    def _defineNewPortPairForPrimaryOutputs(self):
        """
        For each primary output of sync logic in ABC construct a port pair porting it from "parent" back
        to original sync node where it was and update non extracted uses to use it instead original
        port which is now part of extracted sync logic.
        """
        parentElm = self.parentElm
        termPropagationCtx = self.termPropagationCtx
        newPOs = self._newPrimaryOutputs
        clkPeriod = self.clkPeriod
        newOutputsSubstitutingOriginal: Dict[HlsNetNodeOut, HlsNetNodeOut] = {}
        # :attention: expects primaryOutputs to be sorted earlier first
        for (out, dstNode) in self.syncLogicSearch.primaryOutputs:
            out: HlsNetNodeOut
            name = out.getPrettyName(useParentName=False)
            _out, intern = parentElm._addOutput(out._dtype, name=out.getPrettyName(useParentName=False), time=0)
            # out.connectHlsIn(intern)
            newPOs.append(intern)
            k = ArchSyncNodeTerm(dstNode, _out, name)
            newO, _ = importPortToArchElement(_out, name, dstNode)
            termPropagationCtx.importedPorts[k] = newO
            defClkI = out.obj.scheduledOut[out.out_i] // clkPeriod
            dstClkI = dstNode[1]
            if defClkI == dstClkI:
                # newO should be used instead out in clock cycles after def in rest of the circuit (extracted sync logic should use out which is original out port)
                newOutputsSubstitutingOriginal[out] = newO

            builder = out.obj.getHlsNetlistBuilder()
            # replace all uses except the for nodes which will be extracted
            builder.replaceOutputIf(out, newO,
                                    lambda u: (u.obj, useClkI := u.obj.scheduledIn[u.in_i] // clkPeriod)
                                            not in self.syncLogicNodes or
                                            useClkI > dstClkI)
        return newOutputsSubstitutingOriginal

    def extractSyncLogicNodesToNewElm(self,
                                      ioMap: Dict[str, HlsNetNodeOut],
                                      hlsNetOutToAbcOut: HlsNetOutToAbcOutMap_t,
                                      toAbcTranslationCache: Dict[Tuple[HlsNetNodeOut, int], Abc_Obj_t],) -> Tuple[Dict[HlsNetNodeOut, HlsNetNodeOut], Set[HlsNetNodeOut]]:
        """
        Move subgraph selected by syncLogicSearch to a new element "parent"
        construct all ports moving data between original ArchElements and new ArchElement for sync logic
        """
        clkPeriod = self.clkPeriod
        syncLogicNodes = self.syncLogicNodes
        parentElm = self.parentElm
        termPropagationCtx = self.termPropagationCtx
        syncLogicSearch = self.syncLogicSearch
        newOutpustFromSrcElements: Set[HlsNetNodeOut] = set()
        primaryInputsReplacedByNegationOf = syncLogicSearch.primaryInputsReplacedByNegationOf
        primaryInputsReplacedByNegationList = []
        movedOrRemovedSyncLogicNodes: Set[HlsNetNode] = set()
        primaryOutUpdateDict: Dict[HlsNetNodeOut, HlsNetNodeOut] = self._primaryOutUpdateDict
        # sort to process earlier nodes first so if
        syncLogicSearch.primaryOutputs.sort(key=lambda item: item[1][1])
        syncLogicSearch.primaryInputs.sort(key=lambda item: item[1][1])

        newOutputsSubstitutingOriginal = self._defineNewPortPairForPrimaryOutputs()
        # [fixme] problem is that port is replaced for later cycles but code below does not reflect it
        # and works with old port and potentially adds new uses for it (export AggregatePortOut)
        # this results in use of original node which may be already extracted in new parent

        # propagate primary input value to parentElm
        for (o, srcNode) in syncLogicSearch.primaryInputs:
            if isinstance(o, tuple):
                self._extractNewPort(ioMap, hlsNetOutToAbcOut, toAbcTranslationCache, srcNode, o)

            else:
                o: HlsNetNodeOut
                originalO = o
                clkIndex = srcNode[1]
                oDefClkIndex = o.obj.scheduledZero // clkPeriod
                # if input is negation try use original value to avoid case with 2 registers 1st for normal and 2nd for negated value
                if clkIndex != oDefClkIndex:
                    assert clkIndex > oDefClkIndex, o
                    _o = newOutputsSubstitutingOriginal.get(o, o)
                else:
                    _o = o

                unNegated = primaryInputsReplacedByNegationOf.get((o, clkIndex), None)
                if unNegated is not None:
                    negatedAbcI: Abc_Obj_t = toAbcTranslationCache[(o, clkIndex)]
                    assert negatedAbcI.IsComplement(), negatedAbcI
                    assert negatedAbcI.IsPi(), negatedAbcI
                    primaryInputsReplacedByNegationList.append((_o, srcNode, negatedAbcI))
                    continue
                o = _o
                
                if isinstance(o.obj, HlsNetNodeAggregatePortIn):
                    if self._extractHlsNetNodeAggregatePortIn(
                            o.obj, clkIndex,
                            movedOrRemovedSyncLogicNodes):
                        continue
                    # else export it as any other port
                elif isinstance(o.obj, HlsNetNodeAggregatePortOut):
                    raise NotImplementedError(o.obj)

                # oClkIndex = o.obj.scheduledZero // clkPeriod
                # if clkIndex != oClkIndex:
                #    assert (o.obj, oClkIndex) not in syncLogicSearch.nodes, (
                #        "Output is also extracted, but there is register between o and this use,"
                #        " o should already be replaced by AggregatePortIn from new element", o)
                # add link from source ArchElement to "parent" with sync logic
                if isinstance(o.obj, HlsNetNodeAggregatePortIn):
                    name = f"{o.obj.name:}_clk{clkIndex:d}"
                else:
                    name = o.getPrettyName(useParentName=False)
                newO = termPropagationCtx.propagate(srcNode, o, name =name)
                assert newO.obj.parent is parentElm, (newO, o, newO.obj.parent, parentElm)
                newOutpustFromSrcElements.add(HlsNetNodeAggregatePortIn_getInput(newO))
                abcI = toAbcTranslationCache[(originalO, clkIndex)]
                ioMap[abcI.Name()] = newO

                assert isinstance(newO, HlsNetNodeOut), newO
                if o.obj.scheduledZero // clkPeriod == clkIndex:
                    primaryOutUpdateDict[o] = newO
                self._replaceAllExtractedUsesInClkWindow(o, clkIndex, clkPeriod, newO)

        parentBuilder = parentElm.builder
        for (o, srcNode, negatedAbcI) in primaryInputsReplacedByNegationList:
            # negatedAbcI is a complement of PI which will be used, there the "not" is constructed
            unNegatedNewO = ioMap[negatedAbcI.Name()]
            assert unNegatedNewO.obj.parent is parentElm, (o, unNegatedNewO, unNegatedNewO.obj.parent, parentElm)
            defClkIndex = o.obj.scheduledOut[o.out_i] // clkPeriod
            clkIndex = srcNode[1]
            
            #if defClkIndex != clkIndex:
            #    o = newOutputsSubstitutingOriginal.get(o, o)

            newO = parentBuilder.buildNot(unNegatedNewO)
            #defClkIndex = o.obj.scheduledOut[o.out_i] // clkPeriod
            if defClkIndex == clkIndex:
                primaryOutUpdateDict[o] = newO
            syncLogicNodes.append((newO.obj, srcNode[1]))

            self._replaceAllExtractedUsesInClkWindow(o, clkIndex, clkPeriod, newO)

        # move all nodes selected as a sync logic into new parent element
        newPos = set(primaryOutUpdateDict.values())
        for (n, clkIndex) in syncLogicNodes:
            # HlsNetNodeAggregatePortIn and HlsNetNodeAggregatePortOut are not moved but are copied instead
            if isinstance(n, HlsNetNodeAggregatePortIn):
                n: HlsNetNodeAggregatePortIn
                self._extractHlsNetNodeAggregatePortIn(n, clkIndex,
                                                       movedOrRemovedSyncLogicNodes)

            elif isinstance(n, HlsNetNodeAggregatePortOut):
                # :note: dep is not supposed to be primary input defined in srcNode
                #        because it would make this port just export of it.
                #        Such case would cause a new ports for link to new parentElm and back and also from
                #        new parentElm back to it
                dep = n.dependsOn[0]
                assert (dep.obj, clkIndex) in syncLogicNodes or dep in newPos, (
                    "There is no point in extracting this output if it is not driven from extracted logic",
                    n, dep.obj)
                # create a new output in new parent
                outerO, internO = parentElm._addOutput(dep._dtype, n.name, n.scheduledZero)
                # replace output "n" and disconnect it and remove it
                n.getHlsNetlistBuilder().replaceOutput(n.parentOut, outerO, False, checkCycleFree=False)
                n._inputs[0].disconnectFromHlsOut(dep)
                movedOrRemovedSyncLogicNodes.add(n)

                # connect new out on internal side
                dep.connectHlsIn(internO, checkCycleFree=False)

            else:
                originalParent = n.parent
                n.getHlsNetlistBuilder().unregisterNode(n)
                n.parent = None
                parentElm._addNodeIntoScheduled(0, n, allowNewClockWindow=True)
                movedOrRemovedSyncLogicNodes.add(n)

                #beginOfNextClk = (clkIndex + 1) * clkPeriod
                #for nOut, uses in zip(n._outputs, n.usedBy):
                #    syncLogicSearch._getEarliestTimeIfValueIsPersistent(o, syncNode)
                #    for u in uses:
                #        if u.obj.scheduledIn[u.in_i] >= beginOfNextClk:
                #            assert u.obj.parent is originalParent, ("This may be case only for original nodes or new HlsNetNodeAggregatePortOut", nOut, u)
                #            # port is used in next clock window, this must be also primary output
                #            # a port back to original element must be constructed
                #            assert (nOut, (originalParent, clkIndex)) in syncLogicSearch.primaryOutputs, (
                #                "This must be primary output, because it leads to a register, which is then used", nOut, clkIndex, u)
                #
        return movedOrRemovedSyncLogicNodes

    def extractSyncLogicNodesToNewElm_primaryOutputs(self):
        parent = self.parentElm
        primaryOutUpdateDict = self._primaryOutUpdateDict

        assert len(self.syncLogicSearch.primaryOutputs) == len(self._newPrimaryOutputs)
        for (o, dstNode), newOInput in zip(self.syncLogicSearch.primaryOutputs, self._newPrimaryOutputs):
            o: HlsNetNodeOut
            newOInput: HlsNetNodeIn
            origO = o
            # oObj = o.obj
            o = primaryOutUpdateDict.get(o, o)

            assert not o.obj._isMarkedRemoved, (o, origO)
            if o.obj not in parent.subNodes:
                raise NotImplementedError("Value originates from a different node (than parent)",)

            if o.obj.scheduledIn is None:
                self._scheduleDefault((parent, 0), o)
            o.connectHlsIn(newOInput, checkCycleFree=False)
            # add link from "parent" to user ArchElement
            # newO = termPropagationCtx.propagateFromDstElm(
            #    dstNode, o, origO.getPrettyName(useParentName=False),
            # )
            #
            # oObj.getHlsNetlistBuilder().replaceOutputIf(origO, newO,
            #                                            lambda u: u not in newOutpustFromSrcElements and\
            #                                               u.obj not in parent.subNodes)

            # iElmPort: HlsNetNodeAggregatePortIn = newO.obj
            # elm = iElmPort.parentIn.obj
            # assert elm is dstNode[0]
            # srcElmPort = elm.dependsOn[iElmPort.parentIn.in_i]
            # srcElmPortInside = srcElmPort.obj._outputsInside[srcElmPort.out_i]
            # srcElmPortInsideIn = srcElmPortInside._inputs[0]
            # #primaryOutputs.append(srcElmPortInsideIn)
            # # disconnect because it will be replaced after resolved from ABC net
            # srcElmPortInsideIn.disconnectFromHlsOut(srcElmPortInside.depensOn[0], )
