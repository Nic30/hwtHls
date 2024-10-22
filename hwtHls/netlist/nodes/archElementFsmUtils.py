#from typing import List, Dict, Union, Self
#
#from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
#from hwtHls.netlist.nodes.node import HlsNetNode
#
#
#FsmMetaStateItem = List[HlsNetNode]
#
#
#class FsmMeta():
#    """
#    :ivar states: list of FsmMetaStateItem representing this FSM native nodes (index is clkIndex).
#    :ivar transitionTable: a dictionary source stateI to dictionary destination stateI to condition for transition
#    :note: Initially the transitionTable is empty and states are being executed in order specified in sates list.
#        Then non-linear transitions are discovered in ArchElementFsm.
#
#    :note: Only direct children are present in states, children may also be FSM.
#    :note: Some states may be empty, index in states corresponds to clock period index in scheduling.
#    """
#
#    def __init__(self):
#        self.states: List[FsmMetaStateItem] = []
#        self.transitionTable: Dict[int, Dict[int, Union[bool, RtlSignal]]] = {}
#
#    def addState(self, clkI: int):
#        """
#        :param clkI: an index of clk cycle where this state was scheduled
#        """
#        # stateNodes: List[HlsNetNode] = []
#        # stI = len(self.states)
#        assert clkI >= 0, clkI
#        try:
#            return self.states[clkI]
#        except IndexError:
#            pass
#
#        for _ in range(clkI + 1 - len(self.states)):
#            self.states.append([])
#
#        return self.states[clkI]
#
#    # def addStateFromChild(self, clkI: int, child: ArchElement):
#    #    assert clkI >= 0, clkI
#    #    try:
#    #        st = self.states[clkI]
#    #        assert (child, clkI) not in st
#    #    except IndexError:
#    #        for _ in range(clkI + 1 - len(self.states)):
#    #            st = [ ]
#    #            self.states.append(st)
#    #    st.append((child, clkI))
#
#    def hasUsedStateForClkI(self, clkI: int) -> bool:
#        return clkI < len(self.states) and self.states[clkI]
#
#    def mergeFsm(self, other: Self):
#        # rename FSM states in FSM to match names in dst
#        for clkI, srcSt in enumerate(other.states):
#            dstSt = self.addState(clkI)
#            dstSt.extend(srcSt)
