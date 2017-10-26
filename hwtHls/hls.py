from copy import copy
from pprint import pprint

from hwt.hdl.operator import Operator
from hwt.interfaces.std import Signal
from hwt.synthesizer.rtlLevel.netlist import RtlNetlist
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwt.synthesizer.uniqList import UniqList
from hwtHls.platform.xilinx.abstract import AbstractXilinxPlatform
from hwt.hdl.value import Value


class AbstractHlsOp():
    def __init__(self, latency):
        self.usedBy = UniqList()
        self.dependsOn = UniqList()
        self.latency = latency


class ReadOpPromise(Signal, AbstractHlsOp):
    def __init__(self, hlsCtx, intf, latency):
        dataSig = intf._sig
        t = dataSig._dtype

        AbstractHlsOp.__init__(self, latency)
        Signal.__init__(self, dtype=t)

        self._sig = hlsCtx.ctx.sig("hsl_" + intf._name,
                                   dtype=t)

        self._sig.origin = self
        self._sig.drivers.append(self)

        self.hlsCtx = hlsCtx
        self.intf = intf

        hlsCtx.inputs.append(self)


class WriteOpPromise(AbstractHlsOp):
    """
    :ivar what: const value or HlsVariable
    :ivar where: output interface not relatet to HLS
    """

    def __init__(self, hlsCtx, what, where, latency):
        super(WriteOpPromise, self).__init__(latency=latency)
        self.hlsCtx = hlsCtx
        self.what = what
        self.where = where
        if isinstance(what, RtlSignal):
            what.endpoints.append(self)

        hlsCtx.outputs.append(self)


class HlsOperation(AbstractHlsOp):
    """
    Abstract implementation of RTL operator

    :ivar parentHls: Hls instance where is schedueling performed
    :ivar pre_delay: wire delay from input to outputs or next clock cycles
    :ivar pot_delay: wire delay after last clock cycle (or 0)
    :ivar latency: computational latency of pipelined operation (0 == combinational component)
    :ivar cycles: computational delay of operation (0 == result every cycle)
    """

    def __init__(self,
                 rtlOp: Operator,
                 parentHls,
                 onUpdateFn=None):
        super(HlsOperation, self).__init__(latency=0)
        self.parentHls = parentHls
        self.pre_delay = 0
        self.post_delay = 0
        self.cycles = 0

        self.rtlOp = rtlOp
        self.onUpdateFn = onUpdateFn


class HlsSchedueler():
    def __init__(self, parentHls):
        self.parentHls = parentHls

    def alap(self):
        pass

    def asap(self):
        _nodes = copy(self.parentHls.nodes)
        open = set()
        t = 0
        for node in _nodes:
            # has no predecessors
            # [TODO] input read latency
            if isinstance(node, ReadOpPromise):
                for endp in node._sig.endpoints:
                    open.add(endp)

        while open:
            pass

    def scheduele(self):
        self.asap()
        self.alap()


class HlsConst(AbstractHlsOp):
    def __init__(self, val):
        super(HlsConst, self).__init__()
        self.val = val


class Hls():
    """
    High level synthesiser context
    """

    def __init__(self, parentUnit,
                 freq=None, maxLatency=None, resources=None,
                 schedueler=HlsSchedueler):
        self.parentUnit = parentUnit
        # [TODO]
        self.platform = None
        self.freq = freq
        self.maxLatency = maxLatency
        self.resources = resources
        self.inputs = []
        self.outputs = []
        self.ctx = RtlNetlist()
        self.schedueler = schedueler(self)

    def read(self, intf, latency=0):
        """
        Scheduele read operation
        """
        return ReadOpPromise(self, intf, latency)

    def write(self, what, where, latency=1):
        """
        Scheduele write operation
        """
        return WriteOpPromise(self, what, where, latency)

    def discoverAllNodes(self):
        """
        Walk signals and extract operations as AbstractHlsOp

        (convert from representation with signals
         to directed graph of operations)
        """
        nodes = copy(self.outputs)
        nodeToHlsNode = {}

        def convertToHlsNodeTree(operator: Operator) -> HlsOperation:
            assert isinstance(operator, Operator), operator
            try:
                return nodeToHlsNode[operator]
            except KeyError:
                pass

            node = HlsOperation(operator.operator, self)
            nodeToHlsNode[operator] = node

            for op in operator.operands:
                if isinstance(op, Value) or op._const:
                    _op = HlsConst(op)
                    nodes.append(_op)
                else:
                    origin = op.origin
                    if isinstance(origin, ReadOpPromise):
                        _op = origin
                        nodes.append(_op)
                    else:
                        _op = convertToHlsNodeTree(origin)

                _op.usedBy.append(node)
                node.dependsOn.append(_op)
            return node

        def registerNode(node, usedBy):
            usedBy.dependsOn.append(node)
            node.usedBy.append(usedBy)
            nodes.append(node)

        for out in self.outputs:
            driver = out.what
            if isinstance(driver, ReadOpPromise):
                registerNode(driver, out)
            elif isinstance(driver, Value) or driver._const:
                registerNode(HlsConst(driver), out)
            else:
                for _driver in driver.drivers:
                    if isinstance(_driver, Operator):
                        node = convertToHlsNodeTree(_driver)
                    elif isinstance(_driver, ReadOpPromise):
                        node = _driver
                    else:
                        raise NotImplementedError(_driver)

                    registerNode(node, out)

        nodes.extend(nodeToHlsNode.keys())
        return nodes

    def synthesise(self):
        self.nodes = self.discoverAllNodes()
        self.schedueler.scheduele()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.synthesise()
