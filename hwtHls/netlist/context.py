from io import StringIO
from itertools import chain
from math import ceil
from typing import Union, Optional, Set, Callable

from hwt.synthesizer.rtlLevel.netlist import RtlNetlist
from hwt.synthesizer.unit import Unit
from hwtHls.netlist.analysis.hlsNetlistAnalysisPass import HlsNetlistAnalysisPass
from hwtHls.netlist.nodes.aggregate import HlsNetNodeAggregate
from hwtHls.netlist.nodes.node import HlsNetNode, NODE_ITERATION_TYPE
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.observableList import ObservableList, ObservableListRm
from hwtHls.netlist.scheduler.scheduler import HlsScheduler
from hwtHls.ssa.analysisCache import AnalysisCache
from hwtHls.typingFuture import override


class HlsNetlistCtx(AnalysisCache):
    """
    High level synthesiser netlist context.
    Convert sequential code without data dependency cycles to RTL.

    :ivar label: a name of this scope
    :ivar namePrefix: name prefix which should be used for child object names
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
    :ivar _dbgAddSignalNamesToSync: add names to synchronization signals in order to improve readability,
        disabled by default as it goes against optimizations
    """

    def __init__(self, parentUnit: Unit,
                 freq: Union[float, int],
                 label: str,
                 namePrefix:str="hls_",
                 schedulerResolution:float=0.01e-9,
                 platform: Optional["VirtualHlsPlatform"]=None):
        """
        :see: For parameter meaning see doc of this class.
        :ivar schedulerResolution: The time resolution for time in scheduler specified in seconds (1e-9 is 1ns).
        """
        self.label = label
        self.namePrefix = namePrefix
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
        AnalysisCache.__init__(self)
        self.scheduler: HlsScheduler = self.platform.schedulerCls(self, schedulerResolution)
        self._dbgAddSignalNamesToSync = False
        self._dbgAddSignalNamesToData = False
        self._dbgLogPassExec:Optional[StringIO] = None
        if platform is not None:
            self._dbgLogPassExec = platform.getPassManagerDebugLogFile()

    @override
    def _runAnalysisImpl(self, a: HlsNetlistAnalysisPass):
        return a.runOnHlsNetlist(self)

    def _setBuilder(self, b: "HlsNetlistBuilder"):
        self.builder = b

    def getUniqId(self):
        n = self._uniqNodeCntr
        self._uniqNodeCntr += 1
        return n

    def iterAllNodes(self):
        """
        :returns: iterator of all nodes on top hierarchy level
        """
        return chain(self.inputs, self.nodes, self.outputs)

    def iterAllNodesFlat(self, itTy: NODE_ITERATION_TYPE):
        """
        :returns: iterator of all non aggregate nodes on any level of hierarchy
        """
        for n in self.iterAllNodes():
            yield from n.iterAllNodesFlat(itTy)

    def schedule(self):
        self.scheduler.schedule()

    def filterNodesUsingSet(self, removed: Set[HlsNetNode], recursive=False):
        if removed:
            self.inputs[:] = (n for n in self.inputs if n not in removed)
            self.nodes[:] = (n for n in self.nodes if n not in removed)
            self.outputs[:] = (n for n in self.outputs if n not in removed)
            if recursive:
                for n in self.iterAllNodes():
                    if isinstance(n, HlsNetNodeAggregate):
                        n.filterNodesUsingSet(removed, recursive=recursive)

            removed.clear()

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

    def __repr__(self)->str:
        return f"<{self.__class__.__name__:s} {self.label:s}>"
    