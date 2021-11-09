from typing import List, Dict, Union, Optional

from hwt.hdl.statements.assignmentContainer import HdlAssignmentContainer
from hwt.hdl.types.defs import BIT
from hwt.interfaces.hsStructIntf import HsStructIntf
from hwt.interfaces.std import Signal
from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.interfaceLevel.unitImplHelpers import getSignalName
from hwt.synthesizer.rtlLevel.extract_part_drivers import extract_part_drivers
from hwt.synthesizer.rtlLevel.mainBases import RtlSignalBase
from hwt.synthesizer.rtlLevel.netlist import RtlNetlist
from hwt.synthesizer.rtlLevel.remove_unconnected_signals import removeUnconnectedSignals
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwt.synthesizer.unit import Unit
from hwtHls.errors import HlsSyntaxError
from hwtHls.hwtNetlistToHwtHlsNetlist import HwtNetlistToHwtHlsNetlist
from hwtHls.netlist.nodes.ops import AbstractHlsOp
from hwtHls.netlist.nodes.io import HlsRead, HlsWrite, HlsIO
from ipCorePackager.constants import DIRECTION


class HlsPipeline():
    """
    High level synthesiser context.
    Convert sequential code without data dependency cycles to RTL.

    :ivar parentUnit: parent unit where RTL should be instantiated
    :ivar platform: platform with configuration of this HLS context
    :ivar freq: target frequency for RTL (in Hz)
    :ivar resource_constrain: optional resource constrains
    :ivar inputs: list of HlsRead operations in this pipeline
    :ivar outputs: list of HlsWrite operations in this pipeline
    :ivar io_by_interface: dictionary which agregates all io operations by its interface
    :ivar nodes: list of all schedulization nodes present in this pipeline (except inputs/outputs)
    :ivar ctx: RtlNetlist (container of RTL signals for this HLS context)
        the purpose of objects in this ctx is only to store the input code
        these objecs are not present in output circuit and are only form of code
        themplate which must be translated
    :ivar allow_io_aggregation: If true the io_by_interface property is used to store
        the meta of how chunks of code access same interfaces and how the arbitration should be done.
        If False the assertion error is raised if some IO is accessed on multiple code locations.
    """

    def __init__(self, parentUnit: Unit,
                 freq: Union[float, int],
                 resource_constrain=None,
                 allow_io_aggregation=False,
                 coherency_checked_io:Optional[UniqList[Interface]]=None):
        """
        :see: For parameter meaning see doc of this class.
        """
        self.parentUnit = parentUnit
        self.platform = parentUnit._target_platform
        if self.platform is None:
            raise ValueError("HLS requires platform to be specified")

        self.clk_period = 1 / int(freq)
        self.resource_constrain = resource_constrain
        self.inputs: List[HlsRead] = []
        self.outputs: List[HlsWrite] = []
        self.io_by_interface: Dict[Interface, List[Union[HlsRead, HlsWrite]]] = {}
        self.nodes: List[AbstractHlsOp] = []
        self._io: Dict[HlsIO, Interface] = {}
        self.ctx = RtlNetlist()
        self.allow_io_aggregation = allow_io_aggregation
        if coherency_checked_io is None:
            coherency_checked_io = UniqList()

        self.coherency_checked_io: UniqList[Interface] = coherency_checked_io

        self.scheduler = self.platform.scheduler(self)
        self.allocator = self.platform.allocator(self)

    def var(self, name, dtype=BIT, def_val=None):
        """
        Universal HLS code variable
        """
        return self.ctx.sig(name, dtype=dtype, def_val=def_val)

    def _convert_indexed_io_assignments_to_HlsWrite(self):
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
                self.outputs.append(w)
                self.ctx.statements.add(w)

        for a in to_destroy:
            statements.remove(a)

    def _build_data_flow_graph(self):
        """
        Walk signals and extract operations as data flow graph composed of AbstractHlsOp

        (convert from representation with signals
         to directed graph of operations)
        """
        extract_part_drivers(self.ctx)
        self._convert_indexed_io_assignments_to_HlsWrite()
        for io, ioIntf in self._io.items():
            io: HlsIO
            ioIntf: Interface
            if io.drivers:
                # if io.endpoints:
                #    # R/W
                #    raise NotImplementedError("read and write from a single interface", io, ioIntf)
                # else:
                # WriteOnly, HlsWrite already created
                assert len(io.drivers) == 1, (io, io.drivers)
                self.ctx.interfaces[io] = DIRECTION.OUT

            elif io.endpoints:
                # ReadOnly
                r = HlsRead(self, ioIntf, io)
                self.ctx.interfaces[r] = DIRECTION.IN
                self.inputs.append(r)

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
            # driver = out.src
            to_hls.to_hls_expr(out.dst)
            # driver =
            # link_hls_nodes(driver, out)
            # nodeToHlsNode[out] = out

        # list of discovered nodes
        self.nodes.extend(nodeToHlsNode.values())

        for i in self.inputs:
            if i.dependsOn[0] is None:
                i.dependsOn.pop()

    def synthesise(self):
        """
        Convert code template to circuit (netlist of Hdl objects)
        """
        assert not self.io_by_interface
        io_by_interface = self.io_by_interface
        for op in self.inputs:
            op: HlsRead
            op_list = io_by_interface.get(op.src, None)
            if op_list  is None:
                op_list = io_by_interface[op.src] = []
            op_list.append(op)

        for op in self.outputs:
            op: HlsWrite
            op_list = io_by_interface.get(op.dst, None)
            if op_list  is None:
                op_list = io_by_interface[op.dst] = []
            op_list.append(op)

        self.scheduler.schedule(self.resource_constrain)
        self.allocator.allocate()

    def io(self, io: Interface) -> HlsIO:
        """
        Convert signal/interface to IO
        """
        for _io, prev_io_obj in self._io.items():
            if io is prev_io_obj:
                return _io

        name = "hls_io_" + getSignalName(io)
        if isinstance(io, (RtlSignalBase, Signal)):
            dtype = io._dtype
        else:
            assert isinstance(io, HsStructIntf), io
            dtype = io.T

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
            self._build_data_flow_graph()
            self.synthesise()


def reconnect_endpoint_list(signals, oldEp, newEp):
    for s in signals:
        if isinstance(s, RtlSignal):
            try:
                s.endpoints.remove(oldEp)
            except KeyError:
                pass
            s.endpoints.append(newEp)
