
from collections import defaultdict
from random import Random
from typing import Sequence, Callable

from hwt.hdl.types.defs import BIT
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.nodes.ports import HlsNetNodeOut

hlsNetlistGenerateRandomDag_OPS_DEFAULT = [
    (1, lambda builder, o0: builder.buildNot(o0, opt=False)),
    (2, lambda builder, o0, o1: builder.buildAnd(o0, o1, opt=False)),
    (2, lambda builder, o0, o1: builder.buildOr(o0, o1, opt=False)),
    (2, lambda builder, o0, o1: builder.buildXor(o0, o1, opt=False)),
    (3, lambda builder, v0, c0, v1: builder.buildMux(BIT, (v0, c0, v1), opt=False)),
]


def hlsNetlistGenerateRandomDag(random: Random,
                                nodeCnt: int,
                                inputs: list[HlsNetNodeOut],
                                builder: HlsNetlistBuilder,
                                depthFactor=2.0,
                                avoidSameInputs=True,
                                nodeConstructors:Sequence[tuple[int, Callable[[HlsNetlistBuilder, HlsNetNodeOut, ...], HlsNetNodeOut]]]=hlsNetlistGenerateRandomDag_OPS_DEFAULT)\
                                ->Sequence[HlsNetNodeOut]:
    """
    Generates a random layered DAG.
    
    :param depthFactor: The multiplier for probability during imput selection, value higher than 1 prioritizes outputs on later layers,
                        making the DAG deeper, while values lower than 1 prioritize the outputs from more early layers, making final graph
                        more wide and dense.
    :note: typical value for depthFactor will be in range 0.3 to 1.7
    """
    allNodeOutputs = inputs[:]
    
    # Track layer assignment for each node
    nodeLayers = {node: 0 for node in inputs}
    layerOfNode = defaultdict(list)
    for inp in inputs:
        layerOfNode[0].append(inp)
    
    # Precompute base weights (will be updated as layers change)
    nodeWeights = [depthFactor ** (nodeLayers[node] + 1) for node in allNodeOutputs]
    
    while nodeCnt:
        requiredInputCnt, gateBuilder = random.choice(nodeConstructors)
        assert requiredInputCnt <= len(allNodeOutputs)
        
        # Select diverse inputs using weighted choice with zeroed weights
        _inputs = []
        weightsBackup = []
        
        while requiredInputCnt:
            # Weighted selection from allNodeOutputs
            _selectedInputs = random.choices(allNodeOutputs, weights=nodeWeights, k=requiredInputCnt)
            if avoidSameInputs:
                for selected_input in _selectedInputs:
                    if selected_input in _inputs:
                        continue
                    _inputs.append(selected_input)
                    if requiredInputCnt == 1:
                        idx = allNodeOutputs.index(selected_input)
                        weightsBackup.append((idx, nodeWeights[idx]))
                        nodeWeights[idx] = 0
                    requiredInputCnt -= 1
            else:
                _inputs = _selectedInputs
                requiredInputCnt = 0
                break

        if avoidSameInputs:
            # Restore original weights
            for i, w in weightsBackup:
                nodeWeights[i] = w
        
        newNodeOut: HlsNetNodeOut = gateBuilder(builder, *_inputs)
        if newNodeOut in layerOfNode:
            continue  # this expression was already constructed, try again to randomly generate non existing expression

        nodeCnt -= 1
        # assign layer
        newLayer = max(nodeLayers[n] for n in _inputs) + 1
        nodeLayers[newNodeOut] = newLayer
        layerOfNode[newLayer].append(newNodeOut)
        
        allNodeOutputs.append(newNodeOut)
        
        # update base weights for new node (layer-based)
        newNodeWeight = depthFactor ** (newLayer + 1)
        nodeWeights.append(newNodeWeight)
    
    outputs = [o for o in allNodeOutputs if not o.obj.usedBy[o.out_i]]
    
    return outputs

