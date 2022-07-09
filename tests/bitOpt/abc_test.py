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
        d = a ^ b & a & a ^ 1
        e = a._ternary(b, d)
        
        toAig = RtlNetlistToAbcAig()        
        f, net, aig = toAig.translate([a, b, c], [
            d,      # 0
            e,      # 1
            a,      # 2
            a | b,  # 3
            ~a,     # 4
            a & ~a, # 5
            a | ~a, # 6
            ~(a | b | c) # 7
            ])
        net = abcCmd_resyn2(net)
        net = abcCmd_compress2(net)
        toRtl = AbcAigToRtlNetlist(f, net, aig)
        res = toRtl.translate()
        f.DeleteAllNetworks()
        self.assertSequenceEqual(res, [
            ~(a & ~b), # 0
            ~(a & ~b), # 1 
            a,         # 2
            a | b,     # 3
            ~a,        # 4
            BIT.from_py(0), # 5
            BIT.from_py(1), # 6
            ~c & (~a & ~b)])  # 7
        

if __name__ == "__main__":
    suite = unittest.TestSuite()
    # suite.addTest(AbcTC('testFromRtlNetlistAndBack'))
    suite.addTest(unittest.makeSuite(AbcTC))
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
