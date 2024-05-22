#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import List

from hwt.code import In, Concat, Or, And
from hwt.constants import WRITE, READ
from hwt.hwIOs.hwIOStruct import HwIO_to_HdlType, HwIOStruct
from hwt.hwIOs.utils import addClkRstn, propagateClkRstn
from hwt.hwModule import HwModule
from hwt.hObjList import HObjList
from hwt.hwParam import HwParam
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.defs import BIT
from hwt.hdl.types.struct import HStruct
from hwt.math import log2ceil
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.pyBytecode.ioProxyAddressed import IoProxyAddressed
from hwtHls.frontend.pyBytecode.markers import PyBytecodeInline
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.io.bram import BramArrayProxy
from hwtHls.io.portGroups import MultiPortGroup
from hwtHls.scope import HlsScope
from hwtLib.mem.ram import RamSingleClock
from pyMathBitPrecise.bit_utils import mask
from tests.adt.collections.hashTableIo import HashTableCmd, HashTableCmdResult, \
    HASH_TABLE_CMD


class HashTableCuckoo(HwModule):
    """
    Hash table utilizing Cuckoo hashing scheme
    
    :see: :class:`tests.frontend.pyBytecode.hashTableIo.HashTableCmd`
    :ivar STASH_CAM_SIZE: size of temporal memory for moving items between tables in cuckoo hash scheme
        also used to store items if the table is full
    """

    def _config(self) -> None:
        HashTableCmd._config(self)
        self.STASH_CAM_SIZE = HwParam(3)
        self.CLK_FREQ = HwParam(int(40e6))

    def _declr(self) -> None:
        assert self.TABLE_CNT > 0
        assert self.ITEMS_PER_TABLE >= 2
        assert self.STASH_CAM_SIZE >= 1
        
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        with self._hwParamsShared():
            self.cmd = HashTableCmd()
            self.cmdRes = HashTableCmdResult()._m()
            for i in [self.cmd, self.cmdRes]:
                if self.STASH_CAM_SIZE:
                    i.TABLE_CNT += 1
                i.ITEMS_PER_TABLE = max(self.STASH_CAM_SIZE, self.ITEMS_PER_TABLE)
        self.item_t = item_t = HStruct(
            (BIT, "itemValid"),
            (self.KEY_T, "key"),
            (self.VALUE_T, "value"),
        )
        RAM_ADDR_WIDTH = log2ceil(self.ITEMS_PER_TABLE)
        RAM_DATA_WIDTH = item_t.bit_length()
        tableRams = HObjList()
        for _ in range(self.TABLE_CNT):
            t = RamSingleClock()
            t.ADDR_WIDTH = RAM_ADDR_WIDTH
            t.DATA_WIDTH = RAM_DATA_WIDTH
            t.PORT_CNT = (READ, WRITE)
            tableRams.append(t)

        self.tableRams = tableRams

    def hash(self, key: RtlSignal, table_i: int, res: RtlSignal):
        """
        :attention: This methods should be overridden in implementation of this abstract component
        """
        res(key[res._dtype.bit_length():])

    @PyBytecodeInline
    @staticmethod
    def _copyItem(src: HwIOStruct, dst: HwIOStruct):
        dst.itemValid = src.itemValid
        dst.key = src.key
        dst.value = src.value

    @PyBytecodeInline
    @staticmethod
    def _copyOriginalItem(src: HwIOStruct, dst: HashTableCmdResult):
        dst.originalItemValid = src.itemValid
        dst.originalKey = src.key
        dst.originalValue = src.value

    @staticmethod
    def _isFirstEmpty(occupiedFlags: RtlSignal, index:int):
        return ~occupiedFlags[index] & (occupiedFlags[index:]._eq(mask(index)) if index > 0 else 1)

    def mainThread(self, hls: HlsScope, rams: List[IoProxyAddressed]):
        item_t = self.item_t
        item_flat_t = HBits(item_t.bit_length())
        res_t = HwIO_to_HdlType().apply(self.cmdRes, exclude=(self.cmdRes.rd, self.cmdRes.vld))
        ram_index_t = self.tableRams[0].port[0].addr._dtype

        # stash is used to accommodate items which do not fit into main tables due to hash collisions
        # it is also used as a Scratchpad memory for moving of items between tables
        stash = [hls.var(f"stash{i:d}", item_t) for i in range(self.STASH_CAM_SIZE)]
        # reset value for stash valid registers
        for d in stash:
            d.itemValid = 0

        while BIT.from_py(1):
            cmd = hls.read(self.cmd).data
            indexes = [hls.var(f"ram{tI:d}_index", ram_index_t) for tI, _ in enumerate(rams)]
            if In(cmd.cmd, [HASH_TABLE_CMD.LOOKUP, HASH_TABLE_CMD.SWAP]):
                for i, index in enumerate(indexes):
                    # index = cmd.key[index._dtype.bit_length():]
                    PyBytecodeInline(self.hash)(cmd.key, i, index)
            else:
                for index in indexes:
                    # call used instead of assignment because index is a reference in preproc var. and we need to assign value
                    index(cmd.index)

            res = res_t.from_py(None)
            res.found = 0
            if self.ID_T is not None:
                res.id = cmd.id

            curData = [hls.read(ram[i]).data._reinterpret_cast(item_t) for ram, i in zip(rams, indexes)]
            # find in tables or in stash
            foundInRam = Concat(*(d.itemValid & d.key._eq(cmd.key) for d in reversed(curData)))
            occupiedInRam = Concat(*(d.itemValid for d in reversed(curData)))
            foundInStash = Concat(*(d.itemValid & d.key._eq(cmd.key) for d in reversed(stash)))
            occupiedInStash = Concat(*(d.itemValid for d in reversed(stash)))
            isSwap = cmd.cmd._eq(HASH_TABLE_CMD.SWAP)
            isSwapByIndex = cmd.cmd._eq(HASH_TABLE_CMD.SWAP_BY_INDEX)

            for i, (ram, index, d) in enumerate(zip(rams, indexes, curData)):
                swapThis = isSwapByIndex & cmd.table_oh[i]
                _found = foundInRam[i] | swapThis
                if _found:
                    self._copyOriginalItem(d, res)
                    res.index = index
                    res.table_oh = 1 << i

                if isSwap | swapThis:
                    newItem = item_t.from_py(None)
                    self._copyItem(d, newItem)
                    isFirstEmpty = self._isFirstEmpty(occupiedInRam, i)
                    if _found | (isFirstEmpty & foundInStash._eq(0)):
                        hls.write(newItem._reinterpret_cast(item_flat_t), ram[index])

            stashTableI = len(rams)
            for i, d in enumerate(stash):
                swapThis = isSwapByIndex & cmd.table_oh[stashTableI]
                _found = foundInStash[i] | swapThis
                if _found:
                    self._copyOriginalItem(d, res)
                    res.index = i
                    res.table_oh = 1 << stashTableI

                if _found | (self._isFirstEmpty(occupiedInStash, i) & occupiedInStash._eq(0)):
                    self._copyItem(cmd, d)

            res.found = Or(*foundInRam, *foundInStash)
            if cmd.cmd._eq(HASH_TABLE_CMD.READ_BY_INDEX) | cmd.cmd._eq(HASH_TABLE_CMD.SWAP_BY_INDEX):
                res.index = cmd.index
                res.table_oh = cmd.table_oh
            
            if ~res.found & And(*occupiedInRam, *occupiedInStash):
                while stash[-1].itemValid:
                    # [todo] deadlock if the stash is full (not implemented stash swapping)
                    pass

            hls.write(res, self.cmdRes)

    def _impl(self) -> None:
        propagateClkRstn(self)
        hls = HlsScope(self)
        rams = [BramArrayProxy(hls, MultiPortGroup(t.port)) for t in self.tableRams]
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls, rams)
        hls.addThread(mainThread)
        hls.compile()


if __name__ == "__main__":
    # from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synth import to_rtl_str
    from hwtHls.platform.xilinx.artix7 import Artix7Fast
    from hwtHls.platform.platform import HlsDebugBundle
    import sys
    sys.setrecursionlimit(int(10e6))
    for tableCnt in [1]: # ,2,3,4
        m = HashTableCuckoo()
        m.KEY_T = HBits(16)
        m.CLK_FREQ = int(100e6)
        m.TABLE_CNT = tableCnt
        m.STASH_CAM_SIZE = 1
        m.ITEMS_PER_TABLE = 1024
        print(to_rtl_str(m, target_platform=Artix7Fast(debugFilter=HlsDebugBundle.ALL_RELIABLE))) 
    
        #from sphinx_hwt.debugUtils import hwt_unit_to_html
        #hwt_unit_to_html(m, "tmp/HashTableCuckoo.scheme.html")
        #import sqlite3
        #import os
        #import datetime
        #from hwtBuildsystem.vivado.executor import VivadoExecutor
        #from hwtBuildsystem.vivado.part import XilinxPart
        #from hwtBuildsystem.examples.synthetizeHwModule import buildHwModule,\
        #   store_vivado_report_in_db
        #
        #
        #conn = sqlite3.connect('build_report.db')
        #c = conn.cursor()
        #logComunication = True
        #
        #start = datetime.datetime.now()
        #with VivadoExecutor(logComunication=logComunication) as executor:
        #    __pb = XilinxPart
        #    part = XilinxPart(
        #            __pb.Family.kintex7,
        #            __pb.Size._160t,
        #            __pb.Package.ffg676,
        #            __pb.Speedgrade._2)
        #    project = buildHwModule(executor, m, f"tmp/vivado{tableCnt:d}", part,
        #                        targetPlatform=Artix7Fast(debugDir=f"tmp/hls{tableCnt:d}"),
        #                  synthesize=True,
        #                  implement=False,
        #                  writeBitstream=False,
        #                  # openGui=True,
        #                  )
        #    name = ".".join([m.__class__.__module__, m.__class__.__qualname__])
        #    store_vivado_report_in_db(c, start, project, name)
        #    conn.commit()
        