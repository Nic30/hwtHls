from typing import Union

from hwt.hdl.assignment import Assignment
from hwt.hdl.operator import Operator
from hwt.hdl.types.defs import BIT
from hwt.hdl.types.struct import HStruct
from hwt.hdl.value import Value
from hwt.synthesizer.interfaceLevel.unitImplHelpers import getSignalName
from hwt.synthesizer.rtlLevel.netlist import RtlNetlist
from hwt.synthesizer.rtlLevel.optimalizator import removeUnconnectedSignals
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwt.synthesizer.unit import Unit
from hwtHls.codeOps import HlsRead, HlsWrite, HlsOperation,\
    HlsConst, AbstractHlsOp, HlsMux, HlsIO


class HLS_Error(Exception):
    pass


def link_nodes(parent, child):
    child.dependsOn.append(parent)
    parent.usedBy.append(child)


def operator2Hls(operator: Operator, hls, nodeToHlsNode: dict) -> HlsOperation:
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
    op_node = HlsOperation(hls,
                           operator.operator,
                           operator.operands[0]._dtype.bit_length())
    nodeToHlsNode[operator] = op_node

    # walk all inputs and connect them as my parent
    for op in operator.operands:
        op = hdlObj2Hls(op, hls, nodeToHlsNode)
        if op is not None:
            link_nodes(op, op_node)

    return op_node


def mux2Hls(obj: RtlSignal, hls, nodeToHlsNode: dict):
    """
    Recursively convert signal which is output of multiplexer/demultiplexer
    to HLS nodes
    """
    try:
        return nodeToHlsNode[obj]
        # was already discovered
    except KeyError:
        pass

    if obj.hasGenericName:
        name = "mux_"
    else:
        name = obj.name

    _obj = HlsMux(hls, obj._dtype.bit_length(), name=name)
    nodeToHlsNode[obj] = _obj

    # check if conditions are in suitable format for simple MUX
    if len(obj.drivers) != 2:
        raise NotImplementedError()

    ifTrue, ifFalse = obj.drivers
    if len(ifTrue.cond) != len(ifFalse.cond) != 1:
        raise NotImplementedError(ifTrue.cond, ifFalse.cond)

    if ifTrue.cond[0] is not ~ifFalse.cond[0]:
        raise NotImplementedError(ifTrue.cond, ifFalse.cond)

    # add condition to dependencies of this MUX operator
    c = hdlObj2Hls(obj.drivers[0].cond[0],  hls, nodeToHlsNode)
    link_nodes(c, _obj)

    for a in obj.drivers:
        assert isinstance(a, Assignment), a
        if a.indexes:
            raise NotImplementedError()

        src = hdlObj2Hls(a.src,  hls, nodeToHlsNode)
        link_nodes(src, _obj)

    return _obj


def driver2Hls(obj, hls, nodeToHlsNode: dict) -> AbstractHlsOp:
    if isinstance(obj, HlsRead):
        nodeToHlsNode[obj] = obj
        return obj
    elif isinstance(obj, HlsWrite):
        nodeToHlsNode[obj] = obj
        if obj.cond or obj.indexes:
            raise NotImplementedError()

        return hdlObj2Hls(obj.src, hls, nodeToHlsNode)
    elif isinstance(obj, Operator):
        return operator2Hls(obj, hls, nodeToHlsNode)
    elif isinstance(obj, Assignment):
        if obj.cond or obj.indexes:
            raise NotImplementedError()

        src = hdlObj2Hls(obj.src, hls, nodeToHlsNode)
        dst = nodeToHlsNode[obj.dst.endpoints[0]]

        link_nodes(src, dst)
        return src
    else:
        raise NotImplementedError(obj)


def hdlObj2Hls(obj: Union[RtlSignal, Value],
               hls, nodeToHlsNode: dict) -> AbstractHlsOp:
    """
    Convert RtlObject to HlsObject, register it and link it wit parent

    :note: parent is who provides values to operation
    """
    if isinstance(obj, Value) or obj._const:
        _obj = HlsConst(obj)
        nodeToHlsNode[_obj] = _obj
        return _obj

    dcnt = len(obj.drivers)
    if dcnt > 1:
        # [TODO] mux X indexed assignments
        return mux2Hls(obj, hls, nodeToHlsNode)
    elif dcnt == 1:
        # parent is just RtlSignal, we needs operation
        # it is drivern from
        return driver2Hls(obj.drivers[0], hls, nodeToHlsNode)
    else:
        assert isinstance(obj, HlsIO), obj


def reconnect_endpoint_list(signals, oldEp, newEp):
    for s in signals:
        if isinstance(s, RtlSignal):
            try:
                s.endpoints.remove(oldEp)
            except KeyError:
                pass
            s.endpoints.append(newEp)


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
    :ivar io: dict HlsIO:Interface
    :ivar ctx: RtlNetlist (contarner of RTL signals for this HLS context)
    """

    def __init__(self, parentUnit: Unit,
                 freq, maxLatency=None, resource_constrain=None):
        self.parentUnit = parentUnit
        self.platform = parentUnit._targetPlatform
        if self.platform is None:
            raise Exception("HLS requires platform to be specified")

        self.clk_period = 1 / int(freq)
        self.maxLatency = maxLatency
        self.resource_constrain = resource_constrain
        self.inputs = []
        self.outputs = []
        self._io = {}
        self.ctx = RtlNetlist()

        self.scheduler = self.platform.scheduler(self)
        self.allocator = self.platform.allocator(self)
        # (still float div)
        self.platform.onHlsInit(self)

    def var(self, name, dtype=BIT, defVal=None):
        """
        Universal HLS code variable
        """
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

    def convert_indexed_io_assignments_to_HlsWrite(self):
        to_destroy = []
        assignments = self.ctx.statements
        for a in assignments:
            if a.indexes and isinstance(a.dst, HlsIO):
                to_destroy.append(a)
                w = HlsWrite(self, a.src, a.dst)
                w.indexes = a.indexes
                reconnect_endpoint_list(w.indexes, a, w)
                w.cond = a.cond
                reconnect_endpoint_list(w.cond, a, w)

        for a in to_destroy:
            assignments.remove(a)

    def _discoverAllNodes(self):
        """
        Walk signals and extract operations as AbstractHlsOp

        (convert from representation with signals
         to directed graph of operations)
        """
        self.convert_indexed_io_assignments_to_HlsWrite()
        removeUnconnectedSignals(self.ctx)

        for io, ioIntf in self._io.items():
            if io.drivers:
                if io.endpoints:
                    # R/W
                    raise NotImplementedError()
                else:
                    # WriteOnly, HlsWrite already created
                    pass
            elif io.endpoints:
                if io.drivers:
                    # R/W
                    raise NotImplementedError()
                else:
                    # ReadOnly
                    r = HlsRead(self, ioIntf)
                    io.drivers.append(r)
                    io.origin = r
            else:
                raise HLS_Error("Unused IO", io, ioIntf)

        # used as seen set
        nodeToHlsNode = {}

        # walk CFG of HDL objects from outputs to inputs and convert it to CFG
        # of HLS nodes
        # [TODO] write can be to same destination,
        # if there is such a situation MUX has to be created
        for out in self.outputs:
            nodeToHlsNode[out] = out

        for out in self.outputs:
            driver = out.src
            driver = hdlObj2Hls(driver, self, nodeToHlsNode)
            link_nodes(driver, out)

        # list of discovered nodes
        nodes = list(nodeToHlsNode.values())
        return nodes

    def synthesise(self):
        """
        Convert code template to circuit (netlist of Hdl objects)
        """
        self.nodes = self._discoverAllNodes()
        for n in self.nodes:
            n.resolve_realization()

        self.scheduler.schedule(self.resource_constrain)
        self.allocator.allocate()

    def io(self, io):
        """
        Convert signal/interface to IO
        """
        name = "hls_io_" + getSignalName(io)
        dtype = io._dtype
        _io = HlsIO(self, name, dtype)
        _io.hasGenericName = True
        self.ctx.signals.add(_io)
        self._io[_io] = io

        return _io

    def __enter__(self):
        # temporary overload _sig method to use var from HLS
        self._unit_sig = self.parentUnit._sig
        self.parentUnit._sig = self.var
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.parentUnit._sig = self._unit_sig
        if exc_type is None:
            self.synthesise()
