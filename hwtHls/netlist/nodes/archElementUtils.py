from itertools import chain, zip_longest
from typing import Optional, Dict

from hwt.pyUtils.setList import SetList
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.archElementFsm import ArchElementFsm
from hwtHls.netlist.nodes.archElementPipeline import ArchElementPipeline
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, \
    HlsNetNodeOut


def ArchElement_mergePorts(srcElm: ArchElement, dstElm: ArchElement):
    builder: HlsNetlistBuilder = dstElm.getHlsNetlistBuilder()
    # dictionary mapping external output to some existing input on dstElm
    outIndexOffset = len(dstElm._outputs)
    for o in srcElm._outputs:
        o.obj = dstElm
        o.out_i += outIndexOffset

    inIndexOffset = len(dstElm._inputs)
    for i in srcElm._inputs:
        i.obj = dstElm
        i.in_i += inIndexOffset

    assert type(srcElm.scheduledOut) == tuple

    dstElm._inputs.extend(srcElm._inputs)
    dstElm._inputsInside.extend(srcElm._inputsInside)
    for ii in srcElm._inputsInside:
        ii.parent = dstElm
    dstElm.dependsOn.extend(srcElm.dependsOn)
    dstElm.scheduledIn = tuple(chain(dstElm.scheduledIn, srcElm.scheduledIn))
    dstElm._outputs.extend(srcElm._outputs)
    dstElm.usedBy.extend(srcElm.usedBy)
    dstElm._outputsInside.extend(srcElm._outputsInside)
    for oi in srcElm._outputsInside:
        oi.parent = dstElm

    dstElm.scheduledOut = tuple(chain(dstElm.scheduledOut, srcElm.scheduledOut))

    # prune self loops, de-duplicate ports
    dstElm.scheduledIn = list(dstElm.scheduledIn)
    inputDrivers: Dict[HlsNetNodeOut, HlsNetNodeIn] = {}
    inputsToRemove = []
    for outerDep, outerIn, internIn, tNew in zip(dstElm.dependsOn, dstElm._inputs,
                                                 dstElm._inputsInside, dstElm.scheduledIn):
        outerIn: HlsNetNodeIn
        if outerDep.obj is dstElm:
            # the driver is declared directly in dstNode, use it directly instead using aggregate port
            dstInternOut = dstElm._outputsInside[outerDep.out_i]
            builder.replaceOutput(internIn._outputs[0], dstInternOut.dependsOn[0], True)
            outerIn.disconnectFromHlsOut(outerDep)
            inputsToRemove.append(outerIn)
            continue

        existingIn = inputDrivers.get(outerDep, None)
        if existingIn is None:
            # this was moved this input from srcElm to dstElm
            inputDrivers[outerDep] = outerIn
        else:
            # there is already existing port for this external output
            # use it and lower the scheduling time of port if required
            tCur = dstElm.scheduledIn[existingIn.in_i]
            t = min(tNew, tCur)
            dstElm.scheduledIn[existingIn.in_i] = t
            dstInternIn = dstElm._inputsInside[existingIn.in_i]
            dstInternIn._setScheduleZero(t)
            builder.replaceOutput(internIn._outputs[0], dstInternIn._outputs[0], True)
            outerIn.disconnectFromHlsOut(outerDep)
            inputsToRemove.append(outerIn)

    dstElm.scheduledIn = tuple(dstElm.scheduledIn)
    for i in inputsToRemove:
        dstElm._removeInput(i.in_i)

    # filter dstElm output users
    for o, aggregateOutPort, uses in tuple(zip(dstElm._outputs, dstElm._outputsInside, dstElm.usedBy)):
        if uses:
            continue
        aggregateOutPort._inputs[0].disconnectFromHlsOut(aggregateOutPort.dependsOn[0])
        assert dstElm._outputs[o.out_i] is o
        dstElm._removeOutput(o.out_i)


def ArchElement_mergeFsms(src: ArchElementFsm, dst: ArchElementFsm):
    assert not dst._isMarkedRemoved, dst
    assert not src._isMarkedRemoved, src

    dst.fsm.mergeFsm(src.fsm)
    for clkI, _ in src.iterStages():
        srcConnections = src.connections[clkI]
        if srcConnections is not None:
            dst.connections[clkI].merge(srcConnections)
    dst.subNodes.extend(src.subNodes)
    for n in src.subNodes:
        n.parent = dst
    ArchElement_mergePorts(src, dst)
    src.markAsRemoved()
    src.destroy()


def ArchElement_mergePipeToFsm(src: ArchElementPipeline,
                            dst: ArchElementFsm):
    for c in src.connections:
        assert c is None or not c.signals, ("RTL for this element should not yet be instantiated", src)

    raise NotImplementedError()
    dstFsm = dst.fsm
    for clkI, nodes in enumerate(src.stages):
        dstSt = dstFsm.addState(clkI)
        dstSt.extend(nodes)
        dst.connections[clkI].merge(src.connections[clkI])

    dst.subNodes.extend(src.subNodes)
    for n in src.subNodes:
        n.parent = dst
    ArchElement_mergePorts(src, dst)
    src.markAsRemoved()
    src.destroy()


def ArchElement_mergePipeline(src: ArchElementPipeline,
                              dst: ArchElementPipeline):
    for c in src.connections:
        assert c is None or not c.signals, ("RTL for this element should not yet be instantiated", src)

    raise NotImplementedError()
    for srcNodes, dstNodes in zip_longest(src.stages, dst.stages):
        if srcNodes:
            dstNodes.extend(srcNodes)

    dst.subNodes.extend(src.subNodes)
    ArchElement_mergePorts(src, dst)
    src.markAsRemoved()
    src.destroy()


def ArchElement_merge(src: ArchElement, dst: ArchElement,
                      predecessors: Optional[Dict[ArchElement, SetList[ArchElement]]],
                      successors: Optional[Dict[ArchElement, SetList[ArchElement]]]):

    if isinstance(src, ArchElementPipeline) and isinstance(dst, ArchElementFsm):
        ArchElement_mergePipeToFsm(src, dst)
    elif isinstance(src, ArchElementFsm) and isinstance(dst, ArchElementFsm):
        ArchElement_mergeFsms(src, dst)
    elif isinstance(src, ArchElementPipeline) and isinstance(dst, ArchElementPipeline):
        ArchElement_mergePipeline(src, dst)
    else:
        raise NotImplementedError()

    if predecessors or successors:
        dstSuccessors = successors[dst]
        srcSuccessors = successors.pop(src)
        dstSuccessors.extend(n for n in srcSuccessors if n is not dst)

        dstPredecessors = predecessors[dst]
        srcPredecessors = predecessors.pop(src)
        dstPredecessors.extend(n for n in srcPredecessors if n is not dst)
