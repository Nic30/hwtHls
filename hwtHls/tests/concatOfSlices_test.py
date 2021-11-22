
import unittest

from hwt.hdl.types.bits import Bits
from hwt.hdl.types.defs import BIT
from hwt.synthesizer.rtlLevel.netlist import RtlNetlist
from hwtHls.ssa.transformation.utils.concatOfSlices import ConcatOfSlices


class ConcatOfSlicesTC(unittest.TestCase):

    def testConstruct(self):
        n = RtlNetlist()
        a = n.sig("a", BIT)
        b = n.sig("b", BIT)
        c = n.sig("c", BIT)

        conc0 = ConcatOfSlices((a, b, c))
        self.assertEqual(conc0.bit_length, 3)
        self.assertEqual(len(conc0.slices), 3)

    def testConcat(self):
        n = RtlNetlist()
        a = n.sig("a", BIT)
        b = n.sig("b", Bits(2))
        c = n.sig("c", Bits(3))

        d = n.sig("d", BIT)

        conc0 = ConcatOfSlices((a, b, c))
        conc1 = ConcatOfSlices((d,))
        conc2 = conc0.concat(conc1)

        self.assertEqual(conc2.bit_length, 1 + 2 + 3 + 1)
        self.assertSequenceEqual(conc2.slices, ((a, 1, 0), (b, 2, 0), (c, 3, 0), (d, 1, 0)))

    def testSliceErrors(self):
        n = RtlNetlist()
        a = n.sig("a", BIT)
        b = n.sig("b", Bits(2))
        c = n.sig("c", Bits(3))

        conc0 = ConcatOfSlices((a, b, c))
        with self.assertRaises(IndexError):
            conc0.slice(0, 0)
        with self.assertRaises(IndexError):
            conc0.slice(1, -1)
        with self.assertRaises(IndexError):
            conc0.slice(7, 0)

    def testSlice(self):
        n = RtlNetlist()
        a = n.sig("a", BIT)
        b = n.sig("b", Bits(2))
        c = n.sig("c", Bits(3))

        conc0 = ConcatOfSlices((a, b, c))

        s0 = conc0.slice(1, 0)
        self.assertSequenceEqual(s0.slices, ((c, 1, 0), ))

        s0 = conc0.slice(3, 1)
        self.assertSequenceEqual(s0.slices, ((c, 3, 1), ))

        s0 = conc0.slice(4, 2)
        self.assertSequenceEqual(s0.slices, ((b, 1, 0), (c, 3, 2), ))

        s0 = conc0.slice(6, 5)
        self.assertSequenceEqual(s0.slices, ((a, 1, 0), ))


if __name__ == '__main__':
    unittest.main()
