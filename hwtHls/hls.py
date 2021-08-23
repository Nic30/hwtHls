from typing import List, Dict

from hwt.hdl.statements.assignmentContainer import HdlAssignmentContainer
from hwt.hdl.statements.statement import HwtSyntaxError
from hwt.hdl.types.defs import BIT
from hwt.hdl.types.struct import HStruct
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.interfaceLevel.unitImplHelpers import getSignalName
from hwt.synthesizer.rtlLevel.netlist import RtlNetlist
from hwt.synthesizer.rtlLevel.remove_unconnected_signals import removeUnconnectedSignals
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwt.synthesizer.unit import Unit
from hwtHls.codeOps import HlsRead, HlsWrite, HlsIO
from hwtHls.hwtNetlistToHwtHlsNetlist import HwtNetlistToHwtHlsNetlist
from ipCorePackager.constants import DIRECTION


class HlsSyntaxError(HwtSyntaxError):
    pass


class Hls():
    """
    High level synthesiser context.
    Convert sequential code to RTL.

    :ivar parentUnit: parent unit where RTL should be instantiated
    :ivar platform: platform with configuration of this HLS context
    :ivar freq: target frequency for RTL (in Hz)
    :ivar maxLatency: optional maximum allowed latency of circut
    :ivar resources: optional resource constrains
    :ivar ctx: RtlNetlist (container of RTL signals for this HLS context)
    """

    def __init__(self, parentUnit: Unit,
                 freq, maxLatency=None, resource_constrain=None):
        self.parentUnit = parentUnit
        self.platform = parentUnit._target_platform
        if self.platform is None:
            raise Exception("HLS requires platform to be specified")

        self.clk_period = 1 / int(freq)
        self.maxLatency = maxLatency
        self.resource_constrain = resource_constrain
        self.inputs: List[HlsRead] = []
        self.outputs: List[HlsWrite] = []
        self._io: Dict[HlsIO, Interface] = {}
        self.ctx = RtlNetlist()

        self.scheduler = self.platform.scheduler(self)
        self.allocator = self.platform.allocator(self)
        self.platform.onHlsInit(self)

    def var(self, name, dtype=BIT, def_val=None):
        """
        Universal HLS code variable
        """
        if isinstance(dtype, HStruct):
            if def_val is not None:
                raise NotImplementedError()
            container = dtype.fromPy(None)
            for f in dtype.fields:
                if f.name is not None:
                    r = self._var("%s_%s" % (name, f.name), f.dtype)
                    setattr(container, f.name, r)

            return container

        return self.ctx.sig(name, dtype=dtype, def_val=def_val)

    def convert_indexed_io_assignments_to_HlsWrite(self):
        to_destroy = []
        statements = self.ctx.statements
        for stm in list(statements):
            if isinstance(stm, HdlAssignmentContainer)\
                    and stm.indexes\
                    and isinstance(stm.dst, HlsIO):
                a = stm
                to_destroy.append(a)
                w = HlsWrite(self, a.src, a.dst)
                w.indexes = a.indexes
                reconnect_endpoint_list(w.indexes, a, w)

        for a in to_destroy:
            statements.remove(a)

    def _build_data_flow_graph(self):
        """
        Walk signals and extract operations as AbstractHlsOp

        (convert from representation with signals
         to directed graph of operations)
        """
        self.convert_indexed_io_assignments_to_HlsWrite()

        for io, ioIntf in self._io.items():
            io: HlsIO
            ioIntf: Interface
            if io.drivers:
                if io.endpoints:
                    # R/W
                    raise NotImplementedError("read and write from a single interface", io, ioIntf)
                else:
                    # WriteOnly, HlsWrite already created
                    self.ctx.interfaces[io] = DIRECTION.OUT
                    pass
            elif io.endpoints:
                # ReadOnly
                r = HlsRead(self, ioIntf, io)
                self.ctx.interfaces[r] = DIRECTION.IN
            else:
                raise HlsSyntaxError("Unused IO", io, ioIntf)

        removeUnconnectedSignals(self.ctx)

        # used as seen set
        nodeToHlsNode = {}

        # walk CFG of HDL objects from outputs to inputs and convert it to CFG
        # of HLS nodes
        # [TODO] write can be to same destination,
        # if there is such a situation MUX has to be created

        to_hls = HwtNetlistToHwtHlsNetlist(self, nodeToHlsNode)
        for out in self.outputs:
            out: HlsWrite
            #driver = out.src
            to_hls.to_hls_expr(out.dst)
            # driver =
            #link_hls_nodes(driver, out)
            #nodeToHlsNode[out] = out

        # list of discovered nodes
        nodes = list(nodeToHlsNode.values())

        return nodes

    def synthesise(self):
        """
        Convert code template to circuit (netlist of Hdl objects)
        """
        self.nodes = self._build_data_flow_graph()
        for n in self.nodes:
            n.resolve_realization()

        self.scheduler.schedule(self.resource_constrain)
        self.allocator.allocate()

    def io(self, io) -> HlsIO:
        """
        Convert signal/interface to IO
        """
        name = "hls_io_" + getSignalName(io)
        dtype = io._dtype
        _io = HlsIO(self, name, dtype)
        _io.hasGenericName = True
        _io.hidden = False
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


def reconnect_endpoint_list(signals, oldEp, newEp):
    for s in signals:
        if isinstance(s, RtlSignal):
            try:
                s.endpoints.remove(oldEp)
            except KeyError:
                pass
            s.endpoints.append(newEp)
