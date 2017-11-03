from hwtHls.codeObjs import ReadOpPromise, HlsOperation, WriteOpPromise
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwt.synthesizer.interfaceLevel.unitImplHelpers import getSignalName
from hwtHls.hls import Hls


class TimeIndependentRtlResource():
    def __init__(self, signal: RtlSignal, time: int, hlsAllocator):
        self.timeOffset = time
        self.allocator = hlsAllocator
        self.valuesInTime = [signal, ]

    def get(self, time):
        """
        Get value of singal in specified time
        """
        index = time - self.timeOffset
        assert index >= 0
        try:
            return self.valuesInTime[index]
        except IndexError:
            pass
        # allocate registers to propagate value into next cycles
        sig = self.valuesInTime[0]
        prevReg = self.valuesInTime[-1]
        requestedRegCnt = index + 1
        actualTimesCnt = len(self.valuesInTime)
        name = getSignalName(sig)

        for i in range(actualTimesCnt, requestedRegCnt):
            reg = self.allocator._reg(name + "_delay_%d" % i,
                                      dtype=sig._dtype)
            reg(prevReg)
            self.valuesInTime.append(reg)
            prevReg = reg

        return reg


class HlsAllocator():
    """
    Convert virtual operation instances to real RTL code

    :ivar parentHls: parent HLS context for this allocator
    :ivar node2instance: dictionary {hls node: rtl instance}
    """

    def __init__(self, parentHls: Hls):
        self.parentHls = parentHls
        self.node2instance = {}
        # function to create register on RTL level
        self._reg = parentHls.parentUnit._reg

    def instantiateOperation(self, node: HlsOperation):
        """
        Instantiate operation on RTL level
        """
        operands = []
        for o in node.dependsOn:
            try:
                _o = self.node2instance[o]
            except KeyError:
                _o = o
            _o = _o.get(node.scheduledIn)
            operands.append(_o)

        return TimeIndependentRtlResource(node.operator._evalFn(*operands),
                                          node.scheduledIn, self)

    def inistanciateWrite(self, write: WriteOpPromise):
        """
        Instantiate write operation on RTL level
        """
        o = write.dependsOn[0]
        try:
            _o = self.node2instance[o]
        except KeyError:
            _o = o
        _o = _o.get(o.scheduledIn)

        return write.where(_o)

    def allocate(self):
        """
        Allocate scheduled circut in RTL
        """
        scheduler = self.parentHls.scheduler
        node2instance = self.node2instance

        for nodes in scheduler.schedulization:
            for node in nodes:
                # this is one level of nodes,
                # node can not be dependent on nodes behind in this list
                if isinstance(node, ReadOpPromise):
                    rtlNode = TimeIndependentRtlResource(node.getRtlDataSig(),
                                                         node.scheduledIn,
                                                         self)
                elif isinstance(node, WriteOpPromise):
                    self.inistanciateWrite(node)
                    continue
                else:
                    rtlNode = self.instantiateOperation(node)

                node2instance[node] = rtlNode
