#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import hashlib
import struct

from hwt.hdl.commonConstants import b1
from hwt.hdl.types.bits import HBits
from hwt.hwIOs.std import HwIODataRdVld
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.pragmaFunction import PyBytecodeSkipPass
from hwtHls.frontend.pyBytecode.pragmaPreproc import PyBytecodeInline
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.platform.xilinx.artix7 import Artix7Medium
from hwtHls.scope import HlsScope
from hwtSimApi.utils import freq_to_period
from tests.crypto.md5 import md5_accumulator_t, md5ProcessChunk, \
    md5BuildDigist, MD5_INIT_DICT


class Md5(HwModule):

    def hwConfig(self):
        self.DATA_WIDTH = HwParam(32 * 16)
        self.FREQ = HwParam(int(100e6))

    def hwDeclr(self):
        addClkRstn(self)
        self.clk.FREQ = self.FREQ
        assert self.DATA_WIDTH > 0, self.DATA_WIDTH

        self.din = HwIODataRdVld()
        self.din.DATA_WIDTH = self.DATA_WIDTH

        self.dout = HwIODataRdVld()._m()
        self.dout.DATA_WIDTH = 4 * 32

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        PyBytecodeSkipPass(["hwtHls::SlicesToIndependentVariablesPass", "hwtHls::BitwidthReductionPass",])
        while b1:
            chunk = hls.read(self.din)
            acc = md5_accumulator_t.from_py(MD5_INIT_DICT)
            PyBytecodeInline(md5ProcessChunk)(chunk, acc)
            hls.write(PyBytecodeInline(md5BuildDigist)(acc), self.dout)

    def hwImpl(self):
        hls = HlsScope(self)
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls)
        hls.addThread(mainThread)
        hls.compile()


class Md5_TC(SimTestCase):

    def _prepareStr(self, inputString:str):
        # Step 1. Add Padding Bits: bit_sequence length mod 512 has to be equal to 448
        # Convert the message to a bit sequence
        message_bytes = inputString.encode()

        # Append '1' as per MD5 padding requirements
        message_bytes += b"\x80"

        # Add '0's needed to pad the message
        while (len(message_bytes) * 8) % 512 != 448:
            message_bytes += b"\x00"

        # Step 2. This class method appends the 64-bit representation of the original message size,
        # in little-endian format (least significant byte first), to the padded bit sequence.
        # Message's size in bits
        original_size = len(inputString) * 8

        # Convert the size to a 64-bit representation in little-endian format
        size_64bits = (original_size).to_bytes(8, byteorder="little", signed=False)
        # Concatenate the 64 bits representing the size to the padded bit sequence
        preprocessed_message = message_bytes + size_64bits

        # After these two preprocessing steps (adding padding bits and appending length),
        # the preprocessed message length will be a multiple of 512 bits.
        return preprocessed_message

    def test_py(self):
        _s = (''.join(f'{i%16:x}' for i in range(64 - 8 - 1)))
        s = _s.encode()  # max amount of bytes in 1st and last chunk repeating digits 0-f
        ref = self._prepareStr(_s)
        paddedS = s + b'\x80' + struct.pack("<Q", len(s) * 8)
        self.assertEqual(ref, paddedS)
        assert len(paddedS) == 64, paddedS

        chunk = HBits(512).from_py(int.from_bytes(paddedS, byteorder="little"))
        acc = md5_accumulator_t.from_py(MD5_INIT_DICT)
        md5ProcessChunk(chunk, acc)
        digits = md5BuildDigist(acc)
        digitsRef = hashlib.md5(s)
        # print(int(digits).to_bytes(16, 'little'))
        # print(digitsRef.digest())
        digitsRefAsInt = int.from_bytes(digitsRef.digest(), byteorder="little")
        # s = bytes(reversed(s))
        self.assertValEqual(digits, digitsRefAsInt)

    def test_noUnroll(self):
        u = Md5()
        # https://github.com/timvandermeij/md5.py/blob/master/md5.py#L43
        self.compileSimAndStart(u, target_platform=Artix7Medium())
        CLK_PERIOD = freq_to_period(u.clk.FREQ)
        _s = ''.join(f'{i%16:x}' for i in range(64 - 8 - 1))
        paddedS = self._prepareStr(_s)  # max amount of bytes in 1st and last chunk repeating digits 0-f
        u.din._ag.data.append(int.from_bytes(paddedS, byteorder="little"))

        self.runSim((64 * 100) * int(CLK_PERIOD))
        h = hashlib.md5(_s.encode())
        hAsInt = int.from_bytes(h.digest(), byteorder="little")

        self.assertValSequenceEqual(u.dout._ag.data, [hAsInt])


if __name__ == "__main__":
    import unittest
    import sys
    sys.setrecursionlimit(int(1e6))
    #from hwt.synth import to_rtl_str
    #from hwtHls.platform.platform import HlsDebugBundle
    #import cProfile
    #pr = cProfile.Profile()
    #pr.enable()
    #u = Md5()
    #try:
    #    print(to_rtl_str(u, target_platform=Artix7Medium(debugFilter=HlsDebugBundle.ALL_RELIABLE))) # 
    #finally:
    #    pr.disable()
    #    pr.dump_stats('profile.prof')
    
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([Md5_TC('test_noUnroll')])
    suite = testLoader.loadTestsFromTestCase(Md5_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)