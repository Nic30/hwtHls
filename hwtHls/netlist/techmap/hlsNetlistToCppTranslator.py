
from hwt.pyUtils.setList import SetList
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, HlsNetNodeOut
from hwtHls.netlist.nodes.schedulableNode import SchedTime
from hwtHls.netlist.techmap.techmap import HlsNetlistCtx as HlsNetlistCtxCpp, HlsNetNode as HlsNetNodeCpp


class HlsNetlistToCppTranslator():

    def __init__(self, normalizedClkPeriod: SchedTime, schedFFSetupTime: SchedTime):
        self.netlistCpp = HlsNetlistCtxCpp(normalizedClkPeriod, schedFFSetupTime)
        self.nodeMap: dict[HlsNetNode, HlsNetNodeCpp] = {}
        self.nodeOrdered: SetList[HlsNetNode] | None = None
        self.inputs: SetList[HlsNetNode] | None = None
        self.outputs: SetList[HlsNetNode] | None = None

    def translate(self, nodes: SetList[HlsNetNode], inputs: SetList[HlsNetNode], outputs: SetList[HlsNetNode],):
        net = self.netlistCpp
        nodeOrdered = self.nodeOrdered = nodes
        self.inputs = inputs
        self.outputs = outputs
        nodeMap = self.nodeMap
        for n in nodeOrdered:
            nCpp = net.createNode(len(n._inputs), len(n._outputs), id=n._id)
            self.copySchedulingPyToCppOfNode(n, nCpp)
            nodeMap[n] = nCpp

        for n in nodeOrdered:
            nCpp: HlsNetNodeCpp = nodeMap[n]
            # for i, dep in enumerate(n.dependsOn):
            #    iNode = dep.obj
            #    assert iNode in nodeOrdered, iNode
            #    if iNode in inputs:
            #        # primary input
            #        iNodeCpp: HlsNetNodeCpp = nodeMap.get(iNode)
            #        assert iNodeCpp is not None, iNode
            #        # # create a placeholder input node
            #        # iNodeCpp = net.createNode(len(iNode._inputs), len(iNode._outputs), id=iNode._id)
            #        # nodeMap[iNode] = iNodeCpp
            #        # nodeOrdered.append(iNode)
            #        # inputs.append(iNode)
            #
            #        # if iNode.scheduledZero is not None:
            #        #    iNodeCpp._setScheduleZeroTimeSingleClock(iNode.scheduledZero)
            #
            #        iNodeCpp._outputs[dep.out_i].connectHlsIn(nCpp._inputs[i])

            for (o, users) in zip(n._outputs, n.usedBy):
                o: HlsNetNodeOut
                oCpp = nCpp._outputs[o.out_i]
                for u in users:
                    u: HlsNetNodeIn
                    uNode = u.obj
                    uNodeCpp: HlsNetNodeCpp = nodeMap.get(uNode)
                    assert uNodeCpp is not None, uNode
                    # if uNodeCpp is None:
                    #    assert uNode not in self.outputs, uNode
                    #    # primary output
                    #    # create a placeholder output node
                    #    uNodeCpp = net.createNode(len(uNode._inputs), len(uNode._outputs), id=uNode._id)
                    #    nodeMap[uNode] = uNodeCpp
                    #    nodeOrdered.append(uNode)
                    #    self.outputs.append(uNode)
                    #    if uNode.scheduledZero is not None:
                    #        uNodeCpp._setScheduleZeroTimeSingleClock(uNode.scheduledZero)
                    #
                    oCpp.connectHlsIn(uNodeCpp._inputs[u.in_i])

    def copySchedulingPyToCppOfNode(self, n: HlsNetNode, nCpp: HlsNetNodeCpp):
        if n.scheduledZero is not None:
            nCpp.scheduledZero = n.scheduledZero
            nCpp.scheduledZeroMin = n.scheduledZeroMin
            nCpp.scheduledZeroMax = n.scheduledZeroMax
            if n.scheduledIn:
                nCpp.scheduledIn = n.scheduledIn
            if n.scheduledOut:
                nCpp.scheduledOut = n.scheduledOut
        if n.realization is not None:
            nCpp.isMulticlock = n.isMulticlock
            nCpp.scheduleMayBeInFFStoreTime = n.realization.isAllowedInFFStoreTime
            assert len(nCpp.inputWireDelay) == len(n.inputWireDelay)
            nCpp.inputWireDelay = n.inputWireDelay
            assert len(nCpp.inputClkTickOffset) == len(n.inputClkTickOffset)
            nCpp.inputClkTickOffset = n.inputClkTickOffset
            assert len(nCpp.outputWireDelay) == len(n.outputWireDelay)
            nCpp.outputWireDelay = n.outputWireDelay
            assert len(nCpp.outputClkTickOffset) == len(n.outputClkTickOffset)
            nCpp.outputClkTickOffset = n.outputClkTickOffset

    def copySchedulingPyToCpp(self):
        """
        Copy scheduling from python nodes to c++ nodes
        """
        nodeMap = self.nodeMap
        for n in self.nodeOrdered:
            nCpp: HlsNetNodeCpp = nodeMap[n]
            self.copySchedulingPyToCppOfNode(n, nCpp)

    def copySchedulingCppToPyOfNode(self, n: HlsNetNode, nCpp: HlsNetNodeCpp):
        # print("copySchedulingCppToPyOfNode", n._id)
        if n.realization is not None:
            assert len(nCpp.inputWireDelay) == len(n.inputWireDelay)
            assert len(nCpp.inputClkTickOffset) == len(n.inputClkTickOffset)
            assert len(nCpp.outputWireDelay) == len(n.outputWireDelay)
            assert len(nCpp.outputClkTickOffset) == len(n.outputClkTickOffset)
        assert nCpp.scheduledZero is not None, n
        n.scheduledZero = nCpp.scheduledZero
        n.scheduledIn = tuple(nCpp.scheduledIn)
        n.scheduledOut = tuple(nCpp.scheduledOut)
        n.inputWireDelay = tuple(nCpp.inputWireDelay)
        n.inputWireDelay = tuple(nCpp.inputWireDelay)
        n.outputWireDelay = tuple(nCpp.outputWireDelay)
        n.outputClkTickOffset = tuple(nCpp.outputClkTickOffset)

    def copySchedulingCppToPy(self):
        """
        copy scheduling from HlsNetNodeCpp back to HlsNetNode
        """
        nodeMap = self.nodeMap
        for n in self.nodeOrdered:
            nCpp = nodeMap[n]
            self.copySchedulingCppToPyOfNode(n, nCpp)

