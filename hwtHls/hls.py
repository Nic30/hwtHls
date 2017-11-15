from copy import copy

from hwt.hdl.operator import Operator
from hwt.hdl.value import Value
from hwt.synthesizer.rtlLevel.netlist import RtlNetlist
from hwt.synthesizer.unit import Unit
from hwtHls.codeObjs import ReadOpPromise, WriteOpPromise, HlsOperation,\
    HlsConst, AbstractHlsOp


class Hls():
    """
    High level synthesiser context.
    Convert sequential code to RTL.

    :ivar parentUnit: parent unit where RTL should be instantiated
    :ivar platform: platform with configuration of this HLS context
    :ivar freq: target frequency for RTL
    :ivar maxLatency: optional maximum allowed latency of circut
    :ivar resources: optional resource constrains
    :ivar inputs: list of ReadOpPromise in this context
    :ivar outputs: list of WriteOpPromise in this context
    :ivar ctx: RtlNetlist (contarner of RTL signals for this HLS context)
    """

    def __init__(self, parentUnit: Unit,
                 freq, maxLatency=None, resources=None):
        self.parentUnit = parentUnit
        self.platform = parentUnit._targetPlatform
        if self.platform is None:
            raise Exception("HLS requires platform to be specified")

        self.scheduler = self.platform.scheduler(self)
        self.allocator = self.platform.allocator(self)
        # (still float div)
        self.clk_period = 1 / int(freq)
        self.maxLatency = maxLatency
        self.resources = resources
        self.inputs = []
        self.outputs = []
        self.ctx = RtlNetlist()
        self.platform.onHlsInit(self)

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
            """
            Recursively convert operator and it's inputs to HLS representation

            :return: instance of HlsOperation representing of this operator
            """
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
            assert isinstance(node, AbstractHlsOp)
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
                        usedBy = out
                        usedBy.dependsOn.append(node)
                        node.usedBy.append(usedBy)
                    elif isinstance(_driver, ReadOpPromise):
                        node = _driver
                        registerNode(node, out)
                    else:
                        raise NotImplementedError(_driver)

        nodes.extend(nodeToHlsNode.values())
        return nodes

    def synthesise(self):
        self.nodes = self.discoverAllNodes()
        self.scheduler.schedule()
        self.allocator.allocate()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.synthesise()
