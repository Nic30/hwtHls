from typing import Dict, List, Optional

from hwtHls.architecture.analysis.handshakeSCCs import ReadOrWriteType, \
    AllIOsOfSyncNode, TimeOffsetOrderedIoItem
from hwtHls.architecture.analysis.nodeParentSyncNode import ArchSyncNodeTy
from hwtHls.netlist.abc.abcCpp import Abc_Obj_t, Abc_Aig_t
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.nodes.archElementFsm import ArchElementFsm
from hwtHls.architecture.connectionsOfStage import ConnectionsOfStage
from hwtHls.netlist.nodes.archElementPipeline import ArchElementPipeline
from hwtHls.netlist.nodes.archElement import ArchElement


class FLAG_FLUSH_TOKEN_AVAILABLE:
    """
    A class which is used as a constant for output from flush lock circuit which is generated during lowering. 
    """
    pass


class FLAG_FLUSH_TOKEN_ACQUIRE:
    """
    A class which is used as a constant for flag which activates acquire flush token for a node.
    
    :note: there is no FLAG_FLUSH_TOKEN_RELEASE because it always equals to parent sync node ack
    """
    pass


class SyncLogicResolverFlushing():
    """
    This class is used to construct flushing logic for writes. Write can flush if all input data/flags
    are valid and the parent node is stalling.
    :note: This is no a normal pipeline flushing. It is used to assert original program store order.
    
    
    :ivar _dataValidForIO: transitive validity flag for each io
    """

    def __init__(self):
        self._dataValidForIO: Dict[ReadOrWriteType, Abc_Obj_t]
        self._allFlushableWrites: List[TimeOffsetOrderedIoItem] = []

    def getIsNotFlushedFlag(self,
                            syncLogicResolver: "SyncLogicResolver",
                            syncNode: ArchSyncNodeTy,
                            w: HlsNetNodeWrite):
        return syncLogicResolver.toAbc.translationCache[((w, FLAG_FLUSH_TOKEN_AVAILABLE), syncNode[1])]
        # return self._writeFlushTokens[w].associatedRead.getValidNB()

    def getMayFlushCondition(self, syncLogicResolver: "SyncLogicResolver",
                             syncNode: ArchSyncNodeTy,
                             w: HlsNetNodeWrite):
        """
        :return: an ABC expression which is 1 if node is not flushed and data dependencies allows for flushing
        """
        return syncLogicResolver.toAbc.translationCache[((w, FLAG_FLUSH_TOKEN_ACQUIRE), syncNode[1])]

    def abcDeclareInputsForFlushTokens(self, syncLogicResolver: "SyncLogicResolver"):
        """
        Create a register (HlsNetNodeRead/WriteBackedge) in parent for each write which will used flushing. 
        """
        allSccIOs: AllIOsOfSyncNode = syncLogicResolver.allSccIOs
        primaryInputs = syncLogicResolver.syncLogicSearch.primaryInputs
        for item in allSccIOs:
            (_, ioNode, syncNode, ioTy) = item
            ioNode: HlsNetNodeExplicitSync
            syncNode: ArchSyncNodeTy
            # clkIndex = syncNode[1]
            ioTy: ReadOrWriteType
            if not ioTy.isRead() and ioNode._isFlushable:
                cacheKey = (ioNode, FLAG_FLUSH_TOKEN_AVAILABLE)
                primaryInputs.append((cacheKey, syncNode))
                syncLogicResolver._onAbcAddPrimaryInput(cacheKey, syncNode, name=f"n{ioNode._id}_flushToken")
                self._allFlushableWrites.append(item)

    def _getValidOfSyncNodeImplicitInputs(self, syncLogicResolver: "SyncLogicResolver", aig: Abc_Aig_t, elm: ArchElement, clkI: int) -> Optional[Abc_Obj_t]:
        if isinstance(elm, ArchElementFsm):
            con: ConnectionsOfStage = elm.connections[clkI]
            assert con is not None, (elm, clkI)
            return syncLogicResolver.toAbc._translate(aig, (con.fsmStateEnNode._outputs[0], clkI))
        elif isinstance(elm, ArchElementPipeline) and not elm.isBeginStage(clkI):
            con: ConnectionsOfStage = elm.connections[clkI]
            assert con is not None, (elm, clkI)
            assert con.pipelineSyncIn is not None, ("If this is not first stage, there should be pipelineSyncIn from previous stage", elm, clkI)
            return syncLogicResolver.toAbc._translate(aig, (con.pipelineSyncIn.getValidNB(), clkI))
        else:
            return None

    # def _translateIoNodeAckForFlushing(self,
    #                                   syncLogicResolver: "SyncLogicResolver",
    #                                   aig: Abc_Aig_t,
    #                                   ioNode: Union[HlsNetNodeRead, HlsNetNodeWrite],
    #                                   syncNode: ArchSyncNodeTy,
    #                                   useAckFromOtherIoSide: bool):
    #    """
    #    :ivar syncNode: sync node where ioNode is
    #    """
    #    elm, clkI = syncNode
    #    en = self._getValidOfSyncNodeImplicitInputs(syncLogicResolver, aig, elm, clkI)
    #    if useAckFromOtherIoSide:
    #        rtlEn = None
    #        if isinstance(ioNode, HlsNetNodeRead):
    #            if ioNode._rtlUseValid:
    #                rtlEn = ioNode.getValidNB()
    #        else:
    #            if ioNode._rtlUseReady:
    #                rtlEn = ioNode.getReadyNB()
    #
    #
    #        if rtlEn is not None:
    #            if isinstance(rtlEn, HlsNetNodeOut):
    #                rtlEn = syncLogicResolver._translate(aig, (rtlEn, syncNode))
    #            en = aig.And(en, rtlEn)
    #
    #    ec = ioNode.getExtraCondDriver()
    #    sw = ioNode.getSkipWhenDriver()
    #    if ec is not None:
    #        _ec = self._translateWithoutHsSCCEnable(syncNode, ec)
    #
    #    if sw is not None:
    #        _sw = self._translateWithoutHsSCCEnable(syncNode, sw)
    #
    #    if ec is not None and sw is not None:
    #        en = aig.And(en, aig.And(_ec, aig.Not(_sw)))
    #    elif ec is not None:
    #        en = aig.And(en, _ec)
    #    elif sw is not None:
    #        en = aig.And(en, aig.Not(_sw))
    #    return en

    # def _translateWithoutHsSCCEnable(self, syncNode: ArchSyncNodeTy, o: HlsNetNodeOut):
    #    """
    #    If o is defined in previous clock return it as is.
    #    Else translate the expression and use :meth:`SyncLogicResolverFlushing._translateIoNodeAckForFlushing`
    #    for every ioNode readyNB/ready/validNB/valid port.
    #    """
    #    raise NotImplementedError()

    def constructFlushTokenAcquireFlags(self, syncLogicResolver: "SyncLogicResolver", aig: Abc_Aig_t):
        """
        The token behaves as a lock. If available, the write may flush while consuming token.
        The token is returned on ack from parent sync node.
        Token itself will later be implemented as a 1b FF in channel sync logic.
        It will correspond to full of a 1 item buffer and it will be initialized to 1.
        """
        net = syncLogicResolver.toAbc.net
        translationCache = syncLogicResolver.toAbc.translationCache
        ioMap = syncLogicResolver.ioMap
        outputsFromAbcNet = syncLogicResolver.outputsFromAbcNet
        inToOutConnections = syncLogicResolver.inToOutConnections
        for (_, w, syncNode, _) in self._allFlushableWrites:
            elm, clkI = syncNode
            w: HlsNetNodeWrite
            abcI = net.CreatePi()
            abcO = net.CreatePo()
            name = f"n{w._id:d}_flush"
            abcI.AssignName(f"pi{abcI.Id:d}_{name:s}", "")
            abcO.AssignName(f"po{abcO.Id:d}_{name:s}", "")

            tranCacheKey = ((w, FLAG_FLUSH_TOKEN_ACQUIRE), clkI)
            translationCache[tranCacheKey] = abcI
            inToOutConnections[abcI] = abcO
            ioMap[abcO.Name()] = (w, FLAG_FLUSH_TOKEN_ACQUIRE)  # this is just tmp variable
            outputsFromAbcNet.add(abcO)
            
            mayFlush = syncLogicResolver._translateIOEnExpr(aig, syncNode, w, andWithParentEn=False)
            assert mayFlush is not None, w
            en = self._getValidOfSyncNodeImplicitInputs(syncLogicResolver, aig, elm, clkI)
            if en is not None:
                mayFlush = aig.And(en, mayFlush)
            if w._rtlUseReady:
                rtlAck = syncLogicResolver.toAbc._translate(aig, (w.getReadyNB(), clkI))
                mayFlush = aig.And(mayFlush, rtlAck)

            abcO.AddFanin(mayFlush)

            # ec = ioNode.getExtraCondDriver()
            # sw = ioNode.getSkipWhenDriver()
            # if ec is not None:
            #    _ec = self._translateWithoutHsSCCEnable(syncNode, ec)
            #
            # if sw is not None:
            #    _sw = self._translateWithoutHsSCCEnable(syncNode, sw)
            #
            # if ec is not None and sw is not None:
            #    en = aig.And(en, aig.And(_ec, aig.Not(_sw)))
            # elif ec is not None:

            # extraCond/skipWhen conditions should already contain required "and" with validity flag of its source
            # however there is an exception for HlsNetNodeFsmStateEn
            # this flag must be anded now

            # follow recursively and expand valid flag of every channel in this SCC
            # with a value build from channel flags
            # Do not cross primary inputs as it is expected that the channel valid is not used before it

            # # each data predecessor in extraCond/skipWhen
            # # if it is a blocking read append (valid && extraCond) || skipWhen
            # # if it is a non-blocking read ignore it as

            # raise NotImplementedError(ioNode)
