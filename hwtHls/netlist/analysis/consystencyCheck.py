from itertools import chain

from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, HlsNetNodeOut
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass


class HlsNetlistPassConsystencyCheck(HlsNetlistPass):
    """
    Check if connection of nodes is error free.
    """

    def apply(self, hls:"HlsStreamProc", to_hw:"SsaSegmentToHwPipeline"):
        allNodes = set(to_hw.hls.nodes)
        allNodes.update(to_hw.hls.inputs)
        allNodes.update(to_hw.hls.outputs)
        
        for n in chain(to_hw.hls.inputs, to_hw.hls.nodes, to_hw.hls.outputs):
            n: HlsNetNode
            inCnt = len(n._inputs)
            assert inCnt == len(n.dependsOn), n
            for in_i, (i, d) in enumerate(zip(n._inputs, n.dependsOn)):
                assert isinstance(i, HlsNetNodeIn), i
                i: HlsNetNodeIn
                assert i.obj is n, (n, i)
                assert i.in_i == in_i, (n, i)
                assert isinstance(d, HlsNetNodeOut), d
                assert d.obj in allNodes, ("Driven by something which is not in netlist", n, d.obj)
                assert d.obj._outputs[d.out_i] is d, ("Broken HlsNetNodeOut object", n, in_i, d)
                
                assert i in d.obj.usedBy[d.out_i], ("Output knows about connected input", n, d, i)
    
            outCnt = len(n._outputs)
            assert outCnt == len(n.usedBy), n
            for out_i, (o, usedBy) in enumerate(zip(n._outputs, n.usedBy)):
                assert isinstance(o, HlsNetNodeOut), (n, o)
                o: HlsNetNode
                assert o.obj is n, (n, o)
                assert o.out_i is out_i, (n, o)
                for u in usedBy:
                    assert isinstance(u, HlsNetNodeIn), (n, o, u)
                    assert u.obj in allNodes, ("Drives something which is not in netlist", n, o, u)
                    assert u.obj._inputs[u.in_i] is u, ("Broken HlsNetNodeIn object", n, o, u)

                    assert u.obj.dependsOn[u.in_i] is o, ("Input knows about connected output", n, u, o)
