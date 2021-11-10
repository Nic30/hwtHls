from typing import Dict, List

import plotly.express
from plotly.graph_objs import Figure
import plotly.offline

from hwtHls.netlist.nodes.ops import AbstractHlsOp, HlsOperation, HlsConst
import pandas as pd
from hwtHls.netlist.nodes.io import HlsWrite, HlsRead, HlsExplicitSyncNode
from hwtHls.clk_math import epsilon
from hwt.hdl.types.bitsVal import BitsVal


class HwtHlsNetlistToTimeline():
    """

    """

    def __init__(self, clk_period: float):
        self.obj_to_row: Dict[AbstractHlsOp, dict] = {}
        self.rows: List[dict] = []
        self.time_scale = 1e9  # to ns
        self.clk_period = self.time_scale * clk_period
        self.min_duration = 0.5e-9 * self.time_scale  # minimum width of boexes representing operations

    def construct(self, nodes: List[AbstractHlsOp]):
        rows = self.rows
        for row_i, obj in enumerate(nodes):
            obj: AbstractHlsOp
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

            if isinstance(obj, HlsOperation):
                label = obj.operator.id
            elif isinstance(obj, HlsWrite):
                label = f"{obj.dst._name}.write()"
            elif isinstance(obj, HlsRead):
                label = f"{obj.src._name}.read()"
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

            row = {"Label": label, "Start":start, "Finish": finish, "Deps": []}
            rows.append(row)
            self.obj_to_row[obj] = (row, row_i)

        for row, obj in zip(rows, nodes):
            obj: AbstractHlsOp
            row["Deps"].extend(self.obj_to_row[dep.obj][1] for dep in obj.dependsOn)

    def _draw_clock_boundaries(self):
        clk_period = self.clk_period
        last_time = self.df["Finish"].max() + clk_period
        i = 0.0
        fig = self.fig
        row_cnt = len(self.rows)
        while i < last_time:
            fig.add_shape(
                x0=i, y0=0,
                x1=i, y1=row_cnt,
                line=dict(color="gray", dash='dash', width=2)
            )
            i += clk_period

    def _draw_arrow_between_jobs(self):
        df = self.df
        fig = self.fig
        # # draw an arrow from the end of the first job to the start of the second job
        # # retrieve tick text and tick vals
        # job_yaxis_mapping = dict(zip(fig.layout.yaxis.ticktext, fig.layout.yaxis.tickvals))
        for end_i, second_job_dict in df.iterrows():
            endX = second_job_dict['Start']
            endY = second_job_dict['Label']

            for start_i in second_job_dict['Deps']:
                first_job_dict = df.iloc[start_i]
                startX = first_job_dict['Finish']
                # startY = first_job_dict['Task']
                # assert endX >= startX
                # jobs_delta = endX - startX
                # middleX = startX + jobs_delta / 2
                # fig.add_shape(
                #    x0=startX, y0=startY,
                #    x1=endX, y1=endY,
                #    line=dict(color="blue", width=2))

                # p = f"M {startX} {start_i} C {middleX} {start_i}, {middleX} {end_i}, {endX} {end_i}"
                p = f"M {startX} {start_i} L {endX} {end_i}"
                fig.add_shape(
                    type="path",
                    path=p,
                    line_color="MediumPurple",
                )
                # # # horizontal line segment
                # fig.add_shape(
                #    x0=startX, y0=startY,
                #    x1=startX + jobs_delta / 2, y1=startY,
                #    line=dict(color="blue", width=2)
                # )
                # # # vertical line segment
                # fig.add_shape(
                #    x0=startX + jobs_delta / 2, y0=startY,
                #    x1=startX + jobs_delta / 2, y1=endY,
                #    line=dict(color="blue", width=2)
                # )
                # # # horizontal line segment
                # fig.add_shape(
                #    x0=startX + jobs_delta / 2, y0=endY,
                #    x1=endX, y1=endY,
                #    line=dict(color="blue", width=2)
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
                    x=endX, y=endY,
                    xref="x", yref="y",
                    showarrow=True,
                    ax=-10,
                    ay=0,
                    arrowwidth=2,
                    arrowcolor="blue",
                    arrowhead=2,
                )
        return fig

    def show(self):
        # self.rows = [
        #    dict(Task="Job A", id=0, Start=1.01, Finish=2.28, deps=[]),
        #    dict(Task="Job B", id=1, Start=3.05, Finish=4.15, deps=[0]),
        #    dict(Task="Job C", id=2, Start=5.01, Finish=6.30, deps=[1])
        # ]

        self.df: pd.DataFrame = pd.DataFrame(self.rows)
        df = self.df
        df['delta'] = df['Finish'] - df['Start']

        self.fig: Figure = plotly.express.timeline(df, x_start="Start", x_end="Finish", text="Label")
        fig = self.fig
        fig.update_yaxes(title="Operations", autorange="reversed", visible=True, showticklabels=False)  # otherwise tasks are listed from the bottom up

        fig.update_xaxes(title="Time[ns]")
        fig.layout.xaxis.type = 'linear'
        fig.data[0].x = df.delta.tolist()
        self._draw_arrow_between_jobs()
        self._draw_clock_boundaries()
        self.fig.show()

    def save_html(self, filename):
        plotly.offline.plot(self.fig, filename=filename)


if __name__ == "__main__":
    to_timeline = HwtHlsNetlistToTimeline()
    to_timeline.show()
