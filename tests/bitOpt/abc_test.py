import unittest

from hwt.hdl.types.defs import BIT
from hwt.synthesizer.rtlLevel.netlist import RtlNetlist
from hwtHls.netlist.abc.abcAigToRtlNetlist import AbcAigToRtlNetlist
from hwtHls.netlist.abc.optScripts import abcCmd_resyn2, abcCmd_compress2
from hwtHls.netlist.abc.rtlNetlistToAbcAig import RtlNetlistToAbcAig


class AbcTC(unittest.TestCase):

    def testFromRtlNetlistAndBack(self):
        hwtNet = RtlNetlist(None)
        a = hwtNet.sig("a")
        b = hwtNet.sig("b")
        c = hwtNet.sig("c")
        c1 = hwtNet.sig("c1")
        d = a ^ b & a & a ^ 1
        e = a._ternary(b, d)

        toAig = RtlNetlistToAbcAig()
        f, net, aig = toAig.translate([a, b, c, c1], [
            d,  # 0
            e,  # 1
            a,  # 2
            a | b,  # 3
            ~a,  # 4
            a & ~a,  # 5
            ~a & ~b, # 5b
            a | ~a,  # 6
            ~(a | b | c),  # 7
            ~(a | b | c | c1),  # 7b
            ~(a & b & c),  # 7c
            ~(a & b & c & c1),  # 7d
            a._eq(1),  # 8
            a._eq(0),  # 9
            a != 1,  # 10
            a != 0,  # 11
            (~a & (~b & ~c))._eq(0),  # 12
            ~((~a & ~b) & ~c),  # 13
            a | (~b | c),  # 14
            a & ~b,  # 15
            ~a & b,  # 16
            a & (~b | c),  # 17
            (a & b) | (c & ~b), # 18
            ])
        net = abcCmd_resyn2(net)
        net = abcCmd_compress2(net)
        toRtl = AbcAigToRtlNetlist(f, net, aig)
        res = toRtl.translate()
        f.DeleteAllNetworks()
        self.assertSequenceEqual(res, [
            ~a | b,  # 0
            ~a | b,  # 1
            a,  # 2
            a | b,  # 3
            ~a,  # 4
            BIT.from_py(0),  # 5
            ~(a | b), # 5b
            BIT.from_py(1),  # 6
            ~(c | a | b),  # 7
            ~(c1 | c | a | b),  # 7b
            ~(c & a & b),  # 7c
            ~(c1 & c & a & b ),  # 7d
            a,  # 8
            ~a,  # 9
            a ^ 1,  # 10
            a ^ 0,  # 11
            c | a | b,  # 12
            c | a | b,  # 13
            a | ~b | c,  # 14
            a & ~b,  # 15
            ~a & b,  # 16
            a & (~b | c),  # 17
            (a | ~b) & (b | c), # 18
            ])


if __name__ == "__main__":
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([AbcTC('testFromRtlNetlistAndBack')])
    suite = testLoader.loadTestsFromTestCase(AbcTC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)

