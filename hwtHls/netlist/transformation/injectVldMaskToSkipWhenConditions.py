from typing import Set, Dict, Tuple

from hwt.hdl.operatorDefs import AllOps
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.mux import HlsNetNodeMux
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.readSync import HlsNetNodeReadSync
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.loopGate import HlsLoopGateStatus
from hwtHls.netlist.nodes.programStarter import HlsProgramStarter


class HlsNetlistPassInjectVldMaskToSkipWhenConditions(HlsNetlistPass):
    """
    This pass asserts that the skipWhen and extraCond condition is never in invalid state.
    For skipWhen flag it is required because it drives if the channel is used during synchronization.
    For extraCond flag it is required because it could be used when generating sync inside ArchElement.

    To assert this, it is required that each flag value is anded with a validity flag for each source of value.
    First we walk expression from use to definition and collect which which validity flags are already anded to expression.
    Then for first 1b signal generated from each input we add "and" with the valid of IO input.
    (There must be some because the original condition is 1b wide.)
    """

    def apply(self, hls: "HlsScope", netlist: HlsNetlistCtx):
        builder = netlist.builder
        maskAppliedTo: Set[HlsNetNodeOut] = set()
        maskForOut: Dict[HlsNetNodeOut, Tuple[HlsNetNodeOut, HlsNetNodeOut]] = {}

        for n in netlist.iterAllNodes():
            if isinstance(n, HlsNetNodeExplicitSync):
                n: HlsNetNodeExplicitSync
                for inp in (n.skipWhen, n.extraCond):
                    if inp is not None:
                        o = n.dependsOn[inp.in_i]
                        self._collectAndedVlds(o, set(), set(), maskAppliedTo)
                        if o in maskAppliedTo:
                            continue

                        _o, maskToApply = self._injectVldMaskToExpr(builder, o, maskAppliedTo, maskForOut)
                        assert maskToApply is None, "Should be already applied, because this should be 1b signal"
                        if o is not _o:
                            builder.replaceInputDriver(inp, _o)

    def _collectAndedVlds(self, o: HlsNetNodeOut, ioWithAndedVld: Set[HlsNetNodeExplicitSync], ioUsed: Set[HlsNetNodeExplicitSync],
                          maskAppliedTo: Set[HlsNetNodeOut]):
        if o in maskAppliedTo:
            return

        outObj = o.obj
        if isinstance(outObj, (HlsNetNodeConst, HlsLoopGateStatus, HlsProgramStarter)):
            pass
        elif isinstance(outObj, HlsNetNodeOperator):
            op = outObj.operator
            if op == AllOps.AND or len(outObj._inputs) == 1:
                for operand in outObj.dependsOn:
                    self._collectAndedVlds(operand, ioWithAndedVld, ioUsed, maskAppliedTo)
            else:
                _ioWithAndedVld0: Set[HlsNetNodeExplicitSync] = None
                _ioUsed0: Set[HlsNetNodeExplicitSync] = None
                for operand in outObj.dependsOn:
                    _ioWithAndedVld1: Set[HlsNetNodeExplicitSync] = set()
                    _ioUsed1: Set[HlsNetNodeExplicitSync] = set()
                    self._collectAndedVlds(operand, _ioWithAndedVld1, _ioUsed1, maskAppliedTo)
                    if _ioWithAndedVld0 is None:
                        _ioWithAndedVld0 = _ioWithAndedVld1
                        _ioUsed0 = _ioUsed1
                    else:
                        _ioWithAndedVld0.intersection_update(_ioWithAndedVld1)
                        _ioUsed0.intersection_update(_ioUsed1)

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
            self._collectAndedVlds(outObj.dependsOn[0], ioWithAndedVld, ioUsed, maskAppliedTo)
        else:
            raise NotImplementedError(o)

        if len(ioWithAndedVld) == len(ioUsed):
            maskAppliedTo.add(o)

    def _injectVldMaskToExpr(self, builder: HlsNetlistBuilder,
                             out: HlsNetNodeOut,
                             maskAppliedTo: Set[HlsNetNodeOut],
                             maskForOut: Dict[HlsNetNodeOut,
                                              Tuple[HlsNetNodeOut, HlsNetNodeOut]]) -> HlsNetNodeOut:
        """
        For channels which are read optionally we may have to mask incoming data if the data is used directly in this clock cycle
        to decide if some IO channel should be enabled.
        """
        assert isinstance(out, HlsNetNodeOut), (out, "When this function is called every output should be already resolved")
        outObj = out.obj
        m = maskForOut.get(outObj, None)
        if m is not None:
            return m

        maskToApply = None
        if isinstance(outObj, HlsNetNodeReadSync):
            return out, None

        elif isinstance(outObj, (HlsNetNodeRead, HlsNetNodeWrite)):
            maskToApply = builder.buildReadSync(out)
            maskAppliedTo.add(maskToApply)

        elif isinstance(outObj, HlsNetNodeOperator):
            ops = []
            needsRebuild = False
            for o in outObj.dependsOn:
                if o in maskAppliedTo:
                    ops.append(o)
                    continue

                _o, _maskToApply = self._injectVldMaskToExpr(builder, o, maskAppliedTo, maskForOut)
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
                elif isinstance(outObj, HlsNetNodeMux):
                    out = builder.buildMux(out._dtype, tuple(ops))
                else:
                    out = builder.buildOp(outObj.operator, out._dtype, *ops)

        elif isinstance(outObj, HlsNetNodeExplicitSync):
            # inject mask to expression on other side of this node
            oldI = outObj.dependsOn[0]
            if oldI not in maskAppliedTo:
                newI, maskToApply = self._injectVldMaskToExpr(builder, outObj.dependsOn[0], maskAppliedTo, maskForOut)
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
