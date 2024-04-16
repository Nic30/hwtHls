from enum import Enum
from typing import Tuple, List, Union

from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.nodes.backedge import HlsNetNodeReadBackedge, \
    HlsNetNodeWriteBackedge
from hwtHls.netlist.nodes.forwardedge import HlsNetNodeReadForwardedge, \
    HlsNetNodeWriteForwardedge
from hwtHls.netlist.nodes.read import HlsNetNodeRead

HlsNetNodeReadAnyChannel = Union[HlsNetNodeReadForwardedge, HlsNetNodeReadBackedge]
HlsNetNodeWriteAnyChannel = Union[HlsNetNodeWriteForwardedge, HlsNetNodeWriteBackedge]

HlsNetNodeReadOrWriteToAnyChannel = Union[
    HlsNetNodeReadForwardedge,
    HlsNetNodeWriteForwardedge,
    HlsNetNodeReadBackedge,
    HlsNetNodeWriteBackedge]


class LOOP_CHANEL_GROUP_ROLE(Enum):
    """
    An enum of roles for a channel somehow controlling the behaviour of the loop.
    """
    ENTER = 0  # data is blocked uness loop iteration is finished, recieve causes loop to execute
    EXIT_TO_SUCCESSOR = 1  # loop finishes current iteration and is ready to receive new data in next clock period, this channel
        # connects exit point in loop with section behind the loop, after exit
    EXIT_NOTIFY_TO_HEADER = 2  # this channel reads from exit to a loop header to notify about the exit
    REENTER = 3  # loop continues new iteration


class LoopChanelGroup():
    """
    This object aggregates IO channels to/from the loop.
    It exists because when the channel of the loop is optimized it may affect the loop or other channels.

    :note: This object is usually generated for the enter/reenter/exit edges in CFG. 
    :note: One LoopChanelGroup may be io group in multiple loops. For example exit from current and parent loop.
    
    :ivar origin: a list of tuples src basic block number, dst basic block number which is used for better name generation
        and identification of the group
    :ivar members: a list of reads/writes which are accessing the channels connected to the same loop.
    """

    def __init__(self, origin: List[Union[Tuple[int, int], Tuple[int, int, LOOP_CHANEL_GROUP_ROLE]]]):
        self.origin = origin
        self.members: UniqList[HlsNetNodeWriteAnyChannel] = UniqList()
        self.connectedLoops: List[Tuple["HlsNetNodeLoopStatus", LOOP_CHANEL_GROUP_ROLE]] = []

    def appendWrite(self, ch: HlsNetNodeWriteAnyChannel, isControl: bool):
        assert ch._loopChannelGroup is None, (ch, ch._loopChannelGroup)
        ch._loopChannelGroup = self
        assert ch not in self.members, (self, ch)
        if isControl or not self.members:
            self.members.append(ch)
        else:
            c = self.members.pop()
            self.members.append(ch)
            self.members.append(c)

    def associateWithLoop(self, loop: "HlsNetNodeLoopStatus", role:LOOP_CHANEL_GROUP_ROLE):
        self.connectedLoops.append((loop, role))

    def getChannelWhichIsUsedToImplementControl(self) -> HlsNetNodeWriteAnyChannel:
        return self.members[-1]

    def getRoleForLoop(self, loop: "HlsNetNodeLoopStatus") -> LOOP_CHANEL_GROUP_ROLE:
        for l, role in self.connectedLoops:
            if l is loop:
                return role
        raise KeyError("This group is not associated with requested loop", loop)
    
    
    def destroy(self):
        """
        delete itself from every member
        """
        assert not self.connectedLoops, self
        for m in self.members:
            if isinstance(m, HlsNetNodeRead):
                m = m.associatedWrite
            assert m._loopChannelGroup is self
            m._loopChannelGroup = None
        
    def __repr__(self):
        origin = [(o[0], o[1], o[2].name) if len(o) == 3 else o for o in self.origin]
        return  f"<{self.__class__.__name__:s} origin:{origin}, channels:{[(w._id, w.associatedRead._id) for w in self.members]} loops:{[(l._id, r.name) for l, r in self.connectedLoops]}>"

