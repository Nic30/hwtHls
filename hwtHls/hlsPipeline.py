from typing import List, Dict, Union, Optional

from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.rtlLevel.netlist import RtlNetlist
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwt.synthesizer.unit import Unit
from hwtHls.netlist.nodes.io import HlsRead, HlsWrite
from hwtHls.netlist.nodes.ops import AbstractHlsOp
from hwtHls.scheduler.scheduler import HlsScheduler
from hwtHls.allocator.allocator import HlsAllocator


class HlsPipelineNodeContext():

    def __init__(self):
        self.cntr = 0

    def getUniqId(self):
        c = self.cntr
        self.cntr += 1
        return c


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
        self.nodeCtx = HlsPipelineNodeContext()
        if self.platform is None:
            raise ValueError("HLS requires platform to be specified")

        self.clk_period = 1 / int(freq)
        self.resource_constrain = resource_constrain
        self.inputs: List[HlsRead] = []
        self.outputs: List[HlsWrite] = []
        self.io_by_interface: Dict[Interface, List[Union[HlsRead, HlsWrite]]] = {}
        self.nodes: List[AbstractHlsOp] = []
        self._io: Dict[RtlSignal, Interface] = {}
        self.ctx = RtlNetlist()
        self.allow_io_aggregation = allow_io_aggregation
        if coherency_checked_io is None:
            coherency_checked_io = UniqList()

        self.coherency_checked_io: UniqList[Interface] = coherency_checked_io

        self.scheduler: HlsScheduler = self.platform.scheduler(self)
        self.allocator: HlsAllocator = self.platform.allocator(self)

    def schedule(self):
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

    def synthesise(self):
        self.allocator.allocate()


def reconnect_endpoint_list(signals, oldEp, newEp):
    for s in signals:
        if isinstance(s, RtlSignal):
            try:
                s.endpoints.remove(oldEp)
            except KeyError:
                pass
            s.endpoints.append(newEp)
