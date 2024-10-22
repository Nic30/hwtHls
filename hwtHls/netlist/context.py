from collections import OrderedDict
from io import StringIO
from math import ceil
from typing import Union, Optional, Set, Callable, Dict, List, Self, Sequence, \
    Type, Tuple

from hwt.hwIO import HwIO
from hwt.hwModule import HwModule
from hwt.pyUtils.typingFuture import override
from hwt.synthesizer.rtlLevel.netlist import RtlNetlist
from hwtHls.hwIOMeta import HwIOMeta
from hwtHls.netlist.analysis.hlsNetlistAnalysisPass import HlsNetlistAnalysisPass
from hwtHls.netlist.nodes.node import HlsNetNode, NODE_ITERATION_TYPE
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.observableList import ObservableList, ObservableListRm
from hwtHls.netlist.scheduler.scheduler import HlsScheduler
from hwtHls.ssa.analysisCache import AnalysisCache
from hwtHls.netlist.scheduler.resourceList import SchedulingResourceConstraints


class HlsNetlistCtx(AnalysisCache):
    """
    High level synthesiser netlist context.
    Convert sequential code without data dependency cycles to RTL.

    :ivar label: a name of this scope
    :ivar namePrefix: name prefix which should be used for child object names
    :ivar parentHwModule: parent unit where RTL should be instantiated
    :ivar platform: platform with configuration of this HLS context
    :ivar freq: target frequency for RTL (in Hz)
    :ivar nodes: list of all schedulization nodes present in this pipeline
    :ivar ctx: RtlNetlist (container of RTL signals for this HLS context)
        the purpose of objects in this ctx is only to store the input code
        these objects are not present in output circuit and are only form of code
        template which must be translated
    :ivar _dbgAddSignalNamesToSync: add names to synchronization signals in order to improve readability,
        disabled by default as it goes against optimizations
    """

    def __init__(self, parentHwModule: HwModule,
                 freq: Union[float, int],
                 label: str,
                 resourceConstraints:SchedulingResourceConstraints,
                 namePrefix:str="",
                 schedulerResolution:float=0.01e-9,
                 platform: Optional["VirtualHlsPlatform"]=None):
        """
        :see: For parameter meaning see doc of this class.
        :ivar schedulerResolution: The time resolution for time in scheduler specified in seconds (1e-9 is 1ns).
        """
        self.label = label
        self.namePrefix = namePrefix
        self.parentHwModule = parentHwModule
        self.platform = platform if platform is not None else parentHwModule._target_platform
        self.builder: Optional["HlsNetlistBuilder"] = None
        self._uniqNodeCntr = 0

        if self.platform is None:
            raise ValueError("HLS requires platform to be specified")

        self.realTimeClkPeriod = 1 / int(freq)
        self.normalizedClkPeriod = int(ceil(self.realTimeClkPeriod / schedulerResolution))
        self.subNodes: ObservableList[HlsNetNode] = ObservableList()

        self.ctx = RtlNetlist()
        AnalysisCache.__init__(self)
        self.scheduler: HlsScheduler = self.platform.schedulerCls(self, schedulerResolution, resourceConstraints)
        self._dbgAddSignalNamesToSync = False
        self._dbgAddSignalNamesToData = False
        self._dbgLogPassExec:Optional[StringIO] = None
        if platform is not None:
            self._dbgLogPassExec = platform.getPassManagerDebugLogFile()

        from hwtHls.netlist.builder import HlsNetlistBuilder
        self.builder = HlsNetlistBuilder(self)

    def getHlsNetlistBuilder(self) -> "HlsNetlistBuilder":
        return self.builder

    @override
    def _runAnalysisImpl(self, a: HlsNetlistAnalysisPass):
        return a.runOnHlsNetlist(self)

    def getUniqId(self):
        n = self._uniqNodeCntr
        self._uniqNodeCntr += 1
        return n

    def addNode(self, n: HlsNetNode):
        assert n.parent is None, (n, n.parent)
        self.subNodes.append(n)

    def addNodes(self, nodes: Sequence[HlsNetNode]):
        append = self.subNodes.append
        for n in nodes:
            assert n.parent is None, (n, n.parent)
            append(n)

    def iterAllNodes(self):
        """
        :returns: iterator of all nodes on top hierarchy level
        """
        return iter(self.subNodes)

    def iterAllNodesFlat(self, itTy: NODE_ITERATION_TYPE):
        """
        :returns: iterator of all non aggregate nodes on any level of hierarchy
        """
        for n in self.iterAllNodes():
            if n._isMarkedRemoved:
                continue
            yield from n.iterAllNodesFlat(itTy)

    def iterNodesFlatWithParentByType(self, cls_or_tuple: Union[Type, Tuple[Type, ...]], postOrder=True):
        """
        Iterate tuples (parent, childNodes), child nodes are filtered for a specific class using cls_or_tuple parameter
        :attention: if nodes are added or removed from parent it breaks the iterator, nodes can be added but the child
            node iterator will not reflect it
        """
        if not postOrder:
            childNodeIt = (n for n in self.subNodes if isinstance(n, cls_or_tuple))
            yield (self, childNodeIt)

        itTy = NODE_ITERATION_TYPE.ONLY_PARENT_POSTORDER if postOrder else NODE_ITERATION_TYPE.ONLY_PARENT_PREORDER
        for elm in self.iterAllNodesFlat(itTy):
            childNodeIt = (n for n in elm.subNodes if isinstance(n, cls_or_tuple))
            yield (elm, childNodeIt)

        if postOrder:
            childNodeIt = (n for n in self.subNodes if isinstance(n, cls_or_tuple))
            yield (self, childNodeIt)

    def filterNodesUsingRemovedSet(self, recursive=False):
        removed = self.builder._removedNodes
        changed = bool(removed)
        self.filterNodesUsingSet(removed, recursive=False)
        if recursive:
            for n in self.subNodes:
                n: HlsNetNode
                if getattr(n, "subNodes", None):
                    changed |= n.filterNodesUsingRemovedSet(recursive=recursive)
        return changed

    def filterNodesUsingSet(self, removed: Set[HlsNetNode], recursive=False, clearRemoved=True):
        if removed:
            self.subNodes[:] = (n for n in self.subNodes if n not in removed)
            if recursive:
                for n in self.iterAllNodes():
                    n.filterNodesUsingSet(removed, recursive=recursive, clearRemoved=False)

            if clearRemoved:
                removed.clear()

    def setupNetlistListeners(self,
                              beforeNodeAddedListener: Callable[[object, Union[slice, int], Union[HlsNetNode, ObservableListRm]], None],
                              beforeInputDriveUpdate: Callable[[object, Union[slice, int], Union[HlsNetNodeOut, None, ObservableListRm]], None],
                              beforeOutputUpdate: Callable[[object, Union[slice, int], Union[HlsNetNodeOut, None, ObservableListRm]], None]
                              ):
        self.subNodes._setObserver(beforeNodeAddedListener, None)

        for n in self.iterAllNodes():
            if n._isMarkedRemoved:
                continue
            n.dependsOn._setObserver(beforeInputDriveUpdate, n)
            n._outputs._setObserver(beforeOutputUpdate, n)

    def dropNetlistListeners(self):
        self.subNodes._setObserver(None, None)

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

    def _computeSchedulingClockWindowOffsets(self, others: List[Self]):
        offsetsOfOthers: List[int] = []
        clkPeriod = self.normalizedClkPeriod
        _, selfOffset = self.scheduler.getSchedulingMinTime(clkPeriod)
        assert selfOffset == 0, (self, selfOffset)
        for other in others:
            assert other.normalizedClkPeriod == clkPeriod
            _, firstClkI = other.scheduler.getSchedulingMinTime(self.normalizedClkPeriod)
            if selfOffset == 0:
                if firstClkI < 0:
                    # add time of self to make sure other will start at 0
                    selfOffset += -firstClkI
                    offsetsOfOthers += [o + -firstClkI for o in offsetsOfOthers]
                    offsetsOfOthers.append(-firstClkI)
                else:
                    offsetsOfOthers.append(selfOffset)
            else:
                otherOffsetUnderlap = selfOffset + firstClkI
                if otherOffsetUnderlap < 0:
                    # the negative offset of other is so large that it is necessary to also shift the current schedule

                    # add time of self to make sure other will start at 0
                    selfOffset += -otherOffsetUnderlap
                    offsetsOfOthers += [o + -otherOffsetUnderlap for o in offsetsOfOthers]

                    # add time of other to make sure it will start at 0
                    offsetsOfOthers.append(-firstClkI)
                else:
                    # other will be moved ad self was
                    offsetsOfOthers.append(selfOffset)

        assert len(others) == len(offsetsOfOthers)
        return selfOffset, offsetsOfOthers

    def _mergeResourceConstraints(self, otherResources: SchedulingResourceConstraints):
        constr = self.scheduler.resourceUsage.resourceConstraints
        for k, v in otherResources.items():
            cur = constr.get(k, 0)
            constr[k] = cur + v

    def merge(self, hwIOMeta: Dict[HwIO, HwIOMeta], others: Sequence[Self]):
        """
        Merge nodes of the other netlists to this one
        """
        nodesPerIO: OrderedDict[HwIO, List[Union[HlsNetNodeRead, HlsNetNodeWrite]]] = {}
        # maxOpsForIO: Dict[HwIO, int] = {}
        hwIoUserNetlists: Dict[HwIO, List[HlsNetlistCtx]] = {}

        for n in self.iterAllNodesFlat(NODE_ITERATION_TYPE.PREORDER):
            if isinstance(n, HlsNetNodeWrite):
                hwio = n.dst
            elif isinstance(n, HlsNetNodeRead):
                hwio = n.src
            else:
                continue

            if hwio is None:
                continue  # this one will be generated on demand and is guaranteed that there will be correct number of IOs per clock

            hwioUsers = hwIoUserNetlists.get(hwio, None)
            if hwioUsers is None:
                hwIoUserNetlists[hwio] = [self, ]

            ioList = nodesPerIO.get(hwio, None)
            if ioList is None:
                # maxOpsForIO[hwio] = n.maxIosPerClk
                ioList = nodesPerIO[hwio] = []

            ioList.append(n)

        clkPeriod = self.normalizedClkPeriod
        selfOffset, offsetsOfOthers = self._computeSchedulingClockWindowOffsets(others)
        if selfOffset != 0:
            self.scheduler.moveSchedulingTime(selfOffset, clkPeriod)

        for other, otherOffset in zip(others, offsetsOfOthers):
            assert other is not self
            idOffset = self._uniqNodeCntr
            iosSeenInThisNetlist: Set[HwIO] = set()
            if otherOffset != 0:
                other.scheduler.moveSchedulingTime(otherOffset, clkPeriod)

            for n in other.iterAllNodesFlat(NODE_ITERATION_TYPE.PREORDER):
                n: HlsNetNode
                n.netlist = self
                n._id += idOffset

                if isinstance(n, HlsNetNodeWrite):
                    if n.associatedRead is not None:
                        continue  # if it is already associated with something thread local it is not IO
                    isRead = False
                    hwio = n.dst
                elif isinstance(n, HlsNetNodeRead):
                    if n.associatedWrite is not None:
                        continue
                    isRead = True
                    hwio = n.src
                else:
                    continue

                if hwio is None:
                    # this is the case for on demand generated IO which should have be only
                    # thread local or nodes should be already associated
                    continue

                if hwio not in iosSeenInThisNetlist:
                    hwioUsers = hwIoUserNetlists.get(hwio, None)
                    if hwioUsers is None:
                        hwIoUserNetlists[hwio] = [other, ]
                    else:
                        hwioUsers.append(other)
                    # seen first time means that we should add maxIosPerClk
                    ioList = nodesPerIO.get(hwio, None)
                    if ioList is None:
                        # this IO is globally first seen
                        # newMaxOpsPerClk = maxOpsForIO[hwio, 0] = n.maxIosPerClk
                        ioList = nodesPerIO[hwio] = [n]
                    else:
                        # this IO was used in some other netlist
                        # newMaxOpsPerClk = maxOpsForIO.get(hwio, 0) + n.maxIosPerClk
                        # maxOpsForIO[hwio] = newMaxOpsPerClk
                        ioList.append(n)

                    # for _n in ioList:
                    #    _n.maxIosPerClk = newMaxOpsPerClk

                else:
                    ioList = nodesPerIO[hwio]
                    # n.maxIosPerClk = maxOpsForIO[hwio]
                    ioList.append(n)

                # [todo] association of backedges
                if isRead:
                    for _n in ioList:
                        if isinstance(_n, HlsNetNodeWrite) and _n.associatedRead is None and _n.scheduledZero <= n.scheduledZero:
                            _n.associateRead(n)
                            break

                else:
                    meta: Optional[HwIOMeta] = hwIOMeta.get(hwio, None)
                    for _n in ioList:
                        if isinstance(_n, HlsNetNodeRead) and _n.associatedWrite is None and _n.scheduledZero >= n.scheduledZero:
                            n.associateRead(_n)
                            if meta is not None:
                                _n.channelInitValues = meta.channelInit
                            break
            self.subNodes.extend(other.subNodes)
            self._uniqNodeCntr += other._uniqNodeCntr
            self._mergeResourceConstraints(other.scheduler.resourceUsage.resourceConstraints)
            self.scheduler.resourceUsage.merge(other.scheduler.resourceUsage)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__:s} {self.label:s}>"


class HlsNetlistChannels():

    def __init__(self, hwIOMeta: Dict[HwIO, HwIOMeta]):
        self.hwIOMeta = hwIOMeta
        self.nodesPerIO: OrderedDict[HwIO, List[Union[HlsNetNodeRead, HlsNetNodeWrite]]] = {}
        self.hwIoUserNetlists: Dict[HwIO, List[HlsNetlistCtx]] = {}
        self.alreadyAssociated: Set[Union[HlsNetNodeRead, HlsNetNodeWrite]] = set()

    def propagateChannelTimingConstraints(self, netlist: HlsNetlistCtx):
        hwIoUserNetlists = self.hwIoUserNetlists
        nodesPerIO = self.nodesPerIO

        hwiosSeenInThisNetlist: Set[HwIO] = set()
        for n in netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.PREORDER):
            if isinstance(n, HlsNetNodeWrite):
                if n.associatedRead is not None:
                    continue  # if it is already associated with something thread local it is not IO
                isRead = False
                hwio = n.dst
            elif isinstance(n, HlsNetNodeRead):
                if n.associatedWrite is not None:
                    continue
                isRead = True
                hwio = n.src
            else:
                continue

            if hwio is None:
                continue  # this one will be generated on demand and is guaranteed that there will be correct number of IOs per clock

            hwioUsers = hwIoUserNetlists.get(hwio, None)
            if hwioUsers is None:
                hwIoUserNetlists[hwio] = [self, ]
                hwiosSeenInThisNetlist.add(hwio)
            elif hwio not in hwiosSeenInThisNetlist:
                hwioUsers.append(hwio)
                hwiosSeenInThisNetlist.add(hwio)

            ioList = nodesPerIO.get(hwio, None)
            if ioList is None:
                ioList = nodesPerIO[hwio] = []

            meta: Optional[HwIOMeta] = self.hwIOMeta.get(hwio, None)
            if meta is not None:
                if meta.mayBecomeBackedge:
                    continue  # it is not required to constrain scheduling

            # propagate scheduling constraints
            isScheduled = n.scheduledZero is not None
            if isRead:
                for _n in ioList:
                    if isinstance(_n, HlsNetNodeWrite):
                        assert  _n.associatedRead is None, _n
                        if isScheduled and _n.scheduledZero is None:
                            _n.scheduledZeroMax = n.scheduledZero
                            break
                        elif not isScheduled and _n.scheduledZero is not None:
                            n.scheduledZeroMin = _n.scheduledZero
                            break
            else:
                for _n in ioList:
                    if isinstance(_n, HlsNetNodeRead):
                        assert  _n.associatedWrite is None, _n
                        if isScheduled and _n.scheduledZero is None:
                            _n.scheduledZeroMin = n.scheduledZero
                            break
                        elif not isScheduled and _n.scheduledZero is not None:
                            n.scheduledZeroMax = _n.scheduledZero
                            break

            ioList.append(n)

    def assertAllResolved(self):
        unresolved = []
        hwIoUserNetlists = self.hwIoUserNetlists
        for hwIo, ioList in self.nodesPerIO.items():
            if len(hwIoUserNetlists[hwIo]) > 1:
                for n in ioList:
                    if isinstance(n, HlsNetNodeRead):
                        if n.associatedWrite is None:
                            unresolved.append(n)
                    elif isinstance(n, HlsNetNodeWrite):
                        if n.associatedRead is None:
                            unresolved.append(n)

                if unresolved:
                    raise UnresolvedAssociationOfChannelPorts(hwIo, unresolved)


class UnresolvedAssociationOfChannelPorts(AssertionError):
    """
    Raised when there is a hwio connecting multiple netlists but it was not possible
    to resolve which port nodes in netlist are associated together.
    """

    def __init__(self, hwIo: HwIO, unresolvedIos: List[Union[HlsNetNodeRead, HlsNetNodeWrite]]):
        self.args = (hwIo, unresolvedIos)

    def __str__(self) -> str:
        buff = [f"<{self.__class__.__name__}\n"]
        hwIo, ioList = self.args
        try:
            buff.append(repr(hwIo))
        except:
            buff.append(f"<faulty HwIO instance> 0x{id(hwIo)} {hwIo.__class__}")
        buff.append("\n")
        for io in ioList:
            io: Union[HlsNetNodeRead, HlsNetNodeWrite]
            try:
                buff.append(f"{io.scheduledZero:6d} {repr(io):s}\n")
            except:
                buff.append(f"       <brokenNode {io._id:d}>\n")
        buff.append(">")
        return "".join(buff)
