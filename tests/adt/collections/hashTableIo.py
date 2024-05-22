from typing import Optional

from hwt.hdl.types.bits import HBits
from hwt.hdl.types.hdlType import HdlType
from hwt.hwIOs.agents.rdVldSync import UniversalRdVldSyncAgent
from hwt.hwIOs.std import HwIORdVldSync, HwIOSignal, HwIOVectSignal
from hwt.hwParam import HwParam
from hwt.math import log2ceil
from hwt.pyUtils.typingFuture import override
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


class HashTableCmd(HwIORdVldSync):
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

    @override
    def hwConfig(self) -> None:
        self.KEY_T = HwParam(HBits(5))
        self.VALUE_T: Optional[HdlType] = HwParam(HBits(32))
        self.ID_T: Optional[HdlType] = HwParam(None)
        self.TABLE_CNT = HwParam(1)
        self.ITEMS_PER_TABLE = HwParam(16)

    @override
    def hwDeclr(self):
        HwIORdVldSync.hwDeclr(self)
        if self.ID_T is not None:
            self.id = HwIOSignal(self.ID_T)
        self.cmd = HwIOSignal(HBits(2))
        self.itemValid = HwIOSignal()
        self.key = HwIOSignal(self.KEY_T)
        if self.VALUE_T is not None:
            self.value = HwIOSignal(self.VALUE_T)
        self.index = HwIOSignal(HBits(log2ceil(self.ITEMS_PER_TABLE)))
        if self.TABLE_CNT > 1:
            self.table_oh = HwIOVectSignal(self.TABLE_CNT)

    @override
    def _initSimAgent(self, sim:HdlSimulator):
        self._ag = UniversalRdVldSyncAgent(sim, self)


class HashTableCmdResult(HwIORdVldSync):
    """
    A port with a result for :class:`~.HashTableCmd`

    :ivar cmd: original signal with command
    :ivar found: 1 if lookup found the key
    :ivar originalItemValid: the itemValid from the data originally stored in the table
    :ivar originalKey: the key from the data originally stored in the table
    :ivar originalValue: the value from the data originally stored in the table (if VALUE_T is not None)
    """

    @override
    def hwConfig(self) -> None:
        HashTableCmd.hwConfig(self)

    @override
    def hwDeclr(self):
        HwIORdVldSync.hwDeclr(self)
        if self.ID_T is not None:
            self.id = HwIOSignal(self.ID_T)

        self.cmd = HwIOSignal(HBits(2))
        # the item which was originally stored in table or result of LOOKUP/READ_BY_INDEX
        self.found = HwIOSignal()
        self.index = HwIOSignal(HBits(log2ceil(self.ITEMS_PER_TABLE)))
        if self.TABLE_CNT > 1:
            self.table_oh = HwIOVectSignal(self.TABLE_CNT)
        self.originalItemValid = HwIOSignal()
        self.originalKey = HwIOSignal(self.KEY_T)
        if self.VALUE_T is not None:
            self.originalValue = HwIOSignal(self.VALUE_T)

    @override
    def _initSimAgent(self, sim:HdlSimulator):
        self._ag = UniversalRdVldSyncAgent(sim, self)
