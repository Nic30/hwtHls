from hwtHls.architecture.analysis.handshakeSCCs import HlsAndRtlNetlistAnalysisPassHandshakeSCC, \
    ReadOrWriteType
from hwtHls.architecture.analysis.hlsArchAnalysisPass import HlsArchAnalysisPass
from hwtHls.netlist.nodes.write import HlsNetNodeWrite


class HlsAndRtlNetlistAnalysisPassSyncNodeFlushing(HlsArchAnalysisPass):
    """
    Detect which write nodes in ArchSyncNode are subject to flushing.
    
    Flushing is required primarily to avoid deadlock and to remove write order constraints
    added by scheduler :ref:`_figflushing`.
    
    This analysis makes sure of 2 things:
    
    * That the writes may finish in original code order even if they were
    scheduled in the same clock cycle window and some of them are not ready which would otherwise
    cause all writes in same clock window to stall.
    
    * That the cycles in internal channels do not deadlock if there is some optional communication with them.
    
    .. _figflushing:
    
    .. figure:: _static/syncLowering_pipeline_flushing.png
    
       Two cases when write data flushing is required
    
    :note: The result of this analysis is value of :attr:`HlsNetNodeWrite._isFlushable` flag on every :class:`HlsNetNodeWrite` instance
    """

    def runOnHlsNetlistImpl(self, netlist:"HlsNetlistCtx"):
        hsSccs: HlsAndRtlNetlistAnalysisPassHandshakeSCC = netlist.getAnalysis(HlsAndRtlNetlistAnalysisPassHandshakeSCC)

        # stalling: HlsAndRtlNetlistAnalysisPassSyncNodeStallling = netlist.getAnalysis(HlsAndRtlNetlistAnalysisPassSyncNodeStallling)
        self._detectFlushing(hsSccs)

    # @classmethod
    # def _collectFlushingGraphComponent(cls,
    #                                   nodeChannels: ArchSyncNodeIoDict,
    #                                   ioNodeToParentSyncNode: Dict[Union[HlsNetNodeReadAnyChannel, HlsNetNodeWriteAnyChannel], ArchSyncNodeTy],
    #                                   syncNode: ArchSyncNodeTy):
    #    """
    #    Collect all sync nodes which are connected with channel which has the source which may stall.
    #    :note: Channels of this type always use RTL valid signal.
    #    """
    #    # we do not need to discover components of flushing because
    #    # the flushing is propagated trough the valid,
    #    # only place where this is needed is the HsSCC
    #    toSearch = [syncNode, ]
    #    syncGraphComponent: SetList[ArchSyncNodeTy] = SetList(toSearch)
    #    while toSearch:
    #        n = toSearch.pop()
    #        chReads, chWrites = nodeChannels[n]
    #        for w, r in chain(
    #                ((r.associatedWrite, r) for r in chReads),
    #                ((w, w.associatedRead) for w in chWrites)):
    #            if w._rtlUserValid or r._rtlUseValid:
    #                sucNode = ioNodeToParentSyncNode[w]
    #                if sucNode[1] == n[1]:
    #                    # if they are in same clock window
    #                    if syncGraphComponent.append(sucNode):
    #                        toSearch.append(sucNode)
    #
    #    return syncGraphComponent
    @classmethod
    def _detectFlushing(cls, hsSccs: HlsAndRtlNetlistAnalysisPassHandshakeSCC):
        # divide sync node graph to components of nodes which are in the same clock window and are connected
        # by channel where source can stall (has valid)
        # :note: it does not matter if dst can stall or not (has ready) because flushing
        # is required when src node can partially stall

        # collect all IO in component
        for _, allIOs in hsSccs.sccs:
            # Flushing is required for:
            #  * forward edges if there is a triangle in "CFG" in a single clock window
            #    and right side is a loop and jump back to common successor does not happen immediately
            #    In this case write to section with loop must be flushable because loop output is not provided immediately
            #    and common successor would block because of it
            # * Write which has all inputs available but there is a possibility that something else stalls parent node.

            # Obscurities:
            # * write may be also flushed if there are some stalling inputs which are not used by this out
            # * flushing may change total order of IO operations, this is problem as it may lead to a deadlock
            # * Loops are translated in a way where last iteration also loads new data for next iteration
            #   in this situation all writes are requiring flush

            # Write flushing makes sense in situation when
            #  * there are multiple IO operations potentially causing stall of parent node
            #  * this output does not depend on all other nodes all the time
            # write do not need flushing if:
            #  * src can not stall (_rtlUseValid=False)
            #  * or all IOs scheduled after can be stalled by external means
            externalStallSourceSeen = False
            ioNodesInSameTime = []
            lastIoNodeTime = None
            for (ioNodeTime, ioNode, _, ioTy) in reversed(allIOs):
                # :note: some ioNodes may be scheduled to a same time
                #        in this case stalling of on may be source of stalling for all others
                isWrite = ioTy == ReadOrWriteType.CHANNEL_W or ioTy == ReadOrWriteType.W
                if isWrite:
                    isExternalStallCause = ioNode._rtlUseReady
                else:
                    isExternalStallCause = ioNode._rtlUseValid

                if externalStallSourceSeen and isWrite:
                    ioNode: HlsNetNodeWrite
                    if ioNode._mayBecomeFlushable and ioNode._rtlUseValid:
                        ioNode.setFlushable()

                if lastIoNodeTime != ioNodeTime:
                    lastIoNodeTime = ioNodeTime
                    ioNodesInSameTime.clear()
                

                if isExternalStallCause and not externalStallSourceSeen and ioNodesInSameTime:
                    # it was just found that this node may cause stall for nodes in same time
                    for _ioNode in ioNodesInSameTime:
                        _ioNode: HlsNetNodeWrite
                        if _ioNode._mayBecomeFlushable and _ioNode._rtlUseValid:
                            _ioNode.setFlushable()
                    
                if isWrite:
                    ioNodesInSameTime.append(ioNode)
                    
                externalStallSourceSeen |= isExternalStallCause
