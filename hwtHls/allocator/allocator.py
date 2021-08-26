from typing import Union, List

from hwt.code import If, SwitchLogic
from hwt.hdl.operatorDefs import AllOps
from hwt.synthesizer.interfaceLevel.unitImplHelpers import getSignalName
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.clk_math import start_clk, end_clk, epsilon
from hwtHls.codeOps import HlsRead, HlsOperation, HlsWrite, \
    HlsConst, HlsMux
from hwtHls.hlsPipeline import HlsPipeline
from hwt.hdl.statements.assignmentContainer import HdlAssignmentContainer


class TimeIndependentRtlResource():
    """
    Container of resource which manages access to resource
    in different times

    (dynamically generates register chains and synchronization
     to pass values to specified clk periods)
    """
    INVARIANT_TIME = "INVARIANT_TIME"
    # time constant, which means that item is not time dependent
    # and can be accessed any time

    def __init__(self, signal: RtlSignal,
                 time: Union[int, "TimeIndependentRtlResource.INVARIANT_TIME"],
                 hlsAllocator: "HlsAllocator"):
        """
        :param signal: signal with value in initial time
        :param time: number of clock form start when valid data appears on "signal"
            (constant INVARIANT_TIME is used if input signal is constant
             and does not require any registers and synchronizations)
        :param hlsAllocator: HlsAllocator instance to generate registers an synchronization logic

        :ivar valuesInTime: list (chain) of signals (register outputs) for clk periods specified by index
        """
        self.timeOffset = time
        self.allocator = hlsAllocator
        self.valuesInTime = [signal, ]

    def get(self, time):
        """
        Get value of signal in specified time (clk period)
        """

        # if time is first time in live of this value return original signal
        time += epsilon
        if self.timeOffset == self.INVARIANT_TIME or self.timeOffset == time:
            return self.valuesInTime[0]

        # else try to look up register for this signal in valuesInTime cache
        clk_period = self.allocator.parentHls.clk_period
        index = end_clk(time, clk_period) - \
            start_clk(self.timeOffset, clk_period)

        assert index >= 0, (self.timeOffset, time, self.valuesInTime[0])
        try:
            return self.valuesInTime[index]
        except IndexError:
            pass

        # allocate registers to propagate value into next cycles
        sig = self.valuesInTime[0]
        prev = self.valuesInTime[-1]
        requestedRegCnt = index + 1
        actualTimesCnt = len(self.valuesInTime)
        name = getSignalName(sig)

        # allocate specified number of registers to pass value to specified clk
        # period
        for i in range(actualTimesCnt, requestedRegCnt):
            reg = self.allocator._reg(name + "_delay_%d" % i,
                                      dtype=sig._dtype)
            reg(prev)
            self.valuesInTime.append(reg)
            prev = reg

        return reg


class HlsAllocator():
    """
    Convert virtual operation instances to real RTL code

    :ivar parentHls: parent HLS context for this allocator
    :ivar node2instance: dictionary {hls node: rtl instance}
    """

    def __init__(self, parentHls: HlsPipeline):
        self.parentHls = parentHls
        self.node2instance = {}
        # function to create register on RTL level
        self._reg = parentHls.parentUnit._reg
        self._sig = parentHls.parentUnit._sig

    def _instantiate(self, node: Union[HlsOperation,
                                       HlsRead,
                                       HlsWrite]):
        """
        Universal RTL instanciation method for all types
        """
        if isinstance(node, TimeIndependentRtlResource):
            return node
        elif isinstance(node, HlsRead):
            return self.instantiateRead(node)
        elif isinstance(node, HlsWrite):
            return self.instantiateWrite(node)
        else:
            return self.instantiateOperation(node)

    def instantiateOperationInTime(self, o: HlsOperation, time:float):
        try:
            _o = self.node2instance[o]
        except KeyError:
            _o = None

        if _o is None:
            # if dependency of this node is not instantiated yet
            # instantiate it
            _o = self._instantiate(o)

        return _o.get(time)

    def instantiateOperation(self, node: HlsOperation):
        """
        Instantiate operation on RTL level
        """
        if isinstance(node, HlsConst):
            s = node.val
            t = TimeIndependentRtlResource.INVARIANT_TIME
        else:

            # instantiate dependencies
            # [TODO] problem with cyclic dependency
            if node.operator == AllOps.TERNARY:
                node: HlsMux
                name = node.name
                s = self._sig(name, self.instantiateOperationInTime(node.elifs[0][1], node.scheduledIn)._dtype)
                mux_top = None
                for (c, v) in node.elifs:
                    if c is None:
                        _c = c
                    else:
                        _c = self.instantiateOperationInTime(c, node.scheduledIn)
                    _v = self.instantiateOperationInTime(v, node.scheduledIn)

                    if mux_top is None:
                        mux_top = If(_c, s(_v))
                    elif _c is not None:
                        mux_top.Elif(_c, s(_v))
                    else:
                        mux_top.Else(s(_v))

            else:
                operands = []
                for o in node.dependsOn:
                    _o = self.instantiateOperationInTime(o, node.scheduledIn)
                    operands.append(_o)
                s = node.operator._evalFn(*operands)

            # create RTL signal expression base on operator type
            t = node.scheduledIn + epsilon

        rtlObj = TimeIndependentRtlResource(s, t, self)
        self.node2instance[node] = rtlObj
        return rtlObj

    def instantiateRead(self, readOp: HlsRead):
        """
        Instantiate read operation on RTL level
        """
        _o = TimeIndependentRtlResource(
            readOp.getRtlDataSig(),
            readOp.scheduledIn + epsilon,
            self)
        self.node2instance[readOp] = _o
        return _o

    def instantiateWrite(self, write: HlsWrite) -> List[HdlAssignmentContainer]:
        """
        Instantiate write operation on RTL level
        """
        o = write.dependsOn[0]
        # if isinstance(o, HlsMux) and o in self.node2instance:
        #    return []

        try:
            _o = self.node2instance[o]
        except KeyError:
            # o should be instance of TimeIndependentRtlResource itself
            _o = None

        if _o is None:
            _o = self._instantiate(o)

        # apply indexes before assignments
        dst = write.dst
        try:
            # translate HlsIo object to signal
            _dst = self.parentHls._io[dst]
            dst = _dst
        except KeyError:
            pass

        if write.indexes is not None:
            for i in write.indexes:
                dst = dst[i]
        try:
            # skip instantiation of writes in the same mux
            return self.node2instance[(o, dst)]
        except KeyError:
            pass

        assert o is not _o, (o, _o)
        assert isinstance(_o, TimeIndependentRtlResource), _o
        _o = _o.get(o.scheduledIn)

        rtlObj = dst(_o)
        self.node2instance[o] = rtlObj
        self.node2instance[(o, dst)] = rtlObj

        return rtlObj

    def allocate(self):
        """
        Allocate scheduled circuit in RTL
        """
        scheduler = self.parentHls.scheduler

        for nodes in scheduler.schedulization:
            for node in nodes:
                # this is one level of nodes,
                # node can not be dependent on nodes behind in this list
                self._instantiate(node)
