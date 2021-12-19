from hwt.hdl.constants import WRITE, READ
from hwt.hdl.types.bits import Bits
from hwt.hdl.types.defs import BIT
from hwt.hdl.types.struct import HStruct
from hwt.interfaces.hsStructIntf import HsStructIntf
from hwt.interfaces.utils import addClkRstn
from hwt.math import log2ceil
from hwt.synthesizer.param import Param
from hwt.synthesizer.unit import Unit
from hwtHls.hlsStreamProc.streamProc import HlsStreamProc
from hwtLib.logic.crcComb import CrcComb
from hwtLib.logic.crcPoly import CRC_5_USB
from hwtLib.mem.ram import RamSingleClock
from hwtLib.types.ctypes import uint8_t, uint16_t


class SimpleHashTable(Unit):

    class CMD:
        SWAP = 0
        LOOKUP = 1
        _LAST_CMD = LOOKUP

    def _config(self):
        self.CLK_FREQ = Param(int(100e6))
        self.KEY_T = Param(uint8_t)
        self.VALUE_T = Param(uint16_t)
        self.ITEM_CNT = Param(32)

        self.cmdIn = HsStructIntf()
        self.cmdIn.T = HStruct(
            ("cmd", Bits(log2ceil(self.CMD._LAST_CMD))),
            ("vld", BIT),
            ("key", self.KEY_T),
            ("value", self.VALUE_T),
        )
        self.resOut = HsStructIntf()._m()
        self.resOut.T = HStruct(
            ("found", BIT),
            ("key", self.KEY_T),
            ("value", self.VALUE_T),
        )

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ

    def _impl(self):
        hls = HlsStreamProc(self)
        cmd = hls.read(self.cmdIn)
        keyHash = CrcComb()
        keyHash.setConfig(CRC_5_USB)
        keyHash.REFOUT = False
        keyHash.DATA_WIDTH = self.KEY_T.bit_length()
        ram = RamSingleClock()
        record_t = HStruct(
            ("vld", BIT),
            ("key", self.KEY_T),
            ("value", self.VALUE_T),
        )
        ram.PORT_CNT = (READ, WRITE)
        ram.ADDR_WIDTH = log2ceil(self.ITEM_CNT)
        self.ram = ram
        baramManager = HlsIoBramPort(hls, ram.port)

        resTmp = hls.var("resTmp", self.resOut.T)

        def swap():
            index = hls.read(keyHash.dataOut)
            d = baramManager.read(index)
            yield d
            rec = d._reinterpret_cast(record_t)
            yield resTmp.found(rec.vld)
            yield resTmp.key(rec.key)
            yield resTmp.value(rec.value)

            recordTmp = hls.var("recordTmp", record_t)
            yield recordTmp.vld(cmd.vld)
            yield recordTmp.key(cmd.key)
            yield recordTmp.value(cmd.value)

            yield baramManager.write(index, recordTmp)

        def lookup():
            d = baramManager.read(hls.read(keyHash.dataOut))
            yield d
            rec = d._reinterpret_cast(record_t)
            yield resTmp.found(rec.vld & cmd.key._eq(rec.key))
            yield resTmp.key(rec.key)
            yield resTmp.value(rec.value)

        init_i = hls.var("init_i", Bits(ram.ADDR_WIDTH + 1))
        hls.thread(
            # initial reset
            hls.For(init_i(0), init_i < self.ITEM_CNT, init_i(init_i + 1),
                baramManager.write(init_i, ram.port[1].din._dtype.from_py(0))
            ),
            # main operation
            hls.While(True,
                hls.write(cmd.key, keyHash.dataIn),
                hls.If(cmd._eq(self.CMD.SWAP),
                    *swap(),
                ).Else(
                    *lookup(),
                ),
                hls.write(resTmp, self.resOut)
            )

        )

