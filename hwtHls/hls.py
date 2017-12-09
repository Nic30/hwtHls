from hwt.hdl.operator import Operator
from hwt.hdl.value import Value
from hwt.synthesizer.rtlLevel.netlist import RtlNetlist
from hwt.synthesizer.unit import Unit
from hwtHls.codeOps import HlsRead, HlsWrite, HlsOperation,\
    HlsConst, AbstractHlsOp, HlsMux
from hwt.hdl.types.defs import BIT
from hwt.hdl.types.struct import HStruct
from hwt.hdl.assignment import Assignment
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal


def link_nodes(parent, child):
    child.dependsOn.append(parent)
    parent.usedBy.append(child)


class Hls():
    """
    High level synthesiser context.
    Convert sequential code to RTL.

    :ivar parentUnit: parent unit where RTL should be instantiated
    :ivar platform: platform with configuration of this HLS context
    :ivar freq: target frequency for RTL
    :ivar maxLatency: optional maximum allowed latency of circut
    :ivar resources: optional resource constrains
    :ivar inputs: list of HlsRead in this context
    :ivar outputs: list of HlsWrite in this context
    :ivar ctx: RtlNetlist (contarner of RTL signals for this HLS context)
    """

    def __init__(self, parentUnit: Unit,
                 freq, maxLatency=None, resources=None):
        self.parentUnit = parentUnit
        self.platform = parentUnit._targetPlatform
        if self.platform is None:
            raise Exception("HLS requires platform to be specified")

        self.clk_period = 1 / int(freq)
        self.maxLatency = maxLatency
        self.resources = resources
        self.inputs = []
        self.outputs = []
        self.ctx = RtlNetlist()

        self.scheduler = self.platform.scheduler(self)
        self.allocator = self.platform.allocator(self)
        # (still float div)
        self.platform.onHlsInit(self)

    def var(self, name, dtype=BIT, defVal=None):
        if isinstance(dtype, HStruct):
            if defVal is not None:
                raise NotImplementedError()
            container = dtype.fromPy(None)
            for f in dtype.fields:
                if f.name is not None:
                    r = self._var("%s_%s" % (name, f.name), f.dtype)
                    setattr(container, f.name, r)

            return container

        return self.ctx.sig(name, dtype=dtype, defVal=defVal)

    def read(self, intf, latency=0):
        """
        Scheduele read operation
        """
        return HlsRead(self, intf, latency)

    def write(self, what, where, latency=0):
        """
        Scheduele write operation
        """
        return HlsWrite(self, what, where, latency)

    def _discoverAllNodes(self):
        """
        Walk signals and extract operations as AbstractHlsOp

        (convert from representation with signals
         to directed graph of operations)
        """
        # list of discovered nodes
        nodes = []
        # used as seen set
        nodeToHlsNode = {}

        def operator2Hls(operator: Operator) -> HlsOperation:
            """
            Recursively convert operator and it's inputs to HLS representation

            :return: instance of HlsOperation representing of this operator
            """
            try:
                return nodeToHlsNode[operator]
                # was already discovered
            except KeyError:
                pass

            # create HlsOperation node for this operator and register it
            op_node = HlsOperation(self, operator.operator)
            nodeToHlsNode[operator] = op_node

            # walk all inputs and connect them as my parent
            for op in operator.operands:
                op = hldObj2Hls(op)
                link_nodes(op, op_node)

            return op_node

        def mux2Hls(obj: RtlSignal):
            try:
                return nodeToHlsNode[obj]
                # was already discovered
            except KeyError:
                pass

            if obj.hasGenericName:
                name = "mux_"
            else:
                name = obj.name

            _obj = HlsMux(self, name=name)
            nodeToHlsNode[obj] = _obj

            muxInputs = []
            for a in obj.drivers:
                assert isinstance(a, Assignment), a
                if a.indexes:
                    raise NotImplementedError()

                if len(a.cond) > 1:
                    raise NotImplementedError(a.cond)

                c = hldObj2Hls(a.cond[0])
                link_nodes(c, _obj)

                src = hldObj2Hls(a.src)
                link_nodes(src, _obj)

                muxInputs.extend((c, src))

            return _obj

        def hldObj2Hls(obj) -> AbstractHlsOp:
            """
            Convert RtlObject to HlsObject, register it and link it wit parent

            :note: parent is who provides values to operation
            """
            if isinstance(obj, Value) or obj._const:
                _obj = HlsConst(obj)
                nodes.append(_obj)
            elif len(obj.drivers) > 1:
                # [TODO] mux X indexed assignments
                _obj = mux2Hls(obj)
            else:
                # parent is just RtlSignal, we needs operation
                # it is drivern from
                origin = obj.origin
                if isinstance(origin, HlsRead):
                    _obj = origin
                    nodes.append(_obj)
                elif isinstance(origin, Operator):
                    _obj = operator2Hls(origin)
                elif isinstance(origin, Assignment):
                    raise NotImplementedError()
                else:
                    raise NotImplementedError(origin)

            return _obj

        # walk CFG of HDL objects from outputs to inputs and convert it to CFG
        # of HLS nodes
        nodes.extend(self.outputs)
        for out in self.outputs:
            driver = out.what
            driver = hldObj2Hls(driver)
            link_nodes(driver, out)

        nodes.extend(nodeToHlsNode.values())
        return nodes

    def synthesise(self):
        self.nodes = self._discoverAllNodes()
        self.scheduler.schedule()
        self.allocator.allocate()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self.synthesise()
