from typing import Dict, List, Union

from hwt.pyUtils.setList import SetList
from hwtHls.architecture.analysis.channelGraph import HlsArchAnalysisPassChannelGraph, \
    ArchSyncNodeIoDict, ArchSyncNodeTy
from hwtHls.architecture.analysis.hlsArchAnalysisPass import HlsArchAnalysisPass
from hwtHls.netlist.nodes.backedge import HlsNetNodeWriteBackedge
from hwtHls.netlist.nodes.loopChannelGroup import HlsNetNodeWriteAnyChannel, \
    HlsNetNodeReadAnyChannel
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.nodes.archElementFsm import ArchElementFsm


class ArchSyncNodeStallingMeta():
    """
    Object of this class represents an information about stalling of :see:`ArchSyncNodeTy`.
    
    :note: If the inputCanStall=True it means that the input to this node may stall, thus valid rtl signal is required.
        inputCanStall and outputCanStall are separate flags because we need the direction of stalling
        so we can later resolve if we should use ready/valid RTL signal.
    """
    __slots__ = ["inputCanStall", "outputCanStall"]

    def __init__(self, inputCanStall=False, outputCanStall=False):
        self.inputCanStall = inputCanStall
        self.outputCanStall = outputCanStall

    def __bool__(self):
        return self.inputCanStall or self.outputCanStall

    def __repr__(self):
        return (f"<{self.__class__.__name__:s}{' inputCanStall' if self.inputCanStall else '' }"
                f"{' outputCanStall' if self.outputCanStall else '' }>")


class HlsArchAnalysisPassSyncNodeStallling(HlsArchAnalysisPass):
    """
    Detect which nodes in architecture are subject to stalling.
    
    :note: Primary source of stalling is synchronization of IO and channel communication.
    """

    def __init__(self):
        super(HlsArchAnalysisPassSyncNodeStallling, self).__init__()
        self.nodeCanStall: Dict[ArchSyncNodeTy, ArchSyncNodeStallingMeta] = {}

    def runOnHlsNetlistImpl(self, netlist:"HlsNetlistCtx"):
        channels = netlist.getAnalysis(HlsArchAnalysisPassChannelGraph)
        self.nodeCanStall = self.detectStalling(channels.nodes, channels.nodeChannels,
                                                channels.channelPortToParentSyncNode, channels.nodeIo)

    @classmethod
    def detectStalling(cls, nodes: List[ArchSyncNodeTy],
                       nodeChannels: ArchSyncNodeIoDict,
                       channelPortToParentSyncNode: Dict[Union[HlsNetNodeReadAnyChannel, HlsNetNodeWriteAnyChannel], ArchSyncNodeTy],
                       nodeIo: ArchSyncNodeIoDict):
        """
        Detect stalling in pipeline from IO of the circuit.
        
        If node can stall all input channels must have _rtlUseReady=True and outputs _rtlUseValid=True.
        There are several exceptions to this rule caused by channel buffer capacity. See code bellow.
        
        :note: Information about stalling is required for resolving which type of sync should be used by internal channels. 
        """
        nodeCanStall: Dict[ArchSyncNodeTy, ArchSyncNodeStallingMeta] = {}

        # for each node detect if it can stall due IO
        for n in nodes:
            inputCanStall = False
            outputCanStall = False
            rList, wList = nodeIo[n]
            # input read can stall if it has valid rtl signal
            for r in rList:
                r: HlsNetNodeRead
                if r._rtlUseValid:
                    inputCanStall = True
                    break

            # output write can stall if it has ready rtl signal
            for w in wList:
                w: HlsNetNodeWrite
                if w._rtlUseReady:
                    outputCanStall = True
                    break

            rList, wList = nodeChannels[n]
            # channels can also be a source of stalling
            # * if the capacity of output channel is not sufficient
            # * if input channel has skipWhen or extraCond the node may stall this channel,
            #    which may result in output stalling of the write in other node

            # [todo] maybe handling of _isBlocking is missing

            # * if output channel has skipWhen or extraCond the node may stall this channel
            #    which may result in input stalling of the read in other node
            if not inputCanStall:
                for r in rList:
                    w: HlsNetNodeWriteAnyChannel = r.associatedWrite
                    if w.getSkipWhenDriver() is not None\
                            or w.getExtraCondDriver() is not None:
                        inputCanStall = True
                        break
                    elif len(w.channelInitValues) < w._getBufferCapacity():
                        inputCanStall = True
                        break
                    elif (isinstance(w, HlsNetNodeWriteBackedge) and
                                channelPortToParentSyncNode[r] != channelPortToParentSyncNode[w]):
                        inputCanStall = True
                        break
                    elif isinstance(channelPortToParentSyncNode[w][0], ArchElementFsm):
                        inputCanStall = True
                        break

            if not outputCanStall:
                for w in wList:
                    r: HlsNetNodeReadAnyChannel = w.associatedRead
                    if r.getSkipWhenDriver() is not None or r.getExtraCondDriver() is not None:
                        outputCanStall = True
                        break
                    elif len(w.channelInitValues) > w._getBufferCapacity():
                        outputCanStall = True
                        break
                    elif (isinstance(w, HlsNetNodeWriteBackedge) and
                                channelPortToParentSyncNode[r] != channelPortToParentSyncNode[w]):
                        outputCanStall = True
                        break
                    elif isinstance(channelPortToParentSyncNode[r][0], ArchElementFsm):
                        outputCanStall = True
                        break

            nodeCanStall[n] = ArchSyncNodeStallingMeta(inputCanStall, outputCanStall)

        cls.propagateStallingFlags(nodes, channelPortToParentSyncNode, nodeChannels, nodeCanStall)
        return nodeCanStall

    @classmethod
    def propagateStallingFlags(cls, nodes: List[ArchSyncNodeTy],
                               channelPortToParentSyncNode: Dict[Union[HlsNetNodeReadAnyChannel, HlsNetNodeWriteAnyChannel], ArchSyncNodeTy],
                               nodeChannels:ArchSyncNodeIoDict,
                               nodeCanStall: Dict[ArchSyncNodeTy, ArchSyncNodeStallingMeta]):
        # propagate this property over whole graph
        toSearch: SetList[ArchSyncNodeTy] = SetList(n for n in nodes if nodeCanStall[n])
        while toSearch:
            n = toSearch.pop()
            rList, wList = nodeChannels[n]  # channel ports for node
            canStall: ArchSyncNodeStallingMeta = nodeCanStall[n]
            if canStall.inputCanStall:
                # input to this node may stall -> all nodes reading from this node may have input stalled
                for w in wList:
                    w: HlsNetNodeWriteAnyChannel
                    other: ArchSyncNodeTy = channelPortToParentSyncNode[w.associatedRead]
                    otherCanStall: ArchSyncNodeStallingMeta = nodeCanStall[other]
                    # n w -> r other
                    if not otherCanStall.inputCanStall:
                        otherCanStall.inputCanStall = True
                        toSearch.append(other)

            if canStall.outputCanStall:
                # output from this node may stall -> all nodes writing to this node may have output stalled
                for r in rList:
                    r: HlsNetNodeReadAnyChannel
                    other: ArchSyncNodeTy = channelPortToParentSyncNode[r.associatedWrite]
                    otherCanStall: ArchSyncNodeStallingMeta = nodeCanStall[other]
                    # other w -> r n
                    if not otherCanStall.outputCanStall:
                        otherCanStall.outputCanStall = True
                        toSearch.append(other)

