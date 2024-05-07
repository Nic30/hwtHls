#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from typing import Optional

from hwt.code import In
from hwt.hdl.constants import WRITE, READ
from hwt.hdl.types.bits import Bits
from hwt.hdl.types.defs import BIT
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.types.struct import HStruct
from hwt.interfaces.structIntf import Interface_to_HdlType, StructIntf
from hwt.interfaces.utils import addClkRstn, propagateClkRstn
from hwt.math import log2ceil
from hwt.synthesizer.param import Param
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwt.synthesizer.unit import Unit
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.ioProxyAddressed import IoProxyAddressed
from hwtHls.frontend.pyBytecode.markers import PyBytecodeInline
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.io.bram import BramArrayProxy
from hwtHls.io.portGroups import MultiPortGroup
from hwtHls.scope import HlsScope
from hwtLib.mem.ram import RamSingleClock
from tests.adt.collections.hashTableIo import HashTableCmd, HashTableCmdResult, \
    HASH_TABLE_CMD


class HashTable(Unit):
    """
    Hash table without any hash collision resolution scheme.

    :see: :class:`tests.frontend.pyBytecode.hashTableIo.HashTableCmd`
    """

    def _config(self) -> None:
        self.KEY_T = Param(Bits(16))
        self.VALUE_T: Optional[HdlType] = Param(Bits(32))
        self.ID_T: Optional[HdlType] = Param(None)
        self.ITEMS_PER_TABLE = Param(1024)
        self.CLK_FREQ = Param(int(40e6))

    def _declr(self) -> None:
        assert self.ITEMS_PER_TABLE >= 2

        addClkRstn(self)
        with self._paramsShared():
            self.cmd = HashTableCmd()
            self.cmdRes: HashTableCmdResult = HashTableCmdResult()._m()
            for i in [self.cmd, self.cmdRes]:
                i.ITEMS_PER_TABLE = self.ITEMS_PER_TABLE

        self.item_t = item_t = HStruct(
            (BIT, "itemValid"),
            (self.KEY_T, "key"),
            (self.VALUE_T, "value"),
        )

        self.item_flat_t = Bits(item_t.bit_length())
        RAM_ADDR_WIDTH = log2ceil(self.ITEMS_PER_TABLE)
        RAM_DATA_WIDTH = item_t.bit_length()
        t = RamSingleClock()
        t.ADDR_WIDTH = RAM_ADDR_WIDTH
        t.DATA_WIDTH = RAM_DATA_WIDTH
        t.PORT_CNT = (READ, WRITE)

        self.tableRam = t

    @PyBytecodeInline
    @staticmethod
    def _copyItem(src: StructIntf, dst: StructIntf):
        dst.itemValid = src.itemValid
        dst.key = src.key
        dst.value = src.value

    @PyBytecodeInline
    @staticmethod
    def _copyOriginalItem(src: StructIntf, dst: HashTableCmdResult):
        dst.originalItemValid = src.itemValid
        dst.originalKey = src.key
        dst.originalValue = src.value

    @hlsBytecode
    def hash(self, key: RtlSignal, res: RtlSignal):
        # [todo] redefine this function in your implementation of this component
        res = key[res._dtype.bit_length():]

    @hlsBytecode
    def mainThread(self, hls: HlsScope, ram: IoProxyAddressed):
        item_t = self.item_t
        item_flat_t = self.item_flat_t
        res_t = Interface_to_HdlType().apply(self.cmdRes, exclude=(self.cmdRes.rd, self.cmdRes.vld))
        ram_index_t = self.tableRam.port[0].addr._dtype

        while BIT.from_py(1):
            cmd = hls.read(self.cmd).data

            # resolve index for ram read/write
            index = ram_index_t.from_py(None)
            if In(cmd.cmd, [HASH_TABLE_CMD.LOOKUP, HASH_TABLE_CMD.SWAP]):
                PyBytecodeInline(self.hash)(cmd.key, index)
            else:
                index = cmd.index

            d = hls.read(ram[index]).data._reinterpret_cast(item_t)

            res = res_t.from_py(None)
            res.cmd = cmd.cmd
            res.found = d.itemValid & d.key._eq(cmd.key)
            res.index = index
            self._copyOriginalItem(d, res)

            if cmd.cmd._eq(HASH_TABLE_CMD.SWAP) | cmd.cmd._eq(HASH_TABLE_CMD.SWAP_BY_INDEX):
                # d is currently found
                # cmd contains original item which was swapped
                newItem0 = item_t.from_py(None)
                self._copyItem(cmd, newItem0)
                hls.write(newItem0._reinterpret_cast(item_flat_t), ram[index])

            hls.write(res, self.cmdRes)

    def _impl(self) -> None:
        propagateClkRstn(self)
        hls = HlsScope(self)
        ram = BramArrayProxy(hls, MultiPortGroup(self.tableRam.port))
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls, ram)
        hls.addThread(mainThread)
        hls.compile()


if __name__ == "__main__":
    # from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.xilinx.artix7 import Artix7Slow
    from hwtHls.platform.platform import HlsDebugBundle
    u = HashTable()
    print(to_rtl_str(u, target_platform=Artix7Slow(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    from sphinx_hwt.debugUtils import hwt_unit_to_html
    hwt_unit_to_html(u, "tmp/HashTable.scheme.html")
    # import sqlite3
    # import datetime
    # from hwtBuildsystem.vivado.executor import VivadoExecutor
    # from hwtBuildsystem.vivado.part import XilinxPart
    # from hwtBuildsystem.examples.synthetizeUnit import buildUnit,\
    #    store_vivado_report_in_db
    #
    #
    # conn = sqlite3.connect('build_reports.db')
    # c = conn.cursor()
    # logComunication = True
    #
    # start = datetime.datetime.now()
    # with VivadoExecutor(logComunication=logComunication) as executor:
    #    __pb = XilinxPart
    #    part = XilinxPart(
    #            __pb.Family.kintex7,
    #            __pb.Size._160t,
    #            __pb.Package.ffg676,
    #            __pb.Speedgrade._2)
    #    project = buildUnit(executor, u, "tmp/vivado", part,
    #                        target_platform=Artix7Slow(debugDir="tmp/hls", debugFilter=HlsDebugBundle.ALL_RELIABLE),
    #                  synthesize=True,
    #                  implement=False,
    #                  writeBitstream=False,
    #                  # openGui=True,
    #                  )
    #    name = ".".join([u.__class__.__module__, u.__class__.__qualname__])
    #    store_vivado_report_in_db(c, start, project, name)
    #    conn.commit()
