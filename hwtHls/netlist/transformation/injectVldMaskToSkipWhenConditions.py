from typing import Set, List, Union

from hwt.hdl.operatorDefs import AllOps
from hwt.hdl.types.defs import BIT
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.loopControl import HlsNetNodeLoopStatus
from hwtHls.netlist.nodes.mux import HlsNetNodeMux
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.nodes.programStarter import HlsProgramStarter
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.readSync import HlsNetNodeReadSync
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass


class HlsNetlistPassInjectVldMaskToSkipWhenConditions(HlsNetlistPass):
    """
    This pass asserts that the skipWhen and extraCond condition is never in invalid state.
    For skipWhen flag it is required because it drives if the channel is used during synchronization.
    For extraCond flag it is required because it could be used when generating sync inside ArchElement.

    To assert this, it is required that each flag value is anded with a validity flag for each source of value.
    First we walk expression from use to definition and collect which which validity flags are already anded to expression.
    Then for first 1b signal generated from each input we add "and" with the valid of IO input.
    (There must be some because the original condition is 1b wide.)

    :note: It is not possible to have ands with validity flags from previous steps of compilation.
        This is because the inputs may be added during the compilation once the variable
        life is passed trough some buffer. This happens among other cases also in headers of loops for induction variable.
        For each variable a MUX is constructed which is selecting the value from various predecessors
        and the output value from this mux is driving the write to backedge buffer for that variable.
        This means that the compare must be ANDed with a currently selected source read for this induction
        variable.

    .. code-block:: Python3
    
        i = def
        while i != 0:
            i += 1
        
    
    .. code-block:: Python3
    
        i_pred = [def, ]
        i_buff = []
        
        while True:
            i = i_buff.readNB()
            if not i.valid:
                i = i_pred.read()
            if i != 0: # there valid i is required
                i_buff.append(i + 1)
            else:
                break
    """

    def apply(self, hls: "HlsScope", netlist: HlsNetlistCtx):
        builder = netlist.builder
        maskAppliedTo: Set[HlsNetNodeOut] = set()

        for n in netlist.iterAllNodes():
            if isinstance(n, HlsNetNodeExplicitSync):
                n: HlsNetNodeExplicitSync
                for inp in (n.skipWhen, n.extraCond):
                    if inp is not None:
                        o = n.dependsOn[inp.in_i]
                        assert o is not None, inp
                        if o in maskAppliedTo:
                            continue
                        self._detectAndedVlds(o, set(), set(), maskAppliedTo)
                        if o in maskAppliedTo:
                            continue

                        _o, maskToApply = self._injectAndVldIntoExpr(builder, o, maskAppliedTo)
                        assert maskToApply is None, "Should be already applied, because this should be 1b signal"
                        if o is not _o:
                            builder.replaceInputDriver(inp, _o)

    def _detectAndedVlds(self, o: HlsNetNodeOut,
                          ioWithAndedVld: Set[Union[HlsNetNodeExplicitSync, HlsNetNodeMux]],
                          ioUsed: Set[Union[HlsNetNodeExplicitSync, HlsNetNodeMux]],
                          maskAppliedTo: Set[HlsNetNodeOut]):
        """
        :param ioWithAndedVld: Set of IO and mux nodes which have all required masks already applied to this expression.
        :param maskAppliedTo: Set of outputs which have all required masks already applied and thus
            it is not required to modyfy its use nor it is required to search it over and over.
        """
        if o in maskAppliedTo:
            return

        outObj = o.obj
        if isinstance(outObj, (HlsNetNodeConst, HlsNetNodeLoopStatus, HlsProgramStarter)):
            pass

        elif isinstance(outObj, HlsNetNodeOperator):
            op = outObj.operator
            if op == AllOps.AND or len(outObj._inputs) == 1:
                for operand in outObj.dependsOn:
                    self._detectAndedVlds(operand, ioWithAndedVld, ioUsed, maskAppliedTo)
            else:
                _ioWithAndedVld0: Set[HlsNetNodeExplicitSync] = None
                _ioUsed0: Set[HlsNetNodeExplicitSync] = None
                for operand in outObj.dependsOn:
                    _ioWithAndedVld1: Set[HlsNetNodeExplicitSync] = set()
                    _ioUsed1: Set[HlsNetNodeExplicitSync] = set()
                    self._detectAndedVlds(operand, _ioWithAndedVld1, _ioUsed1, maskAppliedTo)
                    if _ioWithAndedVld0 is None:
                        _ioWithAndedVld0 = _ioWithAndedVld1
                        _ioUsed0 = _ioUsed1
                    else:
                        _ioWithAndedVld0.intersection_update(_ioWithAndedVld1)
                        _ioUsed0.update(_ioUsed1)

                if len(_ioWithAndedVld0) == len(_ioUsed0):
                    maskAppliedTo.add(o)

                ioWithAndedVld.update(_ioWithAndedVld0)
                ioUsed.update(_ioUsed0)
                return

        elif isinstance(outObj, HlsNetNodeReadSync):
            return

        elif isinstance(outObj, (HlsNetNodeRead, HlsNetNodeWrite)):
            if o is outObj._validNB or o is outObj._valid:
                ioWithAndedVld.add(outObj)
            ioUsed.add(outObj)

        elif outObj.__class__ is HlsNetNodeExplicitSync:
            self._detectAndedVlds(outObj.dependsOn[0], ioWithAndedVld, ioUsed, maskAppliedTo)

        else:
            raise NotImplementedError(o)

        if len(ioWithAndedVld) == len(ioUsed):
            maskAppliedTo.add(o)

    def _injectAndVldIntoExpr(self, builder: HlsNetlistBuilder,
                             out: HlsNetNodeOut,
                             maskAppliedTo: Set[HlsNetNodeOut]) -> HlsNetNodeOut:
        """
        For channels which are read optionally we may have to mask incoming data if the data is used directly in this clock cycle
        to decide if some IO channel should be enabled.
        
        :param out: an output port where the mask with vld of source IO should be applied if required.
        :param maskAppliedTo: :see: HlsNetlistPassInjectVldMaskToSkipWhenConditions._detectAndedVlds
        """
        assert isinstance(out, HlsNetNodeOut), (out, "When this function is called every output should be already resolved")
        outObj = out.obj
        maskToApply = None
        if isinstance(outObj, HlsNetNodeReadSync):
            return out, None

        elif isinstance(outObj, (HlsNetNodeRead, HlsNetNodeWrite)):
            maskToApply = builder.buildReadSync(out)
            maskAppliedTo.add(maskToApply)  # add to prevent apply of the mask on the vld itself

        elif isinstance(outObj, HlsNetNodeMux):
            # for mux conditions are driving which input is required
            outObj: HlsNetNodeMux
            # if there is a MUX it is required to resolve masks for every value and condition
            # New mux is then constructed for masks which select mask of original mux value.
            # This new mux output is then used as a new mask.
            needsRebuild = False
            maskMuxOps: List[HlsNetNodeOut] = []
            ops: List[HlsNetNodeOut] = []
            anyMaskRequred = False
            for v, c in outObj._iterValueConditionDriverPairs():
                if v in maskAppliedTo:
                    _v, _maskToApply = self._injectAndVldIntoExpr(builder, v, maskAppliedTo)
                    if _v is not v:
                        needsRebuild = True
                else:
                    _v = v
                    _maskToApply = None
                ops.append(_v)
                if _maskToApply is None:
                    _maskToApply = builder.buildConstBit(1)  # 1 because the value is already anded with mask
                else:
                    anyMaskRequred = True
                maskMuxOps.append(_maskToApply)
                    
                if c is not None:
                    if c in maskAppliedTo:
                        ops.append(c)
                        maskMuxOps.append(c)
                    else:
                        _c, _maskToApply = self._injectAndVldIntoExpr(builder, c, maskAppliedTo)
                        if _maskToApply is not None:
                            _c = builder.buildAnd(c, _maskToApply)
                            anyMaskRequred = True
                        ops.append(_c)
                        maskMuxOps.append(_c)

            if anyMaskRequred:
                maskToApply = builder.buildMux(BIT, tuple(maskMuxOps), name=f"n{outObj._id}_vld")
                maskAppliedTo.add(maskToApply)
                
            if needsRebuild:
                out = builder.buildMux(out._dtype, tuple(ops))
        
        elif isinstance(outObj, HlsNetNodeOperator):
            ops: List[HlsNetNodeOut] = []
            needsRebuild = False
            for o in outObj.dependsOn:
                if o in maskAppliedTo:
                    ops.append(o)
                    continue

                _o, _maskToApply = self._injectAndVldIntoExpr(builder, o, maskAppliedTo)
                ops.append(_o)
                if _o is not o:
                    needsRebuild = True

                if _maskToApply is not None:
                    if maskToApply is None:
                        maskToApply = _maskToApply
                    elif maskToApply is not _maskToApply:
                        maskToApply = builder.buildAnd(maskToApply, _maskToApply)
                        maskAppliedTo.add(maskToApply)
                    else:
                        pass

            if needsRebuild:
                if outObj.operator == AllOps.AND:
                    out = builder.buildAnd(*ops)
                elif outObj.operator == AllOps.OR:
                    out = builder.buildOr(*ops)
                else:
                    out = builder.buildOp(outObj.operator, out._dtype, *ops)

        elif isinstance(outObj, HlsNetNodeExplicitSync):
            # inject mask to expression on other side of this node
            oldI = outObj.dependsOn[0]
            if oldI not in maskAppliedTo:
                newI, maskToApply = self._injectAndVldIntoExpr(builder, outObj.dependsOn[0], maskAppliedTo)
                if newI is not oldI:
                    builder.replaceInputDriver(outObj._inputs[0], newI)
                # return original out because we did not modify the node itself

        if maskToApply is not None and out._dtype.bit_length() == 1:
            # walking def->use we got first 1b expression, we apply the mask
            res = builder.buildAnd(out, maskToApply)
            maskAppliedTo.add(res)
            return res, None
        else:
            return out, maskToApply
