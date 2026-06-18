from hwt.serializer.combLoopAnalyzer import CombLoopAnalyzer, freeze_set_of_sets
from hwt.simulator.simTestCase import SimTestCase


class BaseIrMirRtl_TC(SimTestCase):
    """
    This class contains utility methods for testing simple circuit at LLVM IR, MIR and RTL level.
    """

    def _test_no_comb_loops(self):
        s = CombLoopAnalyzer()
        s.visit_HwModule(self.dut)
        comb_loops = freeze_set_of_sets(s.report())
        msg_buff = []
        for loop in comb_loops:
            msg_buff.append(10 * "-")
            for s in loop:
                msg_buff.append(str(s.resolve()[1:]))

        self.assertEqual(comb_loops, frozenset(), msg="\n".join(msg_buff))
