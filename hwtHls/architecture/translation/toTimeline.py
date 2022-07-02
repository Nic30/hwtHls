from math import inf, isfinite
from typing import  Optional

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwtHls.architecture.allocator import HlsAllocator
from hwtHls.architecture.architecturalElement import AllocatorArchitecturalElement
from hwtHls.architecture.connectionsOfStage import ConnectionsOfStage
from hwtHls.architecture.interArchElementNodeSharingAnalysis import InterArchElementNodeSharingAnalysis, \
    ValuePathSpecItem
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource
from hwtHls.netlist.analysis.schedule import HlsNetlistAnalysisPassRunScheduler
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.architecture.transformation.rtlArchPass import RtlArchPass
from hwtHls.netlist.translation.toTimeline import HwtHlsNetlistToTimeline, \
    TimelineRow
from hwtHls.platform.fileUtils import OutputStreamGetter


class HwtHlsNetlistToTimelineArchLevel(HwtHlsNetlistToTimeline):
    """
    Generate a timeline (Gantt) diagram of how architecture elements in circuit are scheduled in time.
    """

    def construct(self, allocator: HlsAllocator):
        rows = self.rows
        obj_to_row = self.obj_to_row
        time_scale: float = self.time_scale
        clkPeriod = self.clkPeriod
        for row_i, archElm in enumerate(allocator._archElements):
            archElm: AllocatorArchitecturalElement
            obj_group_id = row_i
            start = inf
            finish = 0.0
            for tirs in archElm.connections:
                tirs: ConnectionsOfStage
                for tir in tirs.signals:
                    tir: TimeIndependentRtlResource
                    if tir.timeOffset is not TimeIndependentRtlResource.INVARIANT_TIME:
                        start = min(start, tir.timeOffset)
                        finish = max(finish, tir.timeOffset + (len(tir.valuesInTime) - 1) * clkPeriod)
            if not isfinite(start):
                start = finish
                assert isfinite(finish)
            elif not isfinite(finish):
                assert isfinite(finish)

            start *= time_scale
            finish *= time_scale
            assert start <= finish, (start, finish, archElm)
            duration = finish - start
            if duration < self.min_duration:
                to_add = self.min_duration - duration
                start -= to_add / 2
                finish += to_add / 2

            color = "purple"
            label = " ".join([repr(archElm), ", ".join(f"{n._id}" for n in archElm.allNodes)])

            row = TimelineRow(label, obj_group_id, start, finish, color)
            rows.append(row)
            obj_to_row[archElm] = (row, row_i)

        iea: InterArchElementNodeSharingAnalysis = allocator._iea
        for o, i in iea.interElemConnections:
            srcElm = iea.getSrcElm(o)
            for dstElm in iea.ownerOfInput[i]:
                if srcElm is dstElm:
                    continue
                path = iea.explicitPathSpec.get((o, i, dstElm), None)
                if path is None:
                    dstRow: TimelineRow = obj_to_row[dstElm][0]
                    dstRow.deps.append((
                        obj_to_row[iea.ownerOfOutput[o]][1],
                        o.obj.scheduledOut[o.out_i] * time_scale,
                        iea.firstUseTimeOfOutInElem[(dstElm, o)] * time_scale,
                        o._dtype,
                    ))
                else:
                    # :note: from output through all path elements to input
                    # connect first element in path
                    dstRow: TimelineRow = obj_to_row[path[0].element][0]
                    srcRow = obj_to_row[iea.ownerOfOutput[o]][0]
                    dstRow.deps.append((
                            srcRow,
                            o.obj.scheduledOut[o.out_i] * time_scale,
                            path[0].beginTime * time_scale
                    ))
                    srcRow = dstRow
                    # connect rest of elements in path
                    for last, (pi, p) in iter_with_last(enumerate(path)):
                        p: ValuePathSpecItem
                        if last:
                            dstRow = obj_to_row[dstElm]
                            dstTime = iea.firstUseTimeOfOutInElem[(dstElm, o)]
                        else:
                            nextP = path[pi + 1]
                            dstRow = obj_to_row[nextP.element]
                            dstTime = nextP.beginTime

                        dstRow.deps.append((
                            srcRow,
                            p.endTime * time_scale,
                            dstTime * time_scale
                        ))
                        srcRow = dstRow

        #                    for t, dep in zip(obj.scheduledIn, obj.dependsOn))
        #    for bdep_obj in obj.debug_iter_shadow_connection_dst():
        #        bdep = obj_to_row[bdep_obj][0]
        #        bdep.backward_deps.append(row_i)


class RtlArchPassShowTimeline(RtlArchPass):

    def __init__(self, outStreamGetter:Optional[OutputStreamGetter]=None, auto_open=False, expandCompositeNodes=False):
        self.outStreamGetter = outStreamGetter
        self.auto_open = auto_open
        self.expandCompositeNodes = expandCompositeNodes

    def apply(self, hls: "HlsScope", netlist: HlsNetlistCtx):
        netlist.requestAnalysis(HlsNetlistAnalysisPassRunScheduler)

        to_timeline = HwtHlsNetlistToTimelineArchLevel(netlist.normalizedClkPeriod, netlist.scheduler.resolution, self.expandCompositeNodes)
        to_timeline.construct(netlist.allocator)
        if self.outStreamGetter is not None:
            out, doClose = self.outStreamGetter(netlist.label)
            try:
                to_timeline.save_html(out, self.auto_open)
            finally:
                if doClose:
                    out.close()
        else:
            assert self.auto_open, "Must be True because we can not show figure without opening it"
            to_timeline.show()


if __name__ == "__main__":
    to_timeline = HwtHlsNetlistToTimelineArchLevel()
    to_timeline.show()
