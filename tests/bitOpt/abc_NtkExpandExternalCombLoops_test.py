from typing import Set, Dict, List
import unittest

from hwt.synthesizer.rtlLevel.netlist import RtlNetlist
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.netlist.abc.abcAigToRtlNetlist import AbcAigToRtlNetlist
from hwtHls.netlist.abc.abcCpp import Abc_NtkExpandExternalCombLoops, \
    MapAbc_Obj_tToSetOfAbc_Obj_t, MapAbc_Obj_tToAbc_Obj_t, Abc_Ntk_t  # , Io_FileType_t
from hwtHls.netlist.abc.rtlNetlistToAbcAig import RtlNetlistToAbcAig
from tests.frontend.pyBytecode.stmWhile import TRUE


class Abc_NtkExpandExternalCombLoops_TC(unittest.TestCase):

    def _generateExpandExternalCombLoopMaps(self,
                                            net: Abc_Ntk_t,
                                            ioMap: Dict[str, RtlSignal],
                                            _inToOutConnections: Dict[RtlSignal, int],
                                            _outputsFromAbcNet: Set[int],
                                            _impliedValues: Dict[int, Set[RtlSignal]],
                                            ):
        inputs = {}
        # outputs = {}
        for pi in net.IterPi():
            name = pi.Name()
            assert name not in inputs, ("port name must be unique", name, inputs[name], pi)
            inputs[ioMap[name]] = pi
        outputSeq = tuple(net.IterPo())
        # for po in outputSeq:
        #    name = po.Name()
        #    assert name not in outputs, ("port name must be unique", name, outputs[name], po)
        #    outputs[ioMap[name]] = po

        impliedValues = MapAbc_Obj_tToSetOfAbc_Obj_t()
        for k, values in _impliedValues.items():
            impliedValues[outputSeq[k]] = {inputs[v] for v in values}

        inToOutConnections = MapAbc_Obj_tToAbc_Obj_t()
        for k, v in _inToOutConnections.items():
            inToOutConnections[inputs[k]] = outputSeq[v]
        outputsFromAbcNet = set(outputSeq[o] for o in _outputsFromAbcNet)

        return impliedValues, inToOutConnections, outputsFromAbcNet

    def _run_Abc_NtkExpandExternalCombLoops(self, inputs: List[RtlSignal], outputs: List[RtlSignal],
                                            _inToOutConnections: Dict[RtlSignal, int],
                                            _outputsFromAbcNet: Set[int],
                                            _impliedValues: Dict[int, Set[RtlSignal]]={},
                                            ):
        toAig = RtlNetlistToAbcAig()
        f, net, aig, ioMap = toAig.translate(inputs, outputs)

        impliedValues, inToOutConnections, outputsFromAbcNet = self._generateExpandExternalCombLoopMaps(
            net, ioMap,
            _inToOutConnections, _outputsFromAbcNet, _impliedValues)

        # print("impliedValues:")
        # for k, v in impliedValues.items():
        #     print(k, k.Name(), ":")
        #     for _v in v:
        #         print("   ", _v, _v.Name())
        # print("inToOutConnections:")
        # for k, v in inToOutConnections.items():
        #     print(k, k.Name(), ":", v, v.Name())
        # 
        # print("outputsFromAbcNet:")
        # for v in outputsFromAbcNet:
        #     print(v, v.Name())

        # net.Io_Write("abc.0.dot", Io_FileType_t.IO_FILE_DOT)
        Abc_NtkExpandExternalCombLoops(net, net.pManFunc, impliedValues, inToOutConnections, outputsFromAbcNet)
        # net.Io_Write("abc.1.dot", Io_FileType_t.IO_FILE_DOT)
        toRtl = AbcAigToRtlNetlist(f, net, aig, ioMap)
        res = tuple(newO for _, newO in toRtl.translate())
        f.DeleteAllNetworks()
        return res

    def test_1cycleNoCond(self):
        hwtNet = RtlNetlist(None)
        inputs = tuple(hwtNet.sig(name) for name in (
            "c0_en_in",
        ))
        (
            c0_en_in,
        ) = inputs
        exampleExpr = [
            # simple cycle resolved to 1
            c0_en_in,  # = c0_en_out
        ]
        inToOutConnections = {c0_en_in: 0}
        outputsFromAbcNet = {0}
        res = self._run_Abc_NtkExpandExternalCombLoops(inputs, exampleExpr, inToOutConnections, outputsFromAbcNet)
        self.assertSequenceEqual(res, [
            TRUE
        ])

    def test_1cycleCond(self):
        hwtNet = RtlNetlist(None)
        inputs = tuple(hwtNet.sig(name) for name in (
            "i0",
            "c0_en_in",
        ))
        (
            i0,
            c0_en_in,
        ) = inputs
        exampleExpr = [
            # cycle & i0 -> i0
            c0_en_in & i0,  # = c0_en_out
            c0_en_in,
        ]
        inToOutConnections = {c0_en_in: 0}
        outputsFromAbcNet = {0, 1}
        res = self._run_Abc_NtkExpandExternalCombLoops(inputs, exampleExpr, inToOutConnections, outputsFromAbcNet)
        self.assertSequenceEqual(res, [
            i0,
            i0,
        ])

    def test_1cycleCond_n(self):
        hwtNet = RtlNetlist(None)
        inputs = tuple(hwtNet.sig(name) for name in (
            "i0",
            "c0_en_in",
        ))
        (
            i0,
            c0_en_in,
        ) = inputs
        exampleExpr = [
            # cycle & i0 -> i0
            c0_en_in & ~i0,  # = c0_en_out
            c0_en_in,
        ]
        inToOutConnections = {c0_en_in: 0}
        outputsFromAbcNet = {0, 1}
        res = self._run_Abc_NtkExpandExternalCombLoops(inputs, exampleExpr, inToOutConnections, outputsFromAbcNet)
        self.assertSequenceEqual(res, [
            ~i0,
            ~i0,
        ])

    def test_2cycle(self):
        hwtNet = RtlNetlist(None)
        inputs = tuple(hwtNet.sig(name) for name in (
            "i0",
            "i1",
            "c0_en_in",
            "c1_en_in"
        ))
        (
            i0,
            i1,
            c0_en_in,
            c1_en_in
        ) = inputs
        exampleExpr = [
            # 2x cycle connected with 2 edges (1 for each dir)
            c0_en_in & i0 & c1_en_in,  # = c0_en_out
            c0_en_in & c0_en_in & i1,  # = c1_en_out
            c0_en_in,
            c1_en_in,
            ~c0_en_in,
            ~c1_en_in,

            # previous case with and i0, i1 in each cycle
        ]
        inToOutConnections = {c0_en_in: 0, c1_en_in: 1}
        outputsFromAbcNet = set(range(len(exampleExpr)))
        res = self._run_Abc_NtkExpandExternalCombLoops(inputs, exampleExpr, inToOutConnections, outputsFromAbcNet)
        
        self.assertSequenceEqual(res, [
            i0 & i1 & (i0 & (i0 & i1)),
            i1 & (i0 & i1),
            i0 & i1,
            i0 & i1,
            ~(i0 & i1),
            ~(i0 & i1),
        ])


if __name__ == "__main__":
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([Abc_NtkExpandExternalCombLoops_TC('test_2cycle')])
    suite = testLoader.loadTestsFromTestCase(Abc_NtkExpandExternalCombLoops_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)

