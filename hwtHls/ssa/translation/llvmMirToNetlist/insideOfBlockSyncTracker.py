#from typing import Set, Union, Literal, Optional
#
#from hwt.hdl.operatorDefs import HwtOps
#from hwt.hdl.types.bits import HBits
#from hwt.pyUtils.setList import SetList
#from hwtHls.netlist.builder import HlsNetlistBuilder
#from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
#from hwtHls.netlist.nodes.node import HlsNetNode
#from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
#from hwtHls.netlist.nodes.ports import HlsNetNodeOutAny, HlsNetNodeOutLazy, \
#    HlsNetNodeOut
#from hwtHls.netlist.nodes.read import HlsNetNodeRead
#from hwtHls.netlist.nodes.readSync import HlsNetNodeReadSync
#from hwtHls.netlist.nodes.write import HlsNetNodeWrite
#from hwtHls.netlist.transformation.simplifyUtils import getConstDriverOf
#
#
#class InsideOfBlockSyncTracker():
#    """
#    This object holds an information which node may hold invalid value and
#    which needs an and with vld signal of some input before use.
#    
#    For nodes before block the validity of data is asserted by
#    branch condition, for nodes inside of this block we need to extend
#    block en condition with valid & ~skipWhen for each input to expression
#    used by this node
#    
#    #:ivar syncForNode: cache to avoid search of validity flags for previously visited nodes
#    :ivar blockBoudary: boundary which should not be crossed during validity search.
#        The nodes of this boundary and all nodes behind are already asserted to be valid
#        by blockEn condition.
#    """
#
#    def __init__(self, blockEn: HlsNetNodeOutAny, builder: Optional[HlsNetlistBuilder]):
#        self.blockEn = blockEn
#        self.builder = builder
#        self.blockBoudary: Set[HlsNetNodeOutAny] = {blockEn, }
#        # self.syncForOut: Dict[HlsNetNodeOutAny, SetList[HlsNetNodeExplicitSync]] = {}
#
#    def _collectInputValidityFlags(self, out: HlsNetNodeOutAny, parentUser: Optional[HlsNetNode], usedInputs: SetList[HlsNetNodeExplicitSync]):
#        if out in self.blockBoudary:
#            return
#
#        elif isinstance(out, HlsNetNodeOutLazy):
#            assert out in self.blockBoudary, out
#            return
#        else:
#            assert isinstance(out, HlsNetNodeOut), out
#
#        outObj = out.obj
#        assert not isinstance(outObj, HlsNetNodeReadSync), out
#
#        if isinstance(outObj, (HlsNetNodeRead, HlsNetNodeWrite)):
#            if isinstance(outObj, HlsNetNodeRead):
#                if not outObj._isBlocking:
#                    return  # non blocking validity is handled by the user
#                elif out is outObj._valid or out is outObj._validNB:
#                    return  # this is use of valid flag, it does not need and with valid
#                elif out is outObj._rawValue:
#                    # check if it is use of valid contained in _rawValue
#                    if isinstance(parentUser, HlsNetNodeOperator) and parentUser.operator == HwtOps.INDEX:
#                        assert parentUser.dependsOn[0] is out
#                        i = getConstDriverOf(parentUser._inputs[1])
#                        assert i is not None
#                        if isinstance(i._dtype, HBits):
#                            i = int(i)
#                            dataWidth = outObj._portDataOut._dtype.bit_length()
#                            if i >= dataWidth:  # _valid or _validNB
#                                assert i < dataWidth + 2
#                                return
#            usedInputs.append(outObj)
#
#        elif isinstance(outObj, HlsNetNodeExplicitSync):
#            assert outObj in self.blockBoudary, (
#                "HlsNetNodeExplicitSync should be used only to separate blocks and should not appear inside of block", out)
#
#        else:
#            for o in outObj.dependsOn:
#                if o in self.blockBoudary:
#                    continue
#                self._collectInputValidityFlags(o, outObj, usedInputs)
#
#    def resolveControlOutput(self, out: Union[HlsNetNodeOutAny, Literal[0, 1]]):
#        """
#        Resolve some output which is used in control, which must never get into invalid state.
#        To assert this this algorithm collects all validity flags from inputs of expression tree
#        for this output and "ands them" with this output "o" 
#        
#        :attention: non-blocking reads are ignored as the and with valid flag should be done
#            by used. By using of non-blocking user declares that the validity is handled by user.
#        :note: reads/writes may be converted automatically by predication, but if it is the case
#            conditions should be already updated
#
#        :param out: an output port where the mask with vld of source IO should be applied if required.
#        """
#        if isinstance(out, int):
#            assert out in (0, 1), out
#            return out
#
#        usedInputs: SetList[HlsNetNodeExplicitSync] = SetList()
#        self._collectInputValidityFlags(out, None, usedInputs)
#        if usedInputs:
#            b = self.builder
#            andMembers = [out]
#            for rw in usedInputs:
#                if isinstance(rw, HlsNetNodeRead) and rw._rtlUseValid:
#                    # ack = (vld & ec) | sw
#                    # (if sw this out should already contain circuit which manages this case and the input rw is not really required)
#                    ec = rw.getExtraCondDriver()
#                    sw = rw.getSkipWhenDriver()
#                    vld = b.buildAndOptional(ec, rw.getValidNB())
#                    if sw is not None:
#                        ack = b.buildOr(vld, sw)
#                    else:
#                        ack = vld
#                    andMembers.append(ack)
#
#            if len(andMembers) > 1:
#                newOut = b.buildAndVariadic(andMembers)
#                return newOut
#            else:
#                return out
#        else:
#            return out
#