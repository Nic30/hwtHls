from typing import Dict, Union, List
import unittest

from hwt.hdl.const import HConst
from hwt.hdl.types.defs import BIT
from hwt.synthesizer.rtlLevel.netlist import RtlNetlist
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.architecture.transformation.controlLogicMinimize import HlsAndRtlNetlistPassControlLogicMinimize
from hwtHls.netlist.abc.abcAigToRtlNetlist import AbcAigToRtlNetlist
from hwtHls.netlist.abc.optScripts import abcCmd_resyn2, abcCmd_compress2
from hwtHls.netlist.abc.rtlNetlistToAbcAig import RtlNetlistToAbcAig


# from hwtHls.netlist.abc.abcCpp import Io_FileType_t
# from hwtHls.netlist.abc.abcCpp import Io_FileType_t
def generateAllBitPermutations(n:int):
    for i in range(1 << n):  # for all number in range defined by number of bits
        yield tuple((i >> bitIndex) & 1 for bitIndex in range(n))  # extract individual bits from number


# truth table gen: https://www.emathhelp.net/en/calculators/discrete-mathematics/truth-table-calculator/
class AbcTC(unittest.TestCase):

    def assertExprSequenceSame(self, exprs: List[Union[RtlSignal, HConst]], ref: List[Union[RtlSignal, HConst]]):
        assert len(exprs) == len(ref), (len(exprs), len(ref))
        for i, (e, opt) in enumerate(zip(exprs, ref)):
            self.assertEqual(e, opt, i)

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
        exampleExpr0 = [
           d,  # 0
           e,  # 1
           a,  # 2
           a | b,  # 3
           ~a,  # 4
           a & ~a,  # 5
           ~a & ~b,  # 6
           a | ~a,  # 7
           ~(a | b | c),  # 8
           ~(a | b | c | c1),  # 9
           ~(a & b & c),  # 10
           ~(a & b & c & c1),  # 11
           a._eq(1),  # 12
           a._eq(0),  # 13
           a != 1,  # 14
           a != 0,  # 15
           (~a & (~b & ~c))._eq(0),  # 16
           ~((~a & ~b) & ~c),  # 17
           a | (~b | c),  # 18
           a & ~b,  # 19
           ~a & b,  # 20
           a & (~b | c),  # 21
        ]
        exampleExpr1 = [
            (a & b) | (c & ~b),  # 0
            (a | b) & c & c1 & ~c2,  # 1
            (a & c) | (b & ~c),  # 2
            c._ternary(a, ~b),  # 3
            c._ternary(~a, b),  # 4
            c._ternary(~a, ~b),  # 5
            ~c._ternary(~a, b),  # 6
            ~c._ternary(a, ~b),  # 7
            ~c._ternary(~a, ~b),  # 8
            (~a & b)._ternary(BIT.from_py(0), ~a),  # 9
            (c | a) & ~(c & b),
        ]

        exampleExpr2 = [
            n1 | ~n4 | ~n5,  # 0
            e0,  # 1
            e1,  # 2
        ]

        exampleExprInputs = [a, b, c, c1, c2, c3, c4, n1, n2, n3, n4, n5, n6, n7, n8, n9]
        toAig = RtlNetlistToAbcAig()
        exampleExpr = exampleExpr0 + exampleExpr1 + exampleExpr2
        f, net, aig, ioMap = toAig.translate(exampleExprInputs, exampleExpr)
        # net.Io_Write("abc.0.dot", Io_FileType_t.IO_FILE_DOT)
        for _ in range(3):
            net = abcCmd_resyn2(net)
            net = abcCmd_compress2(net)
        # net.Io_Write("abc.1.dot", Io_FileType_t.IO_FILE_DOT)
        toRtl = AbcAigToRtlNetlist(f, net, aig, ioMap)
        res = tuple(newO for _, newO in toRtl.translate())
        f.DeleteAllNetworks()
        ref0 = [
            ~a | b,  # 0
            ~a | b,  # 1
            a,  # 2
            a | b,  # 3
            ~a,  # 4
            BIT.from_py(0),  # 5
            ~(a | b),  # 6
            BIT.from_py(1),  # 7
            ~(c | a | b),  # 8
            ~(c1 | c | a | b),  # 9
            ~(c & a & b),  # 10
            ~(c1 & c & a & b),  # 11
            a,  # 12
            ~a,  # 13
            a ^ 1,  # 14
            a ^ 0,  # 15
            a | b | c,  # 16
            c | a | b,  # 17
            a | ~b | c,  # 18 :attention: order of terms may reorder
            a & ~b,  # 19
            ~a & b,  # 20
            a & (~b | c),  # 21
        ]
        ref1 = [
            b._ternary(a, c),  # 0
            ~(~(a | b) | c2 | ~c | ~c1),  # 1
            c._ternary(a, b),  # 2
            c._ternary(a, ~b),  # 3
            c._ternary(~a, b),  # 4
            ~c._ternary(a, b),  # 5
            c._ternary(a, ~b),  # 6
            c._ternary(~a, b),  # 7
            c._ternary(a, b),  # 8
            ~(a | b),  # 9
            c._ternary(~b, a)  # 10
        ]
        ref2 = [
            ~n5 | n1 | ~n4,  # 0
            ~(~(~n1 | ~(n3 | n4) | n4 & ~n5) | n5 & ~n6 | ~n4 | ~n7),  # 1
            ~(n4._ternary(n5, n3) | n5 & ~n6 | ~n4 | ~n7),  # 2 :note: abc is not able to achieve if used in other expr  n7 & (n4 & ~n5),
        ]
        off = 0
        w = len(ref0)
        self.assertExprSequenceSame(res[off:off + w], ref0)
        off += w

        w = len(ref1)
        self.assertExprSequenceSame(res[off:off + w], ref1)
        off += w

        w = len(ref1)
        self.assertExprSequenceSame(res[off:off + w], ref2)
        off += w

        ref = ref0 + ref1 + ref2
        for oOptimized, oInput, oExpected in zip(res, exampleExpr, ref):
            # print(">>>>>>>>>")
            # print("inp", oInput)
            # print("opt", oOptimized)
            # print("exp", oExpected)
            HlsAndRtlNetlistPassControlLogicMinimize._verifyAbcExprEquivalence(exampleExprInputs, oOptimized, oInput)
            HlsAndRtlNetlistPassControlLogicMinimize._verifyAbcExprEquivalence(exampleExprInputs, oInput, oExpected)

        # for x in range(4):
        #     _a = 0b01 & x
        #     _b = (0b10 & x) >> 1
        #     print(int(0 if (not _a and _b) else not _a),
        #           int(not (_a or _b)))
        #

    def test_largerExpression(self):
        # originally taken from Axi4SPacketCopyByteByByte 1->2B unroll=None pipe0_st0_ack
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
            
            if isinstance(loop_bb2_b, int):
                e0 = loop_bb2_reenterFrom_bb5 if loop_bb2_b else loop_bb2_enterFrom_bb1
            else:
                e0 = loop_bb2_b._ternary(loop_bb2_reenterFrom_bb5, loop_bb2_enterFrom_bb1)
            
            
            return ~(~hls_stSync_0_to_1_atSrc_rd | ~(~loop_bb2_b | ~loop_bb2_reenterFrom_bb5 | bb5_to_bb2_r25_dst_vld & (loop_bb2_b & (loop_bb2_b & loop_bb2_reenterFrom_bb5))) | e0 & ~(rx_valid & e0) | ~loop_bb2_b & (loop_bb2_b | ~bb1_to_bb2_r25_dst_vld) | loop_bb2_b & ~(loop_bb2_b & bb5_to_bb2_r24_dst_vld))

        def testedFn1ExpectedUnoptimized(rx_valid,
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
            
            return (
            ~(~e0 | ~hls_stSync_0_to_1_atSrc_rd | ~bb5_to_bb2_r25_dst_vld & (loop_bb2_b & (loop_bb2_b & loop_bb2_reenterFrom_bb5)) | ~(loop_bb2_b | bb1_to_bb2_r25_dst_vld) | loop_bb2_b & ~bb5_to_bb2_r24_dst_vld)
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
                e1 = bb5_to_bb2_r24_dst_vld if loop_bb2_b else bb1_to_bb2_r25_dst_vld
            else:
                e0 = loop_bb2_b._ternary(loop_bb2_reenterFrom_bb5, loop_bb2_enterFrom_bb1)
                e1 = loop_bb2_b._ternary(bb5_to_bb2_r24_dst_vld, bb1_to_bb2_r25_dst_vld)

            return ~(~rx_valid & e0 | ~e1 | ~hls_stSync_0_to_1_atSrc_rd | ~bb5_to_bb2_r25_dst_vld & (loop_bb2_b & loop_bb2_reenterFrom_bb5))


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
            
            if isinstance(loop_bb2_b, int):
                e0 = loop_bb2_reenterFrom_bb5 if loop_bb2_b else loop_bb2_enterFrom_bb1
                e1 = bb5_to_bb2_r24_dst_vld if loop_bb2_b else bb1_to_bb2_r25_dst_vld
            else:
                e0 = loop_bb2_b._ternary(loop_bb2_reenterFrom_bb5, loop_bb2_enterFrom_bb1)
                e1 = loop_bb2_b._ternary(bb5_to_bb2_r24_dst_vld, bb1_to_bb2_r25_dst_vld)
            return ~(~e0 | ~e1 | ~hls_stSync_0_to_1_atSrc_rd | ~bb5_to_bb2_r25_dst_vld & (loop_bb2_b & loop_bb2_reenterFrom_bb5))

        toAig = RtlNetlistToAbcAig()
        f, net, aig, ioMap = toAig.translate(inputsRtl, (testedFn0(*inputsRtl)))
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
        f, net, aig, ioMap0and1 = toAig.translate(inputsRtl, (testedFn0(*inputsRtl),
                                                              testedFn1(*inputsRtl)))
        toRtl = AbcAigToRtlNetlist(f, net, aig, ioMap0and1)
        res = tuple(newO for _, newO in toRtl.translate())
        # net.setName("test3")
        # net.Io_Write("abc-directly.test3.v", Io_FileType_t.IO_FILE_VERILOG)
        self.assertSequenceEqual(res, (testedFn0ExpectedUnoptimized(*inputsRtl),
                                       testedFn1ExpectedUnoptimized(*inputsRtl)))

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
                    v = valDict[rtlI._name]
                    res[nIndex - 1] = v
            return res

        for inputs in generateAllBitPermutations(9):
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

    def test_largerExpression1(self):
        # originally taken from Axi4SPacketCopyByteByByte 1->2B unroll=None pipe0_st0_ack
        hwtNet = RtlNetlist(None)
        inputs = tuple(hwtNet.sig(name) for name in (
            "a",
            "b",
            "c",
            "d",
            "e",
        ))
        a, b, c, d, e = inputs

        def f0(a, b, c , d, e):
            expr0 = (c & ~d) | (e & d)
            return (a & (~b & expr0)) | (b | ~expr0)

        def f0b(a, b, c, d, e):
            return ((a & (~(b) & ((c & ~d) | (e & d))._eq(1))) | (b | ((c & ~d) | (e & d))._eq(0)))

        def f0_py(a, b, c , d, e):
            return (a and (not b and ((c and not d) or (e and d)))) or (b or not ((c and not d) or (e and d)))

        def f0Opt(a, b, c , d, e):
            # for ('x', 'x', 0, 'x', 0) this returns x (which is different from original which was returning 1)
            return ~(c | d) | (d & ~e) | a | b

        def f0Opt_py(a, b, c , d, e):
            return not (c or d) or (d and not e) or a or b

        def f1(a, b, c):
            return (a & (~b & c)) | (b | ~c)

        def f1Opt(a, b, c):
            # (1, 'x', 'x') this returns 1 (which is different from original which was returning x)
            return ~c | a | b

        exampleExpr = [
            f0(*inputs),
            f0b(*inputs),
            f1(inputs[0], inputs[1], inputs[2])
        ]
        toAig = RtlNetlistToAbcAig()
        f, net, aig, ioMap = toAig.translate(inputs, exampleExpr)
        net = abcCmd_resyn2(net)
        net = abcCmd_compress2(net)
        toRtl = AbcAigToRtlNetlist(f, net, aig, ioMap)
        res = tuple(newO for _, newO in toRtl.translate())
        f.DeleteAllNetworks()
        for i, (oOptimized, oInput) in enumerate(zip(res, exampleExpr)):
            # print(">>>>>>>>>")
            # print("inp", oInput)
            # print("opt", oOptimized)
            _inputs = inputs
            if i == 2:
                _inputs = [inputs[0], inputs[1], inputs[2]]
            HlsAndRtlNetlistPassControlLogicMinimize._verifyAbcExprEquivalence(inputs, oOptimized, oInput)

        # test with fully defined values
        for inputVals in generateAllBitPermutations(5):
            self.assertEqual(f0_py(*inputVals), f0Opt_py(*inputVals), inputVals)

        # def formatValues(_inputVals: Sequence[BitsVal]):
        #    return tuple(v.val if v.vld_mask else 'x' for v in _inputVals)

        # for inputVals in generateAllBitPermutations(3):
        #    for vldMask in generateAllBitPermutations(3):
        #        _inputVals = tuple(BIT.from_py(v, vld_mask) for v, vld_mask in zip(inputVals, vldMask))
        #        res0 = f1(*_inputVals)
        #        res0Opt = f1Opt(*_inputVals)
        #        self.assertEqual((res0.val, res0.vld_mask), (res0Opt.val, res0Opt.vld_mask), formatValues(_inputVals))

        # for inputVals in generateAllBitPermutations(5):
        #    print(inputVals, int(f0_py(*inputVals)))
        #    for vldMask in generateAllBitPermutations(5):
        #        _inputVals = tuple(BIT.from_py(v, vld_mask) for v, vld_mask in zip(inputVals, vldMask))
        #        if formatValues(_inputVals) == ('x', 'x', 0, 'x', 0):
        #            res0Opt = f0Opt(*_inputVals)
        #            print(res0Opt)
        #        res0 = f0(*_inputVals)
        #        res0Opt = f0Opt(*_inputVals)
        #        print(formatValues(_inputVals), res0, res0Opt)
        #        self.assertEqual((res0.val, res0.vld_mask), (res0Opt.val, res0Opt.vld_mask), formatValues(_inputVals))

    def test_mux0(self):
        # originally taken from Axi4SPacketCopyByteByByte 1->2B unroll=None pipe0_st0_ack
        hwtNet = RtlNetlist(None)
        inputs = tuple(hwtNet.sig(name) for name in (
            "v0",
            "v1",
            "c",
            "d",
        ))
        v0, v1, c, d = inputs
        exampleExpr = [
            ~c._ternary(v0, v1) & (c | d),
            ~c._ternary(BIT.from_py(0), BIT.from_py(1)) & (c | d),
            ~c._ternary(v0, v1),
        ]
        toAig = RtlNetlistToAbcAig()
        f, net, aig, ioMap = toAig.translate(inputs, exampleExpr)
        # net.Io_Write("abc-directly.0.dot", Io_FileType_t.IO_FILE_DOT)
        net = abcCmd_resyn2(net)
        net = abcCmd_compress2(net)
        # net.Io_Write("abc-directly.1.dot", Io_FileType_t.IO_FILE_DOT)
        toRtl = AbcAigToRtlNetlist(f, net, aig, ioMap)
        res = tuple(newO for _, newO in toRtl.translate())
        f.DeleteAllNetworks()

        self.assertSequenceEqual(res, [
            (c | d) & ~c._ternary(v0, v1),
            c,
            ~c._ternary(v0, v1),
        ])

        for (oOptimized, oInput) in zip(res, exampleExpr):
            HlsAndRtlNetlistPassControlLogicMinimize._verifyAbcExprEquivalence(inputs, oOptimized, oInput)

        def f0_py(v0, v1, c, d):
            return (not(v0 if c else v1)) & (c | d)

        def f0Opt_py(v0, v1, c, d):
            return (not v0) & c | d & (not (v1 | c))

        for inputVals in generateAllBitPermutations(4):
            self.assertEqual(f0_py(*inputVals), f0Opt_py(*inputVals), inputVals)

        def f1_py(c, d):
            return (not(0 if c else 1)) & (c | d)

        def f1Opt_py(c, d):
            return c

        for inputVals in generateAllBitPermutations(2):
            self.assertEqual(f1_py(*inputVals), f1Opt_py(*inputVals), inputVals)

        def f2_py(v0, v1, c):
            return not (v0 if c else v1)

        def f2Opt_py(v0, v1, c):
            return (not v0) & c | (not (v1 | c))

        for inputVals in generateAllBitPermutations(3):
            self.assertEqual(f2_py(*inputVals), f2Opt_py(*inputVals), inputVals)

    def test_mux_andOfOrs(self):
        hwtNet = RtlNetlist(None)
        inputs = tuple(hwtNet.sig(name) for name in (
            "c",
            "v0",
            "v1",
        ))
        c, v0, v1 = inputs
        exampleExpr = [
            (~c | v0) & (c | v1),
        ]
        toAig = RtlNetlistToAbcAig()
        f, net, aig, ioMap = toAig.translate(inputs, exampleExpr)
        # net.Io_Write("abc-directly.0.dot", Io_FileType_t.IO_FILE_DOT)
        toRtl = AbcAigToRtlNetlist(f, net, aig, ioMap)
        res = tuple(newO for _, newO in toRtl.translate())
        f.DeleteAllNetworks()

        self.assertSequenceEqual(res, [
            c._ternary(v0, v1)
        ])

    def test_mux_nested(self):
        # originally taken from Axi4SPacketCopyByteByByte 1->2B unroll=None pipe0_st0_ack
        hwtNet = RtlNetlist(None)
        inputs = tuple(hwtNet.sig(name) for name in (
            "v0",
            "c0",
            "v1",
            "c1",
            "v2",
            "c2",
            "v3",
        ))
        v0, c0, v1, c1, v2, c2, v3 = inputs
        e0 = c1._ternary(v1, v2)
        e1 = c0._ternary(v0, e0)
        e2 = c2._ternary(e1, v3)
        exampleExpr = [
            e0,
            e1,
            e2,
        ]
        toAig = RtlNetlistToAbcAig()
        f, net, aig, ioMap = toAig.translate(inputs, exampleExpr)
        # net.Io_Write("abc.0.dot", Io_FileType_t.IO_FILE_DOT)
        net = abcCmd_resyn2(net)
        net = abcCmd_compress2(net)
        # net.Io_Write("abc.1.dot", Io_FileType_t.IO_FILE_DOT)
        net = abcCmd_resyn2(net)
        net = abcCmd_compress2(net)
        # net.Io_Write("abc.2.dot", Io_FileType_t.IO_FILE_DOT)
        toRtl = AbcAigToRtlNetlist(f, net, aig, ioMap)
        res = tuple(newO for _, newO in toRtl.translate())
        f.DeleteAllNetworks()

        self.assertSequenceEqual(res, [
            e0,
            e1,
            e2,
        ])


if __name__ == "__main__":
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([AbcTC('test_largerExpression')])
    suite = testLoader.loadTestsFromTestCase(AbcTC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)

