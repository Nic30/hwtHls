from hwt.pyUtils.uniqList import UniqList
from hwtHls.architecture.archElement import ArchElement
from hwtHls.architecture.transformation.rtlArchPass import RtlArchPass
from hwtLib.abstract.componentBuilder import AbstractComponentBuilder
from hwtLib.examples.hierarchy.extractHierarchy import extractRegsToSubunit
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource


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

    def apply(self, hls: "HlsScope", netlist: HlsNetlistCtx):
        parentUnit = netlist.parentUnit
        for e in netlist.allocator._archElements:
            e: ArchElement
            for pipeline_st_i, con in enumerate(e.connections):
                stateRegisters = UniqList()
                for s in con.signals:
                    s: TimeIndependentRtlResource
                    # if the value has a register at the end of this stage
                    v = s.checkIfExistsInClockCycle(pipeline_st_i)
                    if v.isExplicitRegister:
                        stateRegisters.append(v.data)
                    else:
                        v = s.checkIfExistsInClockCycle(pipeline_st_i + 1)
                        if v is not None and v.isRltRegister():
                            stateRegisters.append(v.data)

                if not stateRegisters:
                    continue
                stRegsExtracted = extractRegsToSubunit(stateRegisters)
                name = AbstractComponentBuilder(parentUnit, None, "")._findSuitableName(
                    f"{e.namePrefix:s}st{pipeline_st_i:d}_regs",
                    firstWithoutCntrSuffix=True)
                setattr(parentUnit, name, stRegsExtracted)
            
