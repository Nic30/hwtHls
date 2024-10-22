from typing import Optional, Sequence

from hwtHls.netlist.nodes.aggregate import HlsNetNodeAggregate
from hwtHls.netlist.nodes.aggregatePorts import HlsNetNodeAggregatePortOut
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn, \
    HlsNetNodeOutLazy, HlsNetNodeOutAny
from hwtHls.netlist.nodes.schedulableNode import SchedTime


def _getHlsNetNodeNodePathRec(parent: Optional[HlsNetNodeAggregate]):
    if parent is not None:
        yield from _getHlsNetNodeNodePathRec(parent.parent)
        yield parent


def _getHlsNetNodeNodePath(n: HlsNetNode):
    return tuple(_getHlsNetNodeNodePathRec(n.parent))


def _getCommonPrefixLen(seq0: Sequence, seq1: Sequence):
    i = 0
    for i, (item0, item1) in enumerate(zip(seq0, seq1)):
        if item0 != item1:
            break
    return i


def HlsNetNodeOut_propagateToSameHierarchyLevelAsIn(out: HlsNetNodeOut, in_: HlsNetNodeIn, name: str, time:Optional[SchedTime]=None):
    if isinstance(out, HlsNetNodeOutLazy):
        return out
    outParent = out.obj.parent
    inParent = in_.obj.parent
    if outParent is inParent:
        return out
    else:
        outPath = _getHlsNetNodeNodePath(out.obj)
        inPath = _getHlsNetNodeNodePath(in_.obj)
        commonPrefixLen = _getCommonPrefixLen(outPath, inPath)
        newOut = out
        for outParent in reversed(outPath[commonPrefixLen:]):
            outParent: HlsNetNodeAggregate
            # try to search for existing output which is exporting this port
            existingOutFound = False
            for u in newOut.obj.usedBy[newOut.out_i]:
                if isinstance(u.obj, HlsNetNodeAggregatePortOut):
                    if time is not None and u.obj.scheduledIn[0] != time:
                        # can not use this HlsNetNodeAggregatePortOut because time is different
                        continue
                    newOut = u.obj.parentOut
                    existingOutFound = True

            if not existingOutFound:
                _out, inter = outParent._addOutput(out._dtype, name, time=time)
                newOut.connectHlsIn(inter, checkCycleFree=False)
                newOut = _out

        for inParent in inPath[commonPrefixLen:]:
            inParent: HlsNetNodeAggregate

            existingOutFound = False
            # try to search for existing output which is exporting this port
            for u in newOut.obj.usedBy[newOut.out_i]:
                if u.obj == inParent:
                    if time is not None and u.obj.scheduledIn[u.in_i] != time:
                        # can not use this port because it is in a different  time han requested
                        continue
                    newOut = inParent._inputsInside[u.in_i]._outputs[0]
                    existingOutFound = True

            if not existingOutFound:
                outer, intern = inParent._addInput(out._dtype, name, time=time)
                newOut.connectHlsIn(outer, checkCycleFree=False)
                newOut = intern

        return newOut


def HlsNetNodeOut_connectHlsIn_crossingHierarchy(out: HlsNetNodeOut, in_: HlsNetNodeIn, name: str, time:Optional[SchedTime]=None):
    """
    Connect 2 ports potentially creating HlsNetNodeAggregate ports on the way if ports are not in the same parent
    """
    newOut = HlsNetNodeOut_propagateToSameHierarchyLevelAsIn(out, in_, name, time)
    newOut.connectHlsIn(in_, checkCycleFree=False)


def HlsNetNodeOutLazy_replaceThisInUsers(self: HlsNetNodeOutLazy, replacement:HlsNetNodeOut):
    depInputs = self.dependent_inputs
    if depInputs:
        l0 = len(depInputs)
        for in_ in depInputs:
            in_: HlsNetNodeIn
            newOut = HlsNetNodeOut_propagateToSameHierarchyLevelAsIn(replacement, in_, self.name)
            in_.replaceDriverInInputOnly(newOut)
            builder = in_.obj.getHlsNetlistBuilder()
            builder.unregisterNode(in_.obj)
            builder.registerNode(in_.obj)

        assert len(self.dependent_inputs) == l0, "Must not modify dependent_inputs during replace"
        self.dependent_inputs.clear()


def HlsNetNodeOutLazy_replace(self: HlsNetNodeOutLazy, replacement: HlsNetNodeOutAny):
    """
    Replace this output in all connected inputs.
    """
    assert self is not replacement, self
    assert self.replaced_by is None, (self, self.replaced_by)
    assert self._dtype == replacement._dtype or self._dtype.bit_length() == replacement._dtype.bit_length(), (self, replacement, self._dtype, replacement._dtype)
    for k in self.keys_of_self_in_cache:
        self.op_cache._toHlsCache[k] = replacement

    HlsNetNodeOutLazy_replaceThisInUsers(self, replacement)
    self.replaced_by = replacement

