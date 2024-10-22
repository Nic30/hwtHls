from copy import copy
from enum import Enum
from typing import Tuple, List, Union, Self, Optional

from hwt.pyUtils.setList import SetList
from hwtHls.netlist.nodes.backedge import HlsNetNodeReadBackedge, \
    HlsNetNodeWriteBackedge
from hwtHls.netlist.nodes.forwardedge import HlsNetNodeReadForwardedge, \
    HlsNetNodeWriteForwardedge
from hwtHls.netlist.nodes.node import _HlsNetNodeDeepcopyNil
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.nodes.ports import HlsNetNodeOut

HlsNetNodeReadAnyChannel = Union[HlsNetNodeReadForwardedge, HlsNetNodeReadBackedge]
HlsNetNodeWriteAnyChannel = Union[HlsNetNodeWriteForwardedge, HlsNetNodeWriteBackedge]

HlsNetNodeReadOrWriteToAnyChannel = Union[
    HlsNetNodeReadForwardedge,
    HlsNetNodeWriteForwardedge,
    HlsNetNodeReadBackedge,
    HlsNetNodeWriteBackedge]


class LOOP_CHANEL_GROUP_ROLE(Enum):
    """
    An enum of roles for a channel somehow controlling the behavior of the loop.
    
    :cvar ENTER: data is blocked unless loop iteration is finished, receive causes loop to execute
    :cvar EXIT_TO_SUCCESSOR: loop finishes current iteration and is ready to receive new data
        in next clock period, this channel connects exit point in loop with section behind the loop, after exit
    :cvar EXIT_NOTIFY_TO_HEADER: this channel reads from exit to a loop header to notify about the exit
    :cvar REENTER: loop continues another iteration
    :cvar NON_LOOP: this represents a jump between basic blocks which is not related to a loop
    """
    ENTER = 0
    EXIT_TO_SUCCESSOR = 1
    EXIT_NOTIFY_TO_HEADER = 2
    REENTER = 3
    NON_LOOP_IN = 4
    NON_LOOP_OUT = 5

    def getMinifiedName(self):
        return _LOOP_CHANEL_GROUP_ROLE_MINIFIED_NAME[self]


_LOOP_CHANEL_GROUP_ROLE_MINIFIED_NAME = {
    LOOP_CHANEL_GROUP_ROLE.ENTER: "enter",
    LOOP_CHANEL_GROUP_ROLE.EXIT_TO_SUCCESSOR: "exit",
    LOOP_CHANEL_GROUP_ROLE.EXIT_NOTIFY_TO_HEADER: "exitNofity",
    LOOP_CHANEL_GROUP_ROLE.REENTER: "reenter",
    LOOP_CHANEL_GROUP_ROLE.NON_LOOP_IN: "in",
    LOOP_CHANEL_GROUP_ROLE.NON_LOOP_OUT: "out",
}


class BlockEdgeChannelGroup():
    """
    Group of channels used to implement channels for block liveins/livouts on edge between MachineBasicBlocks
    
    :ivar ~.origin: the number of src and dst MachineBasicBlock for which this group is build
    :ivar members: a list of writes in this group
    """

    def __init__(self, srcBB: int, dstBB: int):
        self.srcBB = srcBB
        self.dstBB = dstBB

    def __eq__(self, other):
        return (self.__class__ is other.__class__ and
                self.srcBB == other.srcBB and
                self.dstBB == other.dstBB)

    def __hash__(self):
        return hash((self.srcBB, self.dstBB))


class LoopChanelGroup():
    """
    This object aggregates IO channels to/from the loop.
    It exists because when the channel of the loop is optimized it may affect the loop or other channels.

    :note: This object is usually generated for the enter/reenter/exit edges in CFG. 
    :note: One LoopChanelGroup may be io group in multiple loops. For example exit from current and parent loop.
    
    :ivar origin: a list of tuples src basic block number, dst basic block number which is used for better name generation
        and identification of the group
    :ivar members: a list of writes which are accessing the channels connected to the same loop.
    :ivar connectedLoopsAndBlocks: 
    """

    def __init__(self, origin: List[Union[Tuple[int, int],
                                          Tuple[int, int, LOOP_CHANEL_GROUP_ROLE]]]):
        self.origin = origin
        self.members: SetList[HlsNetNodeWriteAnyChannel] = SetList()
        self.connectedLoopsAndBlocks: List[Tuple[Union["HlsNetNodeLoopStatus", BlockEdgeChannelGroup], LOOP_CHANEL_GROUP_ROLE]] = []

    def clone(self, memo: dict) -> Tuple["LoopChanelGroup", bool]:
        d = id(self)
        y = memo.get(d, _HlsNetNodeDeepcopyNil)
        if y is not _HlsNetNodeDeepcopyNil:
            return y, False

        y: LoopChanelGroup = copy(self)
        memo[d] = y
        y.members = SetList(c.clone(memo, True)[0] for c in self.members)
        self.connectedLoopsAndBlocks = [(lcg.clone(memo, True)[0], role) for lcg, role in self.connectedLoopsAndBlocks]

        return y, True

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
        self.connectedLoopsAndBlocks.append((loop, role))

    def getChannelUsedAsControl(self) -> HlsNetNodeWriteAnyChannel:
        return self.members[-1]

    def getRoleForLoop(self, loop: "HlsNetNodeLoopStatus") -> LOOP_CHANEL_GROUP_ROLE:
        for l, role in self.connectedLoopsAndBlocks:
            if l is loop:
                return role
        raise KeyError("This group is not associated with requested loop", loop)

    def destroy(self):
        """
        delete itself from every member
        """
        assert not self.connectedLoopsAndBlocks, self
        for m in self.members:
            if isinstance(m, HlsNetNodeRead):
                m = m.associatedWrite
            assert m._loopChannelGroup is self
            m._loopChannelGroup = None

    def __repr__(self):
        origin = [(o[0], o[1], o[2].name) if len(o) == 3 else o for o in self.origin]
        return  f"<{self.__class__.__name__:s} origin:{origin}, channels:{[(w._id, w.associatedRead._id) for w in self.members]} loops:{[(l._id, r.name) for l, r in self.connectedLoopsAndBlocks]}>"

    @staticmethod
    def appendToListOfPriorityEncodedReads(channelGroupList: List[Self],
                                           extraCondOfFirst:Optional[HlsNetNodeOut],
                                           skipWhenOfFirst: Optional[HlsNetNodeOut],
                                           itemToAdd: Self,
                                           name:Optional[str]=None):
        controlChannelW = itemToAdd.getChannelUsedAsControl()
        controlChannelR: HlsNetNodeRead = controlChannelW.associatedRead

        b: HlsNetlistBuilder = controlChannelR.getHlsNetlistBuilder()
        if channelGroupList:
            lastRead: HlsNetNodeRead = channelGroupList[-1].getChannelUsedAsControl().associatedRead
            assert controlChannelR.parent is lastRead.parent, (controlChannelR, lastRead, controlChannelR.parent, lastRead.parent)
            lastRead.setNonBlocking()  # all except last are non blocking
            lastVld = lastRead.getValidNB()
            lastVld_n = b.buildNot(lastVld)
            lastEC = lastRead.dependsOn[lastRead.extraCond.in_i] if lastRead.extraCond is not None else None
            lastSW = lastRead.dependsOn[lastRead.skipWhen.in_i] if lastRead.skipWhen is not None else None
            controlEc = b.buildAndOptional(lastEC, lastVld_n, name=None if name is None else f"{name:s}_extraCond")
            controlSw = b.buildOrOptional(lastSW, lastVld, name=None if name is None else f"{name:s}_extraCond")
        else:
            controlEc = extraCondOfFirst
            controlSw = skipWhenOfFirst
        if controlEc is not None:
            controlChannelR.addControlSerialExtraCond(controlEc)
        if controlSw is not None:
            controlChannelR.addControlSerialSkipWhen(controlSw)

        controlVld = controlChannelR.getValidNB()
        controlVld_n = b.buildNot(controlVld)
        if len(itemToAdd.members) > 1:
            dataEc = b.buildAndOptional(controlEc, controlVld, name=None if name is None else f"{name:s}_data_extraCond")
            dataSw = b.buildOrOptional(controlSw, controlVld_n, name=None if name is None else f"{name:s}_data_skipWhen")
            for channelW in itemToAdd.members:
                if channelW is controlChannelW:
                    continue
                if dataEc is not None:
                    channelW.associatedRead.addControlSerialExtraCond(dataEc)
                if dataSw is not None:
                    channelW.associatedRead.addControlSerialSkipWhen(dataSw)

        # assert not r._isBlocking, r
        assert itemToAdd not in channelGroupList, itemToAdd
        channelGroupList.append(itemToAdd)

