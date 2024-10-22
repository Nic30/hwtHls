from hwt.hdl.types.typeCast import toHVal
from hwt.pyUtils.setList import SetList
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.nodes.backedge import HlsNetNodeWriteBackedge
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.transformation.simplifyUtils import getConstDriverOf


def simplifyChannelValPropagationForNeverWritten(dbgTracer: DebugTracer,
                       w: HlsNetNodeWriteBackedge,
                       worklist: SetList[HlsNetNode]):
    """
    If non void channel is never written and has 1 or 0 init values this value may be propagated
    instead of read value because it is only value which can appear on output.
    """
    with dbgTracer.scoped(simplifyChannelValPropagationForNeverWritten, w):
        r = w.associatedRead
        assert r is not None, w
        if len(r.channelInitValues) > 1:
            return False  # multiple values which will be read in sequence, the value will change

        ec = getConstDriverOf(r.extraCond)
        if ec is None or int(ec):
            return False

        builder: HlsNetlistBuilder = r.getHlsNetlistBuilder()

        t = r._portDataOut._dtype
        if r.channelInitValues:
            dbgTracer.log("channel never written, resolving value to first from channelInitValues")
            v = r.channelInitValues[0]
            assert len(v) == 1, (r, v)
            v = toHVal(v[0], t)
        else:
            dbgTracer.log("channel never written, resolving value to undef")
            v = None

        dataReplacement = builder.buildConst(v)
        for u in r.usedBy[r._portDataOut.out_i]:
            worklist.append(u.obj)
        builder.replaceOutput(r._portDataOut, dataReplacement, True)

        return True

