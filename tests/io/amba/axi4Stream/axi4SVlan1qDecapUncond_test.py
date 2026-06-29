from math import ceil

from hwt.hdl.types.bits import HBits
from hwt.simulator.simTestCase import SimTestCase
from hwtLib.amba.axi4sSimFrameUtils import Axi4StreamSimFrameUtils
from hwtLib.types.net.ethernet import Eth802_1qHeader_t, ETHER_TYPE, \
    Eth2Header_t
from pyMathBitPrecise.bit_utils import int_to_int_list
from tests.io.amba.axi4Stream.axi4SVlan1qDecapUncond import Axi4SVlan1qDecapUncond
from tests.passTestInjectorForStreamHwModule import PassTestInjectorForStreamHwModule


class Axi4SVlan1qDecapUncondTC(SimTestCase):
    StreamSimFrameUtils = Axi4StreamSimFrameUtils
    def _test_decap(self, DATA_WIDTH: int):
        dut = Axi4SVlan1qDecapUncond()
        dut.DATA_WIDTH = DATA_WIDTH
        dut.CLK_FREQ = int(1e6)

        testCases = [
            (
                0x010203040506,  # dst_mac
                0x112233445566,  # src_mac
                (DATA_WIDTH // 8) * 1,  # payload size
            ),
            (
                0x111213141516,
                0x222334455667,
                (DATA_WIDTH // 8) * 2,
            ),
            (
                0x212223242526,
                0x333445566778,
                (DATA_WIDTH // 8) * 3,
            ),

        ]

        tci = 0x5678
        # Expected decap'd Ethernet frames (without VLAN tag)
        refOutFrames: list[list[int]] = []
        ethHeaderSize = ceil(Eth2Header_t.bit_length() / 8)
        eth1qHeaderSize = ceil(Eth802_1qHeader_t.bit_length() / 8)
        inFrames: list[list[int]] = []
        for dstMac, srcMac, payloadSize in testCases:
            # Create 802.1Q frame

            pkt = Eth802_1qHeader_t.from_py({
                "dst": dstMac,
                "src": srcMac,
                "tag": {
                    "tpid": ETHER_TYPE.VLAN_1Q,
                    "tci": tci,
                },
                "type": ETHER_TYPE.IPv4,
            })

            # Convert packet to bytes
            pktAsBytes = pkt._reinterpret_cast(HBits(8 * eth1qHeaderSize))
            pktAsBytes_int = pktAsBytes.val & pktAsBytes.vld_mask

            payload = [i % 256 for i in range(payloadSize)]
            data = int_to_int_list(pktAsBytes_int, 8, eth1qHeaderSize) + payload
            inFrames.append(data)

            expectedPkt = Eth2Header_t.from_py({
                "dst": dstMac,
                "src": srcMac,
                "type": ETHER_TYPE.IPv4,
            })
            data = expectedPkt._reinterpret_cast(HBits(8 * ethHeaderSize))
            refOutFrames.append(list(int_to_int_list(
                data.val & data.vld_mask, 8, ethHeaderSize)) + payload)

        passTests = PassTestInjectorForStreamHwModule(dut, self, self.StreamSimFrameUtils)
        passTests.bindDataByInOut((inFrames,), (refOutFrames,),)
        passTests.setTimeLimits(wallTimeRtlDefaultMultiplier=2.1)
        passTests.test_allInOne(
                platformKwArgs=dict(
                    # debugFilter={
                    #    *HlsDebugBundle.ALL_RELIABLE,
                    #    HlsDebugBundle.DBG_4_0_addSignalNamesToSync,
                    #    HlsDebugBundle.DBG_4_0_addSignalNamesToData,
                    # },
                    # llvmCliArgs=[
                    #   # LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,
                    #   # LLVM_CLI_COMMON_OPTS.PRINT_BEFORE_ALL,
                    #   # LLVM_CLI_COMMON_OPTS.PRINT_AFTER_ALL
                    # ],
                    # runTestAfterEachPass=True,
                    # runTestAfterEachIrPass=True,
                    # runTestAfterEachMirPass=True,
                )
            )


    def test_8b(self):
        self._test_decap(8)

    def test_16b(self):
        self._test_decap(16)

    def test_64b(self):
        self._test_decap(64)

    def test_512b(self):
        self._test_decap(512)


if __name__ == '__main__':
    import unittest

    testLoader = unittest.TestLoader()
    suite = testLoader.loadTestsFromTestCase(Axi4SVlan1qDecapUncondTC)
    # suite = unittest.TestSuite([Axi4SVlan1qDecapUncondTC("test_64b")])
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
