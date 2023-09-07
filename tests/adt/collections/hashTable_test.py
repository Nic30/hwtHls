#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtHls.platform.xilinx.artix7 import Artix7Slow
from hwtSimApi.utils import freq_to_period
from tests.baseSsaTest import BaseSsaTC
from tests.adt.collections.hashTable import HashTable
from tests.adt.collections.hashTableIo import HASH_TABLE_CMD


class HashTable_TC(BaseSsaTC):
    __FILE__ = __file__

    def _cmd(self, cmd: HASH_TABLE_CMD, itemValid: bool, key: int, value: int, index: int):
        return (cmd, int(itemValid), key, value, index)

    def test_SWAP_BY_INDEX(self):
        u = HashTable()
        u.ITEMS_PER_TABLE = 8
        u.CLK_FREQ = int(100e6)
        self.compileSimAndStart(u, target_platform=Artix7Slow())
        
        KEY_VALUE_PAIRS = [
            (1, 2),
            (3, 4),
            (5, 6),
            (7, 8),
            (1, 9),
        ]

        u.cmd._ag.data.extend(self._cmd(HASH_TABLE_CMD.SWAP_BY_INDEX, 1, key, value, key)  for key, value in KEY_VALUE_PAIRS)
        
        self.runSim(int((len(KEY_VALUE_PAIRS) * 2 + 4) * freq_to_period(u.CLK_FREQ)))

        cmdResRef = []
        memRef = {}
        for k, v in KEY_VALUE_PAIRS:
            prevVal = memRef.get(k, None)
            memRef[k] = v
            cmdResRef.append((HASH_TABLE_CMD.SWAP_BY_INDEX,  # cmd 
                              None if prevVal is None else 1,  # found
                              k,  # index
                              1 if prevVal else None,  # originalItemValid
                              None if prevVal is None else k,  # originalKey
                              None if prevVal is None else prevVal  # originalValue
                              ))
            
        self.assertValSequenceEqual(u.cmdRes._ag.data, cmdResRef)
        mem = self.rtl_simulator.model.tableRam_inst.io.ram_memory.val.val

        for key in sorted(memRef.keys()):
            item = mem[key]
            value = memRef[key]
            itemRef = u.item_t.from_py({
                "itemValid": 1,
                "key": key,
                "value": value,
            })._reinterpret_cast(u.item_flat_t)
            self.assertValEqual(item, int(itemRef), repr(item))


if __name__ == "__main__":
    import unittest

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([HashTable_TC("test_frameHeader")])
    suite = testLoader.loadTestsFromTestCase(HashTable_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
