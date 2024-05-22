from hwt.pyUtils.setList import SetList
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResourceItem
from hwtHls.architecture.transformation.rtlArchPass import RtlArchPass
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.archElement import ArchElement
from hwt.pyUtils.typingFuture import override
from hwtLib.abstract.componentBuilder import AbstractComponentBuilder
from hwtLib.examples.hierarchy.extractHierarchy import extractRegsToSubmodule


class RtlArchPassTransplantArchElementsToSubunits(RtlArchPass):
    '''
    Create an individual unit instance for each architectural element instance.
    
    Implementation variants:
    * as a special type of HlsNetNode
        + specifies timing of individual IO
        - complicated rewriting of the HLS netlist
        - potentially complicated HLS netlist transformations
        - limited scope of RTL optimizations
          or complicated rewrite of inputs/outputs, complicated tracking of usage
        - hard to pinpoint exact times when IO happens before RTL allocations
          
    * as a different unit for each arch element instance before allocation:
        + circuit constructed directly on the place where it will be
        - limited scope of RTL optimizations
          or complicated rewrite of inputs/outputs, complicated tracking of usage
        - hard to pinpoint exact times when IO happens before RTL allocations
          
    * after RTL allocation of each element:
        + implementation as an optional pass
        + global scope of RTL optimizations
        - rewrite of whole circuit, monkey patching
        - non linear translation flow    

    * :note: During RTL synthesis the synchronization of channels is implemented which is a main subject
        for late RTL optimizations, because the generated code is highly non linear and stateful the HlsNetlist
        representation is sub-optimal because it does not contain registers and operation nodes can move freely in time.
        This is the reason for the existence of RtlNetlist and its optimizations in the first place.
        This implies that we can not easily transfer RtlNetlist optimizations to HlsNetlist.
    
    After whole RTL is allocated iterate every element and wrap its statements into a unit instance.
    Each signal is private to this newly extracted unit if used only by this element.
    '''
    @override
    def runOnHlsNetlistImpl(self, netlist: HlsNetlistCtx):
        parentHwModule = netlist.parentHwModule
        for e in netlist.nodes:
            e: ArchElement
            for pipeline_st_i, con in enumerate(e.connections):
                stateRegisters = SetList()
                for v in con.signals:
                    v: TimeIndependentRtlResourceItem
                    # if the value has a register at the end of this stage
                    v = v.parent.checkIfExistsInClockCycle(pipeline_st_i + 1)
                    if v is not None and v.isRltRegister():
                        stateRegisters.append(v.data)

                if not stateRegisters:
                    continue

                stRegsExtracted = extractRegsToSubmodule(stateRegisters)
                name = AbstractComponentBuilder(parentHwModule, None, "")._findSuitableName(
                    f"{e.name:s}st{pipeline_st_i:d}_regs",
                    firstWithoutCntrSuffix=True)
                setattr(parentHwModule, name, stRegsExtracted)

