from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync


def trasferHlsNetNodeExplicitSyncFlagsSeriallyConnected(
        src: HlsNetNodeExplicitSync, dst: HlsNetNodeExplicitSync,
        removeFromSrc=True):
    assert src is not dst, src
    # reconnect the flag, possibly merge using appropriate logical function and update reachDb
    if src.extraCond is not None:
        ec = src.dependsOn[src.extraCond.in_i]
        assert ec is not None, (src.extraCond, "If has no driver the input shoud be removed")

        if removeFromSrc:
            src.extraCond.disconnectFromHlsOut(ec)
        if dst.extraCond:
            assert dst.dependsOn[dst.extraCond.in_i] is not None, ("If has no driver the input shoud be removed")
        dst.addControlSerialExtraCond(ec)
        if removeFromSrc:
            src._removeInput(src.extraCond.in_i)
            src.extraCond = None

    if src.skipWhen is not None:
        sw = src.dependsOn[src.skipWhen.in_i]
        assert sw is not None, (src.skipWhen, "If has no driver the input shoud be removed")
        if removeFromSrc:
            src.skipWhen.disconnectFromHlsOut(sw)
        if dst.skipWhen:
            assert dst.dependsOn[dst.skipWhen.in_i] is not None, ("If has no driver the input shoud be removed")
        dst.addControlSerialSkipWhen(sw)
        if removeFromSrc:
            src._removeInput(src.skipWhen.in_i)
            src.skipWhen = None
