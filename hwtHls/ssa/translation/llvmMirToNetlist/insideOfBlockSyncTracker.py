from typing import Set, Union, Literal, Optional

from hwt.hdl.operatorDefs import AllOps
from hwt.hdl.types.bits import Bits
from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOutAny, HlsNetNodeOutLazy, \
    HlsNetNodeOut
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.readSync import HlsNetNodeReadSync
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.transformation.simplifyUtils import getConstDriverOf


class InsideOfBlockSyncTracker():
    """
    This object holds an information which node may hold invalid value and
    which needs an and with vld singnal of some input before use.
    
    For nodes before block the validity of data is asserted by
    branch condition, for nodes inside of this block we need to extend
    block en condition with valid & ~skipWhen for each input to expression
    used by this node
    
    #:ivar syncForNode: cache to avoid search of validity flags for previously visited nodes
    :ivar blockBoudary: boundary which should not be crossed during validity search.
        The nodes of this boundary and all nodes behind are already asserted to be valid
        by blockEn condition.
    """

    def __init__(self, blockEn: HlsNetNodeOutAny, builder: HlsNetlistBuilder):
        self.blockEn = blockEn
        self.builder = builder
        self.blockBoudary: Set[HlsNetNodeOutAny] = {blockEn, }
        # self.syncForOut: Dict[HlsNetNodeOutAny, UniqList[HlsNetNodeExplicitSync]] = {}

    def _collectInputValidityFlags(self, out: HlsNetNodeOutAny, parentUser: Optional[HlsNetNode], usedInputs: UniqList[HlsNetNodeExplicitSync]):
        if out in self.blockBoudary:
            return

        elif isinstance(out, HlsNetNodeOutLazy):
            assert out in self.blockBoudary, out
            return
        else:
            assert isinstance(out, HlsNetNodeOut), out

        outObj = out.obj
        assert not isinstance(outObj, HlsNetNodeReadSync), out

        if isinstance(outObj, (HlsNetNodeRead, HlsNetNodeWrite)):
            if isinstance(outObj, HlsNetNodeRead):
                if out is outObj._valid or out is outObj._validNB:
                    return
                elif out is outObj._rawValue:
                    if isinstance(parentUser, HlsNetNodeOperator) and parentUser.operator == AllOps.INDEX:
                        assert parentUser.dependsOn[0] is out
                        i = getConstDriverOf(parentUser._inputs[1])
                        assert i is not None
                        if isinstance(i._dtype, Bits):
                            i = int(i)
                            dataWidth = outObj._outputs[0]._dtype.bit_length()
                            if i >= dataWidth: # _valid or _validNB
                                assert i < dataWidth + 2
                                return 
            usedInputs.append(outObj)

        elif isinstance(outObj, HlsNetNodeExplicitSync):
            assert outObj in self.blockBoudary, (
                "HlsNetNodeExplicitSync should be used only to separate blocks and should not appear inside of block", out)

        else:
            for o in outObj.dependsOn:
                if o in self.blockBoudary:
                    continue
                self._collectInputValidityFlags(o, outObj, usedInputs)

    def resolveControlOutput(self, out: Union[HlsNetNodeOutAny, Literal[0, 1]]):
        """
        Resolve some output which is used in control, which must never get into invalid state.
        To assert this this algorithm collects all validity flags from inputs of expression tree
        for this output and "ands them" with this output "o" 
        
        :attention: non-blocking reads are ignored as the and with valid flag should be done
            by used. By using of non-blocking user declares that the validity is handled by user.
        :note: reads/writes may be converted automatically by predication, but if it is the case
            conditions should be already updated

        :param out: an output port where the mask with vld of source IO should be applied if required.
        """
        if isinstance(out, int):
            assert out in (0, 1), out
            return out
        usedInputs: UniqList[HlsNetNodeExplicitSync] = UniqList()
        self._collectInputValidityFlags(out, None, usedInputs)
        if usedInputs:
            andMembers = tuple((out, *(rw.getValidNB() for rw in usedInputs)))
            newOut = self.builder.buildAndVariadic(andMembers)
            return newOut
        else:
            return out
