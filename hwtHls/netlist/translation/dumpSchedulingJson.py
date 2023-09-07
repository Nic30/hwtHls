from collections import deque
from io import StringIO
import json
from typing import Dict, List, Optional, Set, Tuple

from hwt.hdl.operatorDefs import OpDefinition
from hwt.hdl.types.bitsVal import BitsVal
from hwt.hdl.types.sliceVal import HSliceVal
from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.interface import Interface
from hwtHls.io.bram import HlsNetNodeWriteBramCmd
from hwtHls.netlist.analysis.schedule import HlsNetlistAnalysisPassRunScheduler
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.aggregate import HlsNetNodeAggregate
from hwtHls.netlist.nodes.backedge import HlsNetNodeWriteBackedge
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.orderable import HVoidOrdering, HVoidExternData
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.readSync import HlsNetNodeReadSync
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from hwtHls.platform.fileUtils import OutputStreamGetter


class TimelineItem():
    """
    A container of data for row in timeline graph.

    """
    BRIGHT_COLORS = {"white", "lime", "plum", "lightblue", "lightlime", "yellow"}

    def __init__(self, id_: int, label:str, row: int, start:float, end:float, color:str):
        self.id = id_
        self.label = label
        self.row = row
        self.start = start
        self.end = end
        self.color = color
        self.textColor = "black" if color in self.BRIGHT_COLORS else "white"
        self.portsIn: List[Tuple[float, str, TimelineItem, int, str]] = []  # tuples (abs. time, name, dependency TimelineItem, dependency port index, link color)
        self.portsOut: List[Tuple[float, str]] = []  # tuples (abs. time, name)
        self.genericDeps: UniqList[TimelineItem] = UniqList()

    def toJson(self):
        return {
            "id": self.id,
            "label": self.label,
            "row": self.row,
            "start": round(self.start, 2),
            "end": round(self.end, 2),
            "color": self.color,
            "textColor": self.textColor,
            "portsIn": [(round(t, 2), name if name else name, dep.id, depOutI, linkColor) for t, name, dep, depOutI, linkColor in self.portsIn],
            "portsOut": [(round(t, 2), name) for (t, name) in self.portsOut],
            "genericDeps": [d.id for d in self.genericDeps],
        }


def _mkPortOut(time: float, name:str):
    return (time, name)


def _mkPortIn(arrivalTime: float, name:str, dep: TimelineItem, depOutI: int, color: str):
    return (arrivalTime, name, dep, depOutI, color)


def _toJson(data: List[TimelineItem], clkPeriod: float  # , minStartTime: float, maxEndTime: float
            ):
    return {
        "data": [d.toJson() for d in data],
        "clkPeriod": clkPeriod,
        # "minStartTime": minStartTime,
        # "maxEndTime": maxEndTime,
    }


class HwtHlsNetlistToTimelineJson():
    """
    Generate a timeline (Gantt) diagram of how operations in circuit are scheduled in time.

    :ivar time_scale: Specified how to format time numbers in output.
    :ivar min_duration: minimum width of boexes representing operations
    """

    def __init__(self, normalizedClkPeriod: int, resolution: float, expandCompositeNodes=False):
        self.objToJsonObj: Dict[HlsNetNode, TimelineItem] = {}
        self.jsonObjs: List[TimelineItem] = []
        self.rowOccupiedRanges: List[List[Tuple[float, float]]] = [[], ]
        self.time_scale = resolution / 1e-9  # to ns
        self.clkPeriod = self.time_scale * normalizedClkPeriod
        self.min_duration = 0.05 * normalizedClkPeriod * self.time_scale
        self.expandCompositeNodes = expandCompositeNodes

    def _findClosestNonOccupiedRow(self, currentRowIndex, start, end) -> Tuple[int, int]:
        """
        :return: tuple index of row and index in rowOccupiedRanges[rowI] where to insert
        """
        rowI = currentRowIndex
        distance = 0
        rowOccupiedRanges = self.rowOccupiedRanges
        searchUp = False
        while True:
            if rowI > len(rowOccupiedRanges) - 1:
                return (rowI, 0)  # place in a newly generated empty row

            row = rowOccupiedRanges[rowI]
            if not row:
                return (rowI, 0)  # place into an empty row

            for i, (otherStart, otherEnd) in enumerate(row):
                if i == 0 and end < otherStart:
                    # found place before this sequence
                    return (rowI, i)

                if otherEnd < start:
                    # found end of sequence where it may be possible to place this item
                    if len(row) - 1 == i:  # if this is last item
                        return (rowI, i + 1)
                    else:
                        nextStart, _ = row[i + 1]
                        if end < nextStart:
                            # can place after this item because there is enough space behind it
                            return (rowI, i + 1)
                        else:
                            break  # there is something colliding, we have to move on other row

            if row[-1][1] < start:
                return (rowI, len(row))  # place behind whole row

            # seach up first then search down, then incr. distance and search up again
            if searchUp:
                searchUp = False
                rowI = currentRowIndex + distance
            else:
                distance += 1
                if currentRowIndex - distance >= 0:
                    searchUp = True
                    rowI = currentRowIndex - distance
                else:
                    rowI = currentRowIndex + distance

    @staticmethod
    def _iterateUsersTransitively(n: HlsNetNode, seen: Set[HlsNetNode]):
        if n in seen:
            return
        toSearch = deque((n,))
        while toSearch:
            n = toSearch.popleft()
            if n in seen:
                continue
            seen.add(n)
            yield n

            for uses in n.usedBy:
                for u in uses:
                    if u.obj in seen:
                        continue
                    toSearch.append(u.obj)

    def translateNodeToTimelineItemTransitively(self,
                                       obj: HlsNetNode,
                                       ioGroupIds: Dict[Interface, int],
                                       nodesFlat: List[HlsNetNode],
                                       compositeNodes: Set[HlsNetNodeAggregate],
                                       seenNodes: Set[HlsNetNode]):
        if self.expandCompositeNodes and isinstance(obj, HlsNetNodeAggregate):
            compositeNodes.add(obj)
            for subNode in obj._subNodes:
                for n in self._iterateUsersTransitively(subNode, seenNodes):
                    self.translateNodeToTimelineItem(n, ioGroupIds)
                    nodesFlat.append(subNode)
        else:
            for n in self._iterateUsersTransitively(obj, seenNodes):
                self.translateNodeToTimelineItem(n, ioGroupIds)
                nodesFlat.append(n)

    def translateNodeToTimelineItem(self, obj: HlsNetNode, io_group_ids: Dict[Interface, int]):
        if obj.scheduledIn:
            start = min(obj.scheduledIn)
        else:
            assert obj.scheduledOut is not None, (obj, "node was not scheduled so it is not possible to add int into output graph")
            assert obj.scheduledOut, (obj, "does not have any port")
            start = max(obj.scheduledOut)

        if obj.scheduledOut:
            end = max(obj.scheduledOut)
        else:
            end = start

        start *= self.time_scale
        end *= self.time_scale

        assert start <= end, (start, end, obj)
        duration = end - start
        if duration < self.min_duration:
            to_add = self.min_duration - duration
            start -= to_add / 2
            end += to_add / 2

        connectedNodesRows = []
        for dep in obj.dependsOn:
            depJson = self.objToJsonObj.get(dep.obj, None)
            if depJson is not None:
                depJson:TimelineItem
                connectedNodesRows.append(depJson.row)

        for users in obj.usedBy:
            for u in users:
                uJson = self.objToJsonObj.get(u.obj, None)
                if uJson is not None:
                    uJson:TimelineItem
                    connectedNodesRows.append(uJson.row)

        if connectedNodesRows:
            objGroupId = int(sum(connectedNodesRows) // len(connectedNodesRows))
        else:
            objGroupId = len(self.rowOccupiedRanges) - 1

        objGroupId, inRowIndex = self._findClosestNonOccupiedRow(objGroupId, start, end)
        color = "white"
        if isinstance(obj, HlsNetNodeOperator):
            label = f"{obj.operator.id if isinstance(obj.operator, OpDefinition) else str(obj.operator)} {obj._id:d}"

        elif isinstance(obj, HlsNetNodeWrite):
            name = obj.name
            if not name:
                name = obj._getInterfaceName(obj.dst)
            if isinstance(obj, HlsNetNodeWriteBramCmd):
                label = f"{name:s}.write_cmd({obj.cmd})  {obj._id:d}"
            else:
                label = f"{name:s}.write()  {obj._id:d}"

            if isinstance(obj, HlsNetNodeWriteBackedge):
                objGroupId = io_group_ids.setdefault(obj.associatedRead.src if obj.associatedRead is not None else obj.dst, objGroupId)
                if obj.channelInitValues:
                    label = f"{label:s} init:{obj.channelInitValues}"
            color = "lime"

        elif isinstance(obj, HlsNetNodeRead):
            name = obj.name
            if not name:
                name = obj._getInterfaceName(obj.src) if obj.src is not None else None
            label = f"{name:s}.read()  {obj._id:d}"
            objGroupId = io_group_ids.setdefault(obj.src, objGroupId)
            color = "lime"

        elif isinstance(obj, HlsNetNodeConst):
            val = obj.val
            if isinstance(val, BitsVal):
                if val._is_full_valid():
                    label = "0x%x" % int(val)
                elif val.vld_mask == 0:
                    label = "X"
                else:
                    label = repr(val)
            elif isinstance(val, HSliceVal):
                if int(val.val.step) == -1:
                    label = f"{int(val.val.start)}:{int(val.val.stop)}"
                else:
                    label = repr(val)
            else:
                label = repr(val)

            color = "plum"

        elif isinstance(obj, HlsNetNodeExplicitSync):
            label = f"{obj.__class__.__name__:s}  {obj._id:d}"
            color = "lightblue"
        else:
            if isinstance(obj, (HlsNetNodeExplicitSync, HlsNetNodeReadSync)):
                color = "yellow"
            label = repr(obj)

        jObj = TimelineItem(obj._id, label, objGroupId, start, end, color)
        self.jsonObjs.append(jObj)
        self.objToJsonObj[obj] = jObj
        if len(self.rowOccupiedRanges) < objGroupId + 1:
            self.rowOccupiedRanges.extend([] for _ in range(objGroupId - len(self.rowOccupiedRanges) + 1))
        self.rowOccupiedRanges[objGroupId].insert(inRowIndex, (start, end))

    def iterAtomicNodes(self, n: HlsNetNode):
        if isinstance(n, HlsNetNodeAggregate):
            for subNode in n._subNodes:
                yield from self.iterAtomicNodes(subNode)
        else:
            yield n

    def construct(self, nodes: List[HlsNetNode]):
        jsonObjs = self.jsonObjs
        objToJsonObj = self.objToJsonObj
        ioGroupIds: Dict[Interface, int] = {}
        nodesFlat = []
        compositeNodes: Set[HlsNetNodeAggregate] = set()
        containerOfNode: Dict[HlsNetNode, HlsNetNodeAggregate] = {}
        if not self.expandCompositeNodes:
            for n in nodes:
                if isinstance(n, HlsNetNodeAggregate):
                    for subNode in self.iterAtomicNodes(n):
                        containerOfNode[subNode] = n

        seenNodes = set()
        for obj in nodes:
            self.translateNodeToTimelineItemTransitively(obj, ioGroupIds, nodesFlat, compositeNodes, seenNodes)

        for (jObj, obj) in zip(jsonObjs, nodesFlat):
            jObj: TimelineItem
            obj: HlsNetNode
            # convert output ports
            for t, o in zip(obj.scheduledOut, obj._outputs):
                jObj.portsOut.append(_mkPortOut(t * self.time_scale, o.name))

            # convert input ports and its links
            for t, dep, i in zip(obj.scheduledIn, obj.dependsOn, obj._inputs):
                depObj = dep.obj
                while depObj in compositeNodes:
                    dep = depObj._outputsInside[dep.out_i].dependsOn[0]
                    depObj = dep.obj

                depOutI = dep.out_i
                color = 'lime' if dep._dtype is HVoidOrdering else 'yellow' if dep._dtype is HVoidExternData else 'white'
                depJsonObj = objToJsonObj[depObj]
                jObj.portsIn.append(_mkPortIn(t * self.time_scale, i.name, depJsonObj, depOutI, color))

            # convert other logical connections which are not done trough ports
            for bdep_obj in obj.debug_iter_shadow_connection_dst():
                if not self.expandCompositeNodes:
                    bdep_obj = containerOfNode.get(bdep_obj, bdep_obj)
                try:
                    bdep = objToJsonObj[bdep_obj]
                except KeyError:
                    raise AssertionError("debug_iter_shadow_connection_dst of ", obj, " yield an object which is not in all nodes", bdep_obj)
                bdep.genericDeps.append(jObj)

    def saveJson(self, file: StringIO):
        j = self.jsonObjs
        json.dump(_toJson(j, self.clkPeriod), file)


class HlsNetlistPassDumpSchedulingJson(HlsNetlistPass):

    def __init__(self, outStreamGetter:Optional[OutputStreamGetter]=None, expandCompositeNodes=False):
        self.outStreamGetter = outStreamGetter
        self.expandCompositeNodes = expandCompositeNodes

    def apply(self, hls: "HlsScope", netlist: HlsNetlistCtx):
        netlist.getAnalysis(HlsNetlistAnalysisPassRunScheduler)
        to_timeline = HwtHlsNetlistToTimelineJson(netlist.normalizedClkPeriod,
                                              netlist.scheduler.resolution,
                                              expandCompositeNodes=self.expandCompositeNodes)
        to_timeline.construct(list(netlist.iterAllNodes()))
        if self.outStreamGetter is not None:
            out, doClose = self.outStreamGetter(netlist.label)
            try:
                to_timeline.saveJson(out)
            finally:
                if doClose:
                    out.close()
        else:
            assert self.auto_open, "Must be True because we can not show figure without opening it"
            to_timeline.show()

