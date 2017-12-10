
import unittest

from hwt.hdl.operatorDefs import AllOps
from hwt.hdl.types.defs import BIT
from hwt.synthesizer.rtlLevel.netlist import RtlNetlist
from hwt.synthesizer.unit import Unit
from hwtHls.codeOps import HlsRead, HlsOperation, HlsWrite
from hwtHls.hls import Hls, link_nodes
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scheduler.list_schedueling import list_schedueling
from hwtHls.clk_math import start_clk, start_of_next_clk_period
from pprint import pprint


n = RtlNetlist("test")


def sig(name, t=BIT):
    return n.sig("sig", t)


def dummy_constrainFn(node, sched, suggestedStart, suggestedEnd, priv):
    return suggestedStart, suggestedEnd


class ListSchedueling_TC(unittest.TestCase):
    def setUp(self):
        u = Unit()
        u._targetPlatform = VirtualHlsPlatform()
        self.hls = Hls(u, freq=int(100e6))

    def simple_not(self):
        hls = self.hls
        a_in_sig = sig("a_in")
        a_out_sig = sig("a_out")

        a_in = HlsRead(hls, a_in_sig)
        a_not = HlsOperation(hls, AllOps.NOT, 1)
        link_nodes(a_in, a_not)
        a_out = HlsWrite(hls, 1, a_out_sig)
        link_nodes(a_not, a_out)
        for n in [a_in, a_not, a_out]:
            n.resolve_realization()

        return a_in, a_not, a_out

    def dual_and(self):
        hls = self.hls

        def and_op(prefix):
            a0_in_sig = sig(prefix + "0_in")
            a1_in_sig = sig(prefix + "1_in")
            a_out_sig = sig(prefix + "_out")

            a0_in = HlsRead(hls, a0_in_sig)
            a1_in = HlsRead(hls, a1_in_sig)

            a_and = HlsOperation(hls, AllOps.AND, 1)
            link_nodes(a0_in, a_and)
            link_nodes(a1_in, a_and)

            a_out = HlsWrite(hls, 1, a_out_sig)
            link_nodes(a_and, a_out)
            ops = [a0_in, a1_in, a_and, a_out]
            for n in ops:
                n.resolve_realization()
            return ops

        return and_op("a") + and_op("b")

    def test_simple_not(self):
        a_in, a_not, a_out = self.simple_not()

        def priorityFn(node):
            if node is a_in:
                return 0
            elif node is a_not:
                return 1
            elif node is a_out:
                return 2
            else:
                raise ValueError(node)

        sched = list_schedueling([a_in, ], [a_not, ], [a_out, ],
                                 dummy_constrainFn, priorityFn)
        ref = {
            a_in: (0, 0),
            a_not: (0, 1.2e-09),
            a_out: (1.2e-09, 1.2e-09),
        }
        self.assertDictEqual(sched, ref)

    def test_dual_and_simple(self):
        a0_in, a1_in, a_and, a_out, \
            b0_in, b1_in, b_and, b_out = self.dual_and()

        inputs = [a0_in, a1_in, b0_in, b1_in]
        nodes = [a_and, b_and]
        outputs = [a_out, b_out]

        def priorityFn(node):
            if node in inputs:
                return 0
            elif node in nodes:
                return 1
            elif node in outputs:
                return 2
            else:
                raise ValueError(node)

        sched = list_schedueling(inputs, nodes, outputs,
                                 dummy_constrainFn, priorityFn)
        ref = {a_in: (0, 0) for a_in in inputs}
        ref.update({op: (0, 1.2e-09) for op in nodes})
        ref.update({a_out: (1.2e-09, 1.2e-09) for a_out in outputs})
        self.assertDictEqual(sched, ref)

    def test_dual_and_constrained(self):
        a0_in, a1_in, a_and, a_out, \
            b0_in, b1_in, b_and, b_out = self.dual_and()
        clk_period = 1.2e-08

        def one_op_per_clk(node, sched, suggestedStart, suggestedEnd, priv):
            clk_index = start_clk(suggestedStart, clk_period)
            others_in_clk = priv.get(clk_index, set())
            isAllone = not (isinstance(node, HlsOperation) and others_in_clk)
            others_in_clk.add(node)

            if not isAllone:
                suggestedStart = start_of_next_clk_period(
                    suggestedStart, clk_period)
                suggestedEnd = suggestedStart + node.latency_pre + node.latency_post

            return suggestedStart, suggestedEnd

        inputs = [a0_in, a1_in, b0_in, b1_in]
        nodes = [a_and, b_and]
        outputs = [a_out, b_out]

        def priorityFn(node):
            if node in inputs:
                return 0
            elif node in nodes:
                return 1
            elif node in outputs:
                return 2
            else:
                raise ValueError(node)

        sched = list_schedueling(inputs, nodes, outputs,
                                 one_op_per_clk, priorityFn)
        ref = {a_in: (0, 0)
               for a_in in inputs}
        ref.update({op: (0, 1.2e-09)
                    for op in nodes})
        ref.update({a_out: (1.2e-09, 1.2e-09)
                    for a_out in outputs})

        self.assertDictEqual(sched, ref)


if __name__ == '__main__':
    unittest.main()
