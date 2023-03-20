from itertools import chain
from math import ceil
from typing import Union, Optional, Type, Set, Callable

from hwt.synthesizer.rtlLevel.netlist import RtlNetlist
from hwt.synthesizer.unit import Unit
from hwtHls.architecture.allocator import HlsAllocator
from hwtHls.netlist.analysis.hlsNetlistAnalysisPass import HlsNetlistAnalysisPass
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.observableList import ObservableList, ObservableListRm
from hwtHls.netlist.scheduler.scheduler import HlsScheduler
from hwtHls.netlist.nodes.ports import HlsNetNodeOut


class HlsNetlistCtx():
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
        these objects are not present in output circuit and are only form of code
        template which must be translated
    """

    def __init__(self, parentUnit: Unit,
                 freq: Union[float, int],
                 label: str,
                 schedulerResolution:float=0.01e-9,
                 platform: Optional["VirtualHlsPlatform"]=None):
        """
        :see: For parameter meaning see doc of this class.
        :ivar schedulerResolution: The time resolution for time in scheduler specified in seconds (1e-9 is 1ns).
        """
        self.label = label
        self.parentUnit = parentUnit
        self.platform = platform if platform is not None else parentUnit._target_platform
        self.builder: Optional["HlsNetlistBuilder"] = None
        self._uniqNodeCntr = 0

        if self.platform is None:
            raise ValueError("HLS requires platform to be specified")

        self.realTimeClkPeriod = 1 / int(freq)
        self.normalizedClkPeriod = int(ceil(self.realTimeClkPeriod / schedulerResolution))
        self.inputs: ObservableList[HlsNetNodeRead] = ObservableList()
        self.outputs: ObservableList[HlsNetNodeWrite] = ObservableList()
        self.nodes: ObservableList[HlsNetNode] = ObservableList()

        self.ctx = RtlNetlist()
        self._analysis_cache = {}

        self.scheduler: HlsScheduler = self.platform.scheduler(self, schedulerResolution)
        self.allocator: HlsAllocator = self.platform.allocator(self)

    def _setBuilder(self, b: "HlsNetlistBuilder"):
        self.builder = b

    def getUniqId(self):
        n = self._uniqNodeCntr
        self._uniqNodeCntr += 1
        return n

    def iterAllNodes(self):
        return chain(self.inputs, self.nodes, self.outputs)

    def invalidateAnalysis(self, analysis_cls:Type[HlsNetlistAnalysisPass]):
        a = self._analysis_cache.pop(analysis_cls, None)
        if a is not None:
            a.invalidate()

    def getAnalysisIfAvailable(self, analysis_cls:Type[HlsNetlistAnalysisPass]):
        try:
            return self._analysis_cache[analysis_cls]
        except KeyError:
            return None

    def getAnalysis(self, analysis_cls:Union[Type[HlsNetlistAnalysisPass], HlsNetlistAnalysisPass]):
        if isinstance(analysis_cls, HlsNetlistAnalysisPass):
            a = analysis_cls
            analysis_cls = analysis_cls.__class__
        else:
            a = None

        try:
            return self._analysis_cache[analysis_cls]
        except KeyError:
            pass

        if a is None:
            a = analysis_cls(self)

        self._analysis_cache[analysis_cls] = a
        a.run()
        return a

    def schedule(self):
        self.scheduler.schedule()

    def filterNodesUsingSet(self, removed: Set[HlsNetNode]):
        if removed:
            self.inputs[:] = (n for n in self.inputs if n not in removed)
            self.nodes[:] = (n for n in self.nodes if n not in removed)
            self.outputs[:] = (n for n in self.outputs if n not in removed)

    def setupNetlistListeners(self,
                              beforeNodeAddedListener: Callable[[object, Union[slice, int], Union[HlsNetNode, ObservableListRm]], None],
                              beforeInputDriveUpdate: Callable[[object, Union[slice, int], Union[HlsNetNodeOut, None, ObservableListRm]], None],
                              beforeOutputUpdate: Callable[[object, Union[slice, int], Union[HlsNetNodeOut, None, ObservableListRm]], None],
                              removed: Set[HlsNetNode]):
        for nodeList in (self.inputs, self.nodes, self.outputs):
            nodeList._setObserver(beforeNodeAddedListener, None)

        for n in self.iterAllNodes():
            if n in removed:
                continue
            n.dependsOn._setObserver(beforeInputDriveUpdate, n)
            n._outputs._setObserver(beforeOutputUpdate, n)

    def dropNetlistListeners(self):
        for nodeList in (self.inputs, self.nodes, self.outputs):
            nodeList._setObserver(None, None)

        for n in self.iterAllNodes():
            n.dependsOn._setObserver(None, None)
            n._outputs._setObserver(None, None)

    def _dbgGetNodeById(self, _id: int) -> HlsNetNode:
        """
        :attention: Highly inefficient intended only for debugging
        """
        for n in self.iterAllNodes():
            if n._id == _id:
                return n
        raise ValueError("Node with requested id not found", _id)

