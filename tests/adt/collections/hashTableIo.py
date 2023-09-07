from typing import Optional

from hwt.hdl.types.bits import Bits
from hwt.hdl.types.hdlType import HdlType
from hwt.interfaces.agents.handshaked import UniversalHandshakedAgent
from hwt.interfaces.std import HandshakeSync, Signal, VectSignal
from hwt.math import log2ceil
from hwt.synthesizer.param import Param
from hwtSimApi.hdlSimulator import HdlSimulator


class HASH_TABLE_CMD():
    """
    :cvar LOOKUP: use key to find an item and return it
    :cvar SWAP: use key to find item and replace it with input, the replaced item may be empty
        (the key does not need to match for swap to happen)
    :cvar READ_BY_INDEX: use index to read a specific item from table
    :cvar SWAP_BY_INDEX: use index to replace item with a specific item, original item is returned
    """
    LOOKUP = 0
    SWAP = 1
    READ_BY_INDEX = 2
    SWAP_BY_INDEX = 3


class HashTableCmd(HandshakeSync):
    """
    A command port of a hash table engines.

    :ivar KEY_T: type of the key in table
    :ivar VALUE_T: type of the value stored in the table
    :ivar ID_T: type of the identifier of the transaction, not used in this unit, but can be used to pass data trough
    :ivar TABLE_CNT: number of tables used by cuckoo hash scheme
    :ivar ITEMS_PER_TABLE: number of items in a single table used by cuckoo hash table

    :ivar cmd: see :class:`~.HASH_TABLE_CMD`
    :ivar itemValid: value of itemValid stored in the table, can be used to delete or add item
    :ivar table_oh: one hot encoded index of subtable if TABLE_CNT>1
    :ivar index: index of the item referenced by this command
    :ivar value: item value to store/update (if VALUE_T is not None)
    """

    def _config(self) -> None:
        self.KEY_T = Param(Bits(5))
        self.VALUE_T: Optional[HdlType] = Param(Bits(32))
        self.ID_T: Optional[HdlType] = Param(None)
        self.TABLE_CNT = Param(1)
        self.ITEMS_PER_TABLE = Param(16)

    def _declr(self):
        HandshakeSync._declr(self)
        if self.ID_T is not None:
            self.id = Signal(self.ID_T)
        self.cmd = Signal(Bits(2))
        self.itemValid = Signal()
        self.key = Signal(self.KEY_T)
        if self.VALUE_T is not None:
            self.value = Signal(self.VALUE_T)
        self.index = Signal(Bits(log2ceil(self.ITEMS_PER_TABLE)))
        if self.TABLE_CNT > 1:
            self.table_oh = VectSignal(self.TABLE_CNT)

    def _initSimAgent(self, sim:HdlSimulator):
        self._ag = UniversalHandshakedAgent(sim, self)


class HashTableCmdResult(HandshakeSync):
    """
    A port with a result for :class:`~.HashTableCmd`

    :ivar cmd: original signal with command
    :ivar found: 1 if lookup found the key
    :ivar originalItemValid: the itemValid from the data originally stored in the table
    :ivar originalKey: the key from the data originally stored in the table
    :ivar originalValue: the value from the data originally stored in the table (if VALUE_T is not None)
    """

    def _config(self) -> None:
        HashTableCmd._config(self)

    def _declr(self):
        HandshakeSync._declr(self)
        if self.ID_T is not None:
            self.id = Signal(self.ID_T)

        self.cmd = Signal(Bits(2))
        # the item which was originally stored in table or result of LOOKUP/READ_BY_INDEX
        self.found = Signal()
        self.index = Signal(Bits(log2ceil(self.ITEMS_PER_TABLE)))
        if self.TABLE_CNT > 1:
            self.table_oh = VectSignal(self.TABLE_CNT)
        self.originalItemValid = Signal()
        self.originalKey = Signal(self.KEY_T)
        if self.VALUE_T is not None:
            self.originalValue = Signal(self.VALUE_T)

    def _initSimAgent(self, sim:HdlSimulator):
        self._ag = UniversalHandshakedAgent(sim, self)
