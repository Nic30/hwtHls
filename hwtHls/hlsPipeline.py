from itertools import chain
from typing import List, Union, Optional, Type

from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.rtlLevel.netlist import RtlNetlist
from hwt.synthesizer.unit import Unit
from hwtHls.allocator.allocator import HlsAllocator
from hwtHls.netlist.analysis.hlsNetlistAnalysisPass import HlsNetlistAnalysisPass
from hwtHls.netlist.nodes.io import HlsNetNodeRead, HlsNetNodeWrite
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.scheduler.scheduler import HlsScheduler


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
    :ivar inputs: list of HlsNetNodeRead operations in this pipeline
    :ivar outputs: list of HlsNetNodeWrite operations in this pipeline
    :ivar nodes: list of all schedulization nodes present in this pipeline (except inputs/outputs)
    :ivar ctx: RtlNetlist (container of RTL signals for this HLS context)
        the purpose of objects in this ctx is only to store the input code
        these objecs are not present in output circuit and are only form of code
        themplate which must be translated
    """

    def __init__(self, parentUnit: Unit,
                 freq: Union[float, int],
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
        self.inputs: List[HlsNetNodeRead] = []
        self.outputs: List[HlsNetNodeWrite] = []
        self.nodes: List[HlsNetNode] = []

        self.ctx = RtlNetlist()
        if coherency_checked_io is None:
            coherency_checked_io = UniqList()

        self.coherency_checked_io: UniqList[Interface] = coherency_checked_io
        
        self._analysis_cache = {}
        
        self.scheduler: HlsScheduler = self.platform.scheduler(self)
        self.allocator: HlsAllocator = self.platform.allocator(self)

    def iterAllNodes(self):
        return chain(self.inputs, self.nodes, self.outputs)

    def invalidateAnalysis(self, analysis_cls:Type[HlsNetlistAnalysisPass]):
        a = self._analysis_cache.pop(analysis_cls, None)
        if a is not None:
            a.invalidate()
        
    def requestAnalysis(self, analysis_cls:Type[HlsNetlistAnalysisPass]):
        try:
            return self._analysis_cache[analysis_cls]
        except KeyError:
            pass
        a = analysis_cls(self)
        a.run()
        self._analysis_cache[analysis_cls] = a
        return a

    def schedule(self):
        self.scheduler.schedule()

    def allocate(self):
        """
        Convert the HLS netlist to RTL netlist
        """
        self.allocator.allocate()

