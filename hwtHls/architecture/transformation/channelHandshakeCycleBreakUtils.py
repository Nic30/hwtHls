from itertools import chain
from typing import Optional, Union, List, Tuple

from hwt.hdl.operatorDefs import HOperatorDef
from hwt.hdl.types.defs import BIT
from hwtHls.architecture.analysis.channelGraph import ArchSyncNodeTy
from hwtHls.architecture.transformation.utils.termPropagationContext import ArchSyncNodeTerm, \
    ArchElementTermPropagationCtx
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.nodes.aggregate import HlsNetNodeAggregatePortIn
from hwtHls.netlist.nodes.loopChannelGroup import HlsNetNodeReadAnyChannel, \
    HlsNetNodeWriteAnyChannel
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite


def optionallyAddNameToOperatorNode(out: Optional[HlsNetNodeOut], name: str):
    if out is not None and isinstance(out.obj, HlsNetNodeOperator) and out.obj.name is None:
        out.obj.name = name


ArchSyncExprTemplate = Union[ArchSyncNodeTerm, Tuple[HOperatorDef, Tuple["ArchSyncExprTemplate", ...]]]


def _getIOAck(node:ArchSyncNodeTy,
              builder: HlsNetlistBuilder,
              termPropagationCtx: ArchElementTermPropagationCtx,
              predecessorAck: Optional[HlsNetNodeOut],
              io: Union[HlsNetNodeRead, HlsNetNodeWrite],
              extraExtraCond:Optional[HlsNetNodeOut]=None) -> Optional[HlsNetNodeOut]:
    """
    Resolve if expression which is 0 if this node is causing rest of the circuit to stall
    None means circuit never stalls.
    """
    ack: Optional[HlsNetNodeOut] = None
    if isinstance(io, HlsNetNodeRead):
        if io._isBlocking and io._rtlUseValid:  # isChannelPrivateToHsScc
            ack = io.getValidNB()
            ack = termPropagationCtx.propagate(node, ack, f"r{io._id}_validNB")

    else:
        assert isinstance(io, HlsNetNodeWrite), io
        if io._isBlocking and io._rtlUseReady:
            ack = io.getReadyNB()
            ack = termPropagationCtx.propagate(node, ack, f"w{io._id}_readyNB")

    extraCond = io.getExtraCondDriver()
    if extraCond is not None:
        extraCond = termPropagationCtx.propagate(node, extraCond, f"n{io._id}_extraCond")
        # extraCond = builder.buildAndOptional(predecessorAck, extraCond)
    extraCond = builder.buildAndOptional(extraCond, extraExtraCond)
    
    if ack is not None or extraCond is not None:
        skipWhen = io.getSkipWhenDriver()
        if skipWhen is not None:
            skipWhen = termPropagationCtx.propagate(node, skipWhen, f"n{io._id}_skipWhen")
            # skipWhen = builder.buildAndOptional(predecessorAck, skipWhen)
    else:
        skipWhen = None

    ack = builder.buildOrOptional(builder.buildAndOptional(ack, extraCond), skipWhen)
    optionallyAddNameToOperatorNode(ack, f"ackFromIo_n{io._id}")

    if predecessorAck is not None:
        ack = builder.buildAndOptional(predecessorAck, ack)
    return ack


def resolveAckFromNodeIo(node:ArchSyncNodeTy,
                         builder: HlsNetlistBuilder,
                         termPropagationCtx: ArchElementTermPropagationCtx,
                         inputs: List[HlsNetNodeRead], outputs: List[HlsNetNodeWrite]):
    """
    This function builds an expression:
    .. code-block:: python3
        And(*((allPredecAck(i) & ((i.valid & i.extraCond) | i.skipWhen)) for i in inputs),
            *((allPredecAck(o) & ((o.ready & o.extraCond) | o.skipWhen)) for o in outputs)))

    However all variables in expression are optional and their default replacements are:
    * valid - 1
    * ready - 1
    * extraCond - 1
    * skipWhen - 0

    During the expression construction new nodes are scheduled with 0 duration.
    0 is used to keep everything in same clock cycle.
    :note: allPredecAck is important because it asserts that extraCond, skipWhen are valid
    :return: None if all IO always enabled and never blocks otherwise return an expression under which all IO is enabled and active 
    """
    channels = sorted(chain(inputs, outputs), key=lambda x: x.scheduledZero)
    ack = None
    for io in channels:
        _ack = _getIOAck(node, builder, termPropagationCtx, ack, io)
        ack = builder.buildAndOptional(ack, _ack)

    return ack


def iterParentPortAlieasesInHierarchy(port0: HlsNetNodeAggregatePortIn):
    yield port0
    while isinstance(port0.obj, HlsNetNodeAggregatePortIn):
        p:HlsNetNodeAggregatePortIn = port0.obj
        parentDep: HlsNetNodeOut = p.parentIn.obj.dependsOn[p.parentIn.in_i]
        yield parentDep
        parentDepInside = parentDep.obj._outputsInside[parentDep.out_i].dependsOn[0]
        yield parentDepInside
        port0 = parentDepInside


def hasSameDriver(port0: Optional[HlsNetNodeIn], port1: Optional[HlsNetNodeIn]):
    if port0 is port1:
        return True
    elif port0 is None or port1 is None:
        return False
    else:
        # because port may be driven from some hierarchical port it may have same value and be a different object
        # collect set of aliases of each port and check for intersection
        port0Synonyms = set(iterParentPortAlieasesInHierarchy(port0))
        for p1Alias in iterParentPortAlieasesInHierarchy(port1):
            if p1Alias in port0Synonyms:
                return True
        return False


def hasNotAnySyncOrFlag(n: Union[HlsNetNodeReadAnyChannel, HlsNetNodeWriteAnyChannel]):
    return not n._rtlUseValid and not n._rtlUseReady and n.extraCond is None and n.skipWhen is None


def constructExpressionFromTemplate(builder: HlsNetlistBuilder,
                                    termPropagationCtx: ArchElementTermPropagationCtx,
                                    exprTemplate: ArchSyncExprTemplate) -> HlsNetNodeOut:
    """
    Build expression from template in specified node potentially adding ports to traverse hierarchy if term is
    defined in a different node.
    """
    if isinstance(exprTemplate, ArchSyncNodeTerm):
        return termPropagationCtx.propagate(exprTemplate.node, exprTemplate.out, exprTemplate.name)
        # e = importedPorts.get(exprTemplate, None)
        # if e is not None:
        #     return e
        # # get output port of other node or construct it
        # e = exportedPorts.get(exprTemplate, None)
        # if e is None:
        #     if exprTemplate.node == syncNode:
        #         # imported and exported to same sync node, use original expr directly
        #         e = exprTemplate.out
        #         return e
        #     else:
        #         e = exportPortFromArchElement(exprTemplate.node, exprTemplate.out, exprTemplate.name, exportedPorts)
        #         exportedPorts[exprTemplate] = e
        # # construct input to this node
        # e, _ = importPortToArchElement(e, e.name, syncNode)
        # importedPorts[exprTemplate] = e
    elif isinstance(exprTemplate, HlsNetNodeOut):
        return exprTemplate
    else:
        assert not isinstance(exprTemplate, HlsNetNodeOut), (
            "Node outs should be wrapped in ArchSyncNodeTerm instance", exprTemplate)
        op, args = exprTemplate
        args = tuple(constructExpressionFromTemplate(builder, termPropagationCtx, o) for o in args)
        e = builder.buildOpWithOpt(op, BIT, *args)
    return e
