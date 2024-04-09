import unittest

from hwt.hdl.types.defs import BIT
from hwt.synthesizer.rtlLevel.netlist import RtlNetlist
from hwtHls.netlist.abc.abcAigToRtlNetlist import AbcAigToRtlNetlist
from hwtHls.netlist.abc.abcCpp import Io_FileType_t
from hwtHls.netlist.abc.optScripts import abcCmd_resyn2, abcCmd_compress2
from hwtHls.netlist.abc.rtlNetlistToAbcAig import RtlNetlistToAbcAig
from hwtHls.architecture.transformation.controlLogicMinimize import RtlNetlistPassControlLogicMinimize
from typing import Dict


def generateAllBitPermutations(n):
    for i in range(1 << n):
        yield ((i >> bitIndex) & 1 for bitIndex in range(n))


class AbcTC(unittest.TestCase):

    def testFromRtlNetlistAndBack(self):
        hwtNet = RtlNetlist(None)
        a = hwtNet.sig("a")
        b = hwtNet.sig("b")
        c = hwtNet.sig("c")
        c1 = hwtNet.sig("c1")
        c2 = hwtNet.sig("c2")
        c3 = hwtNet.sig("c3")
        c4 = hwtNet.sig("c4")
        n1, n2, n3, n4, n5, n6, n7, n8, n9 = (hwtNet.sig(f"n{i}") for i in range(1, 10))

        d = a ^ b & a & a ^ 1
        e = a._ternary(b, d)

        def testOpt0and1(n1, n2, n3, n4, n5, n6, n7, n8, n9):
            new_n12 = n4 & n5
            new_n13 = n3 & ~n4
            new_n14 = ~new_n12 & ~new_n13
            new_n15 = n1 & ~new_n14
            new_n16 = ~n6 & new_n12
            new_n17 = ~n4  # & n9
            new_n18 = n4  # & n8
            new_n19 = new_n17 & ~new_n18
            new_n20 = n7 & ~new_n16
            new_n21 = ~new_n19 & new_n20
            n10 = ~new_n15 & new_n21
            n28 = new_n14 & new_n21
            return n10, n28

        e0, e1 = testOpt0and1(n1, n2, n3, n4, n5, n6, n7, n8, n9)
        exampleExpr = [
            d,  # 0
            e,  # 1
            a,  # 2
            a | b,  # 3
            ~a,  # 4
            a & ~a,  # 5
            ~a & ~b,  # 5b
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
            (a & b) | (c & ~b),  # 18
            (a | b) & c & c1 & ~c2,  # 19
            (a & c) | (b & ~c),  # 20
            (~a & b)._ternary(BIT.from_py(0), ~a),  # 21
            n1 | ~n4 | ~n5,
            e0,
            e1,
        ]
        exampleExprInputs = [a, b, c, c1, c2, c3, c4, n1, n2, n3, n4, n5, n6, n7, n8, n9]
        toAig = RtlNetlistToAbcAig()
        f, net, aig, ioMap = toAig.translate(exampleExprInputs, exampleExpr)
        net = abcCmd_resyn2(net)
        net = abcCmd_compress2(net)
        toRtl = AbcAigToRtlNetlist(f, net, aig, ioMap)
        res = tuple(newO for _, newO in toRtl.translate())
        f.DeleteAllNetworks()
        ref = [
            ~a | b,  # 0
            ~a | b,  # 1
            a,  # 2
            a | b,  # 3
            ~a,  # 4
            BIT.from_py(0),  # 5
            ~(a | b),  # 5b
            BIT.from_py(1),  # 6
            ~(c | a | b),  # 7
            ~(c1 | c | a | b),  # 7b
            ~(c & a & b),  # 7c
            ~(c1 & c & a & b),  # 7d
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
            (a | ~b) & (b | c),  # 18
            ~(~(a | b) | c2 | ~c | ~c1),  # 19
            (b | c) & (a | ~c),  # 20
            ~(a | b),  # 21
            ~n5 | n1 | ~n4,
            ~(~(~n1 | ~(n3 | n4) | n4 & ~n5) | n5 & ~n6 | ~n4 | ~n7),
            ~((n3 | n4) & (~n4 | n5) | n5 & ~n6 | ~n4 | ~n7),
        ]
        self.assertSequenceEqual(res, ref)
        for oOptimized, oInput, oExpected in zip(res, exampleExpr, ref):
#            print(">>>>>>>>>")
#            print("inp", oInput)
#            print("opt", oOptimized)
#            print("exp", oExpected)
            RtlNetlistPassControlLogicMinimize._verifyAbcExprEquivalence(exampleExprInputs, oOptimized, oInput)
            RtlNetlistPassControlLogicMinimize._verifyAbcExprEquivalence(exampleExprInputs, oInput, oExpected)

        # for x in range(4):
        #     _a = 0b01 & x
        #     _b = (0b10 & x) >> 1
        #     print(int(0 if (not _a and _b) else not _a),
        #           int(not (_a or _b)))
        #

    def test_largerExpression(self):
        # originally taken from AxiSPacketCopyByteByByte 1->2B unroll=None pipe0_st0_ack
        hwtNet = RtlNetlist(None)
        inputsRtl = tuple(hwtNet.sig(name) for name in (
            "rx_valid",
            "rx_last",
            "loop_bb2_enterFrom_bb1",
            "loop_bb2_b",
            "loop_bb2_reenterFrom_bb5",
            "bb5_to_bb2_r25_dst_vld",
            "hls_stSync_0_to_1_atSrc_rd",
            "bb5_to_bb2_r24_dst_vld",
            "bb1_to_bb2_r25_dst_vld"))

        def testedFn0(rx_valid,
             rx_last,
             loop_bb2_enterFrom_bb1,
             loop_bb2_b,
             loop_bb2_reenterFrom_bb5,
             bb5_to_bb2_r25_dst_vld,
             hls_stSync_0_to_1_atSrc_rd,
             bb5_to_bb2_r24_dst_vld,
             bb1_to_bb2_r25_dst_vld):
            return (
                (rx_last | ~(loop_bb2_enterFrom_bb1 & ~loop_bb2_b | loop_bb2_reenterFrom_bb5 & loop_bb2_b) |
                  ~rx_last & (loop_bb2_enterFrom_bb1 & ~loop_bb2_b | loop_bb2_reenterFrom_bb5 & loop_bb2_b) |
                  (rx_last | ~(loop_bb2_enterFrom_bb1 & ~loop_bb2_b | loop_bb2_reenterFrom_bb5 & loop_bb2_b))
                ) &
                (bb5_to_bb2_r25_dst_vld & (loop_bb2_reenterFrom_bb5 & loop_bb2_b & loop_bb2_b) |
                  ~(loop_bb2_reenterFrom_bb5 & loop_bb2_b & loop_bb2_b)) &
                (rx_valid & (loop_bb2_enterFrom_bb1 & ~loop_bb2_b | loop_bb2_reenterFrom_bb5 & loop_bb2_b) |
                     ~(loop_bb2_enterFrom_bb1 & ~loop_bb2_b | loop_bb2_reenterFrom_bb5 & loop_bb2_b)) &
                (bb1_to_bb2_r25_dst_vld & ~loop_bb2_b | loop_bb2_b) &
                (bb5_to_bb2_r24_dst_vld & loop_bb2_b | ~loop_bb2_b) &
                hls_stSync_0_to_1_atSrc_rd
            )

        def testedFn1(rx_valid,
             rx_last,
             loop_bb2_enterFrom_bb1,
             loop_bb2_b,
             loop_bb2_reenterFrom_bb5,
             bb5_to_bb2_r25_dst_vld,
             hls_stSync_0_to_1_atSrc_rd,
             bb5_to_bb2_r24_dst_vld,
             bb1_to_bb2_r25_dst_vld):
            return (
                (rx_last | ~(loop_bb2_enterFrom_bb1 & ~loop_bb2_b | loop_bb2_reenterFrom_bb5 & loop_bb2_b) |
                 ~rx_last & (loop_bb2_enterFrom_bb1 & ~loop_bb2_b | loop_bb2_reenterFrom_bb5 & loop_bb2_b) |
                 (rx_last | ~(loop_bb2_enterFrom_bb1 & ~loop_bb2_b | loop_bb2_reenterFrom_bb5 & loop_bb2_b))
                 ) &
                (bb5_to_bb2_r25_dst_vld | ~(loop_bb2_reenterFrom_bb5 & loop_bb2_b & loop_bb2_b)) &
                (bb1_to_bb2_r25_dst_vld | loop_bb2_b) &
                (bb5_to_bb2_r24_dst_vld | ~loop_bb2_b) &
                hls_stSync_0_to_1_atSrc_rd &
                (loop_bb2_enterFrom_bb1 & ~loop_bb2_b | loop_bb2_reenterFrom_bb5 & loop_bb2_b) &
                (loop_bb2_enterFrom_bb1 & ~loop_bb2_b | loop_bb2_reenterFrom_bb5 & loop_bb2_b)
            )

        def testedFn0ExpectedUnoptimized(rx_valid,
             rx_last,
             loop_bb2_enterFrom_bb1,
             loop_bb2_b,
             loop_bb2_reenterFrom_bb5,
             bb5_to_bb2_r25_dst_vld,
             hls_stSync_0_to_1_atSrc_rd,
             bb5_to_bb2_r24_dst_vld,
             bb1_to_bb2_r25_dst_vld):
            return ~(~hls_stSync_0_to_1_atSrc_rd | ~(~loop_bb2_b | ~loop_bb2_reenterFrom_bb5 | bb5_to_bb2_r25_dst_vld & (loop_bb2_b & (loop_bb2_b & loop_bb2_reenterFrom_bb5))) | (loop_bb2_enterFrom_bb1 & ~loop_bb2_b | loop_bb2_b & loop_bb2_reenterFrom_bb5) & ~(rx_valid & (loop_bb2_enterFrom_bb1 & ~loop_bb2_b | loop_bb2_b & loop_bb2_reenterFrom_bb5)) | ~loop_bb2_b & (loop_bb2_b | ~bb1_to_bb2_r25_dst_vld) | loop_bb2_b & ~(loop_bb2_b & bb5_to_bb2_r24_dst_vld))

        def testedFn1ExpectedUnoptimized(rx_valid,
             rx_last,
             loop_bb2_enterFrom_bb1,
             loop_bb2_b,
             loop_bb2_reenterFrom_bb5,
             bb5_to_bb2_r25_dst_vld,
             hls_stSync_0_to_1_atSrc_rd,
             bb5_to_bb2_r24_dst_vld,
             bb1_to_bb2_r25_dst_vld):
            return (
            ~((~loop_bb2_enterFrom_bb1 | loop_bb2_b) & ~(loop_bb2_b & loop_bb2_reenterFrom_bb5) | ~hls_stSync_0_to_1_atSrc_rd | ~bb5_to_bb2_r25_dst_vld & (loop_bb2_b & (loop_bb2_b & loop_bb2_reenterFrom_bb5)) | ~(loop_bb2_b | bb1_to_bb2_r25_dst_vld) | loop_bb2_b & ~bb5_to_bb2_r24_dst_vld)
            )

        def testedFn0ExpectedOptimized(rx_valid,
             rx_last,
             loop_bb2_enterFrom_bb1,
             loop_bb2_b,
             loop_bb2_reenterFrom_bb5,
             bb5_to_bb2_r25_dst_vld,
             hls_stSync_0_to_1_atSrc_rd,
             bb5_to_bb2_r24_dst_vld,
             bb1_to_bb2_r25_dst_vld):

            if isinstance(loop_bb2_b, int):
                e0 = loop_bb2_reenterFrom_bb5 if loop_bb2_b else loop_bb2_enterFrom_bb1
            else:
                e0 = loop_bb2_b._ternary(loop_bb2_reenterFrom_bb5, loop_bb2_enterFrom_bb1)

            return ~(~rx_valid & e0 | (loop_bb2_b | ~bb1_to_bb2_r25_dst_vld) & ~(loop_bb2_b & bb5_to_bb2_r24_dst_vld) | ~hls_stSync_0_to_1_atSrc_rd | ~bb5_to_bb2_r25_dst_vld & (loop_bb2_b & loop_bb2_reenterFrom_bb5))

        def testedFn0ExpectedOptimizedAlone(rx_valid,
             rx_last,
             loop_bb2_enterFrom_bb1,
             loop_bb2_b,
             loop_bb2_reenterFrom_bb5,
             bb5_to_bb2_r25_dst_vld,
             hls_stSync_0_to_1_atSrc_rd,
             bb5_to_bb2_r24_dst_vld,
             bb1_to_bb2_r25_dst_vld):

            return (~(~(loop_bb2_b & ~loop_bb2_reenterFrom_bb5 | rx_valid | ~(loop_bb2_enterFrom_bb1 | loop_bb2_b)) | ~hls_stSync_0_to_1_atSrc_rd | (loop_bb2_b | ~bb1_to_bb2_r25_dst_vld) & (loop_bb2_reenterFrom_bb5 & ~bb5_to_bb2_r25_dst_vld | ~loop_bb2_b | ~bb5_to_bb2_r24_dst_vld)))

        def testedFn1ExpectedOptimized(rx_valid,
             rx_last,
             loop_bb2_enterFrom_bb1,
             loop_bb2_b,
             loop_bb2_reenterFrom_bb5,
             bb5_to_bb2_r25_dst_vld,
             hls_stSync_0_to_1_atSrc_rd,
             bb5_to_bb2_r24_dst_vld,
             bb1_to_bb2_r25_dst_vld):
            return ~(~(loop_bb2_b & loop_bb2_reenterFrom_bb5) & (~loop_bb2_enterFrom_bb1 | loop_bb2_b) | (loop_bb2_b | ~bb1_to_bb2_r25_dst_vld) & ~(loop_bb2_b & bb5_to_bb2_r24_dst_vld) | ~hls_stSync_0_to_1_atSrc_rd | ~bb5_to_bb2_r25_dst_vld & (loop_bb2_b & loop_bb2_reenterFrom_bb5))

        toAig = RtlNetlistToAbcAig()
        f, net, aig, ioMap = toAig.translate(inputsRtl, (testedFn0(*inputsRtl,)))
        toRtl = AbcAigToRtlNetlist(f, net, aig, ioMap)
        res = tuple(newO for _, newO in toRtl.translate())
        self.assertSequenceEqual(res, [testedFn0ExpectedUnoptimized(*inputsRtl), ])

        for _ in range(2):
            net = abcCmd_resyn2(net)
            net = abcCmd_compress2(net)

        # net.Io_Write("abc-directly.test2.dot", Io_FileType_t.IO_FILE_DOT)
        toRtl = AbcAigToRtlNetlist(f, net, aig, ioMap)
        res = tuple(newO for _, newO in toRtl.translate())
        self.assertSequenceEqual(res, [testedFn0ExpectedOptimizedAlone(*inputsRtl), ])

        f.DeleteAllNetworks()

        toAig = RtlNetlistToAbcAig()
        f, net, aig, ioMap0and1 = toAig.translate(inputsRtl, (testedFn0(*inputsRtl,), testedFn1(*inputsRtl,)))
        toRtl = AbcAigToRtlNetlist(f, net, aig, ioMap0and1)
        res = tuple(newO for _, newO in toRtl.translate())
        # net.setName("test3")
        # net.Io_Write("abc-directly.test3.v", Io_FileType_t.IO_FILE_VERILOG)
        self.assertSequenceEqual(res, (testedFn0ExpectedUnoptimized(*inputsRtl), testedFn1ExpectedUnoptimized(*inputsRtl)))

        for _ in range(2):
            net = abcCmd_resyn2(net)
            net = abcCmd_compress2(net)

        toRtl = AbcAigToRtlNetlist(f, net, aig, ioMap0and1)
        res = tuple(newO for _, newO in toRtl.translate())
        # net.setName("test4")
        # net.Io_Write("abc-directly.test4.v", Io_FileType_t.IO_FILE_VERILOG)

        self.assertEqual(res[0], testedFn0ExpectedOptimized(*inputsRtl))
        self.assertEqual(res[1], testedFn1ExpectedOptimized(*inputsRtl))

        f.DeleteAllNetworks()

        def testNoOpt0and1(n1, n2, n3, n4, n5, n6, n7, n8, n9):
            """
            :note: produced by net.Io_Write("abc-directly.test3.v", Io_FileType_t.IO_FILE_VERILOG)
                used to assert that translation to ABC was correct
            """
            new_n12 = n3 & ~n4
            new_n13 = n4 & n5
            new_n14 = ~new_n12 & ~new_n13
            new_n15 = n4 & new_n13
            new_n16 = n6 & new_n15
            new_n17 = new_n15 & ~new_n16
            new_n18 = n1 & ~new_n14
            new_n19 = ~new_n14 & ~new_n18
            new_n20 = ~new_n17 & ~new_n19
            new_n21 = ~n4 & n9
            new_n22 = ~n4 & ~new_n21
            new_n23 = new_n20 & ~new_n22
            new_n24 = n4 & n8
            new_n25 = n4 & ~new_n24
            new_n26 = new_n23 & ~new_n25
            n10 = n7 & new_n26
            new_n28_1 = ~n6 & new_n15
            new_n29 = ~n4 & ~n9
            new_n30 = ~new_n28_1 & ~new_n29
            new_n31 = n4 & ~n8
            new_n32 = new_n30 & ~new_n31
            new_n33 = n7 & new_n32
            new_n34 = ~new_n14 & new_n33
            n28 = ~new_n14 & new_n34
            return n10, n28

        def testOpt0and1(n1, n2, n3, n4, n5, n6, n7, n8, n9):
            new_n12 = n4 & n5
            new_n13 = n3 & ~n4
            new_n14 = ~new_n12 & ~new_n13
            new_n15 = ~n1 & ~new_n14
            new_n16 = ~n6 & new_n12
            new_n17 = ~n4 & n9
            new_n18 = n4 & n8
            new_n19 = ~new_n17 & ~new_n18
            new_n20 = n7 & ~new_n16
            new_n21 = ~new_n19 & new_n20
            n10 = ~new_n15 & new_n21
            n28 = ~new_n14 & new_n21
            return n10, n28

        def translateInputNamesToNNames(valDict: Dict[str, int]):
            """
            reorder arguments to match parameters of testNoOpt0and1
            """
            res = [None for _ in range(1, 10)]
            for nName, rtlI in ioMap0and1.items():
                nIndex = int(nName[1:])
                assert nIndex > 0
                if nIndex <= 9:
                    assert res[nIndex - 1] is None, res[nIndex - 1]
                    v = valDict[rtlI.name]
                    res[nIndex - 1] = v
            return res

        for inputs in generateAllBitPermutations(9):
            inputs = tuple(inputs)
            (rx_valid,
             rx_last,
             loop_bb2_enterFrom_bb1,
             loop_bb2_b,
             loop_bb2_reenterFrom_bb5,
             bb5_to_bb2_r25_dst_vld,
             hls_stSync_0_to_1_atSrc_rd,
             bb5_to_bb2_r24_dst_vld,
             bb1_to_bb2_r25_dst_vld) = inputs
            eRef0 = testedFn0(*inputs)
            eRef1 = testedFn1(*inputs)

            fn0, fn1 = testNoOpt0and1(*translateInputNamesToNNames(locals()))
            self.assertEqual((fn0, fn1), (eRef0, eRef1), inputs)

            eUnOptimized = testedFn0ExpectedUnoptimized(*inputs)
            self.assertEqual(eRef0, eUnOptimized, (eRef0, eUnOptimized, inputs))

            euNOptimized = testedFn1ExpectedUnoptimized(*inputs)
            self.assertEqual(eRef1, euNOptimized, (eRef0, euNOptimized, inputs))

            eOptimized = testedFn0ExpectedOptimized(*inputs)
            assert eRef0 == eOptimized, (eRef0, eOptimized, inputs)

            eOptimized = testedFn0ExpectedOptimizedAlone(*inputs)
            assert eRef0 == eOptimized, (eRef0, eOptimized, inputs)

            eOptimized = testedFn1ExpectedOptimized(*inputs)
            assert eRef1 == eOptimized, (eRef1, eOptimized, inputs)

            fn0, fn1 = testOpt0and1(*translateInputNamesToNNames(locals()))
            self.assertEqual((fn0, fn1), (eRef0, eRef1), inputs)


if __name__ == "__main__":
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([AbcTC('testFromRtlNetlistAndBack')])
    suite = testLoader.loadTestsFromTestCase(AbcTC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)

