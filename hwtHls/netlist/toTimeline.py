from typing import Dict, List, Optional

from plotly import graph_objs as go
from plotly.graph_objs import Figure
import plotly.offline

from hwt.hdl.types.bitsVal import BitsVal
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.interfaceLevel.unitImplHelpers import getSignalName
from hwtHls.hlsStreamProc.ssa.translation.toHwtHlsNetlist.nodes.backwardEdge import HlsWriteBackwardEdge
from hwtHls.netlist.nodes.io import HlsWrite, HlsRead, HlsExplicitSyncNode
from hwtHls.netlist.nodes.ops import AbstractHlsOp, HlsOperation, HlsConst
import pandas as pd


# [todo] pandas is overkill in this case, rm if ploty does not have it as dependencies
class HwtHlsNetlistToTimeline():
    """
    Generate a timeline (Gantt) diagram of how operations in curcuti are scheduled in time.
    """

    def __init__(self, clk_period: float):
        self.obj_to_row: Dict[AbstractHlsOp, dict] = {}
        self.rows: List[dict] = []
        self.time_scale = 1e9  # to ns
        self.clk_period = self.time_scale * clk_period
        self.min_duration = 0.5e-9 * self.time_scale  # minimum width of boexes representing operations

    def construct(self, nodes: List[AbstractHlsOp]):
        rows = self.rows
        io_group_ids: Dict[Interface, int] = {}
        for row_i, obj in enumerate(nodes):
            obj: AbstractHlsOp
            obj_group_id = row_i
            if obj.scheduledIn:
                start = min(obj.scheduledIn)
            else:
                start = max(obj.scheduledInEnd)

            if obj.scheduledInEnd:
                finish = max(obj.scheduledInEnd)
            else:
                finish = start

            start *= self.time_scale
            finish *= self.time_scale
            assert start <= finish, (start, finish, obj)
            duration = finish - start
            if duration < self.min_duration:
                to_add = self.min_duration - duration
                start -= to_add / 2
                finish += to_add / 2

            color = "purple"
            if isinstance(obj, HlsOperation):
                label = obj.operator.id

            elif isinstance(obj, HlsWrite):
                label = f"{getSignalName(obj.dst)}.write()"
                if isinstance(obj, HlsWriteBackwardEdge):
                    obj_group_id = io_group_ids.setdefault(obj.associated_read.src, obj_group_id)
                color = "green"

            elif isinstance(obj, HlsRead):
                label = f"{getSignalName(obj.src)}.read()"
                obj_group_id = io_group_ids.setdefault(obj.src, obj_group_id)
                color = "green"

            elif isinstance(obj, HlsConst):
                val = obj.val
                if isinstance(val, BitsVal):
                    if val._is_full_valid():
                        label = "0x%x" % int(val)
                    else:
                        label = repr(val)
                else:
                    label = repr(val)

            elif isinstance(obj, HlsExplicitSyncNode):
                label = obj.__class__.__name__

            else:
                label = repr(obj)

            row = {"label": label, "group": obj_group_id, "start":start, "finish": finish, "deps": [], "backward_deps": [], "color": color}
            rows.append(row)
            self.obj_to_row[obj] = (row, row_i)

        for row_i, (row, obj) in enumerate(zip(rows, nodes)):
            obj: AbstractHlsOp
            row["deps"].extend(self.obj_to_row[dep.obj][1] for dep in obj.dependsOn)
            for bdep_obj in obj.debug_iter_shadow_connection_dst():
                bdep = self.obj_to_row[bdep_obj][0]
                bdep["backward_deps"].append(row_i)

    def _draw_clock_boundaries(self, fig: Figure):
        clk_period = self.clk_period
        last_time = self.df["finish"].max() + clk_period
        i = 0.0
        row_cnt = len(self.rows)
        while i < last_time:
            fig.add_shape(
                x0=i, y0=0,
                x1=i, y1=row_cnt,
                line=dict(color="gray", dash='dash', width=2)
            )
            i += clk_period

    def _draw_arrow(self, fig: Figure, x0:float, y0:float, x1:float, y1:float, color: str):
        # assert x1 >= x0
        jobs_delta = x1 - x0
        # fig.add_shape(
        #    x0=x0, y0=startY,
        #    x1=x1, y1=endY,
        #    line=dict(color=color, width=2))
        if jobs_delta > 0 and y0 == y1:
            p = f"M {x0} {y0} L {x1} {y1}"
        else:
            if jobs_delta > 0:
                middleX = x0 + jobs_delta / 2
                p = f"M {x0} {y0} C {middleX} {y0}, {middleX} {y1}, {x1} {y1}"
            else:
                # x0 is on right, x1 on left
                p = f"M {x0} {y0} C {x0 + self.min_duration} {y0}, {x1-self.min_duration} {y1}, {x1} {y1}"
        fig.add_shape(
            type="path",
            path=p,
            line_color=color,
        )
        # # # horizontal line segment
        # fig.add_shape(
        #    x0=x0, y0=startY,
        #    x1=x0 + jobs_delta / 2, y1=startY,
        #    line=dict(color=color, width=2)
        # )
        # # # vertical line segment
        # fig.add_shape(
        #    x0=x0 + jobs_delta / 2, y0=startY,
        #    x1=x0 + jobs_delta / 2, y1=endY,
        #    line=dict(color="blue", width=2)
        # )
        # # # horizontal line segment
        # fig.add_shape(
        #    x0=x0 + jobs_delta / 2, y0=endY,
        #    x1=x1, y1=endY,
        #    line=dict(color=color, width=2)
        # )
        # Add shapes
        # fig.update_layout(
        #    shapes=[
        #        dict(type="line", xref="x", yref="y",
        #            x0=3, y0=0.5, x1=5, y1=0.8, line_width=3),
        #        dict(type="rect", xref="x2", yref='y2',
        #             x0=4, y0=2, x1=5, y1=6),
        #     ])

        # # draw an arrow
        fig.add_annotation(
            x=x1, y=y1,
            xref="x", yref="y",
            showarrow=True,
            ax=-10,
            ay=0,
            arrowwidth=2,
            arrowcolor=color,
            arrowhead=2,
        )

    def _draw_arrow_between_jobs(self, fig: Figure):
        df = self.df
        # # draw an arrow from the end of the first job to the start of the second job
        # # retrieve tick text and tick vals
        # job_yaxis_mapping = dict(zip(fig.layout.yaxis.ticktext, fig.layout.yaxis.tickvals))
        for _, second_job_dict in df.iterrows():
            endX = second_job_dict['start']
            endY = second_job_dict['group']

            for start_i in second_job_dict['deps']:
                first_job_dict = df.iloc[start_i]
                startX = first_job_dict['finish']
                startY = first_job_dict['group']
                self._draw_arrow(fig, startX, startY, endX, endY, "blue")

            for start_i in second_job_dict["backward_deps"]:
                first_job_dict = df.iloc[start_i]
                startX = first_job_dict['finish']
                startY = first_job_dict['group']
                self._draw_arrow(fig, startX, startY, endX, endY, "gray")

        return fig

    def _generate_fig(self):
        self.df: pd.DataFrame = pd.DataFrame(self.rows)
        df = self.df
        df['delta'] = df['finish'] - df['start']

        # https://plotly.com/python/bar-charts/
        bars = []
        for color, rows in df.groupby(by="color", sort=False):
            b = go.Bar(x=rows["delta"], base=rows["start"], y=rows["group"],
                       marker_color=color,
                       orientation='h',
                       customdata=rows["label"],
                       showlegend=False,
                       texttemplate="%{customdata}",
                       textangle=0,
                       textposition="inside",
                       insidetextanchor="middle",
                       hovertemplate="<br>".join([
                           "(%{base}, %{x}):",
                           " %{customdata}",
                       ]))
            bars.append(b)
        fig = Figure(bars, go.Layout(barmode='overlay'))

        fig.update_yaxes(title="Operations", autorange="reversed", visible=True, showticklabels=False)  # otherwise tasks are listed from the bottom up
        fig.update_xaxes(title="Time[ns]")
        self._draw_arrow_between_jobs(fig)
        self._draw_clock_boundaries(fig)
        return fig

    def show(self):
        fig = self._generate_fig()
        plotly.offline.iplot(fig)

    def save_html(self, filename, auto_open):
        fig = self._generate_fig()
        plotly.offline.plot(fig, filename=filename, auto_open=auto_open)


class RtlNetlistPassShowTimeline():

    def __init__(self, filename:Optional[str]=None, auto_open=False):
        self.filename = filename
        self.auto_open = auto_open

    def apply(self, to_hw: "SsaSegmentToHwPipeline"):
        to_timeline = HwtHlsNetlistToTimeline(to_hw.hls.clk_period)
        to_timeline.construct(to_hw.hls.inputs + to_hw.hls.nodes + to_hw.hls.outputs)
        if self.filename is not None:
            to_timeline.save_html(self.filename, self.auto_open)
        else:
            assert self.auto_open, "Must be True because we can not show figure without opening it"
            to_timeline.show()


if __name__ == "__main__":
    to_timeline = HwtHlsNetlistToTimeline()
    to_timeline.show()
