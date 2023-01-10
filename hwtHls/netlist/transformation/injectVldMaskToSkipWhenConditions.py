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


class HlsNetlistPassInjectVldMaskToSkipWhenConditions(HlsNetlistPass):
    """
    This pass asserts that the skipWhen and extraCond condition is never in invalid state.
    For skipWhen is required because it drives if the channel is used during synchronization.
    For extraCond it is required because it could be used when generating sync inside ArchElement.
    To assert this it is required that each flag value is anded with a validity flag for each source of value.
    To have expression as simple as possible we add this "and" to top most 1b signal generated from the input.
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
                        if o in maskAppliedTo:
                            continue
    
                        _o, maskToApply = self._injectVldMaskToExpr(builder, o, maskAppliedTo, maskForOut)
                        assert maskToApply is None, "Should be already applied, because this should be 1b signal"
                        if o is not _o:
                            builder.replaceInputDriver(inp, _o)

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
            res = builder.buildAnd(out, maskToApply)
            maskAppliedTo.add(res)
            return res, None
        else:
            return out, maskToApply
