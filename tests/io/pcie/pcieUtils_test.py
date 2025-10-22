import unittest
from tests.io.pcie.pcieTlpTestUtils import PcieTlpPretty, pcieTlpParse_DWs

# UG-01097_avst Transaction Layer Packet (TLP) Header Formats

# read from addr 0

r0 = [
    0x00000001,  # MRd32, len=1
    0x001A080F,
    0xDF8C0000,
    0x0,
]
# read from addr 4
r4 = [
    0x00000001,  # MRd32, len=1
    0x001A080F,
    0xDF8C0004,
    0x0,
]

# write to 0x8
w8 = [
    0x40000001,  # MWr32, len=1
    0x00000B0F,  # first_be=0xf
    0xDF8C0008,  # addr32_2  # :attention: Figure B-10: Memory Write Request, 32-Bit Addressing
    0x0,  # 0xDDCCBBAA, #           #             specifies format as for 64b
    0xAABBCCDD,  # https://forum.xillybus.com/viewtopic.php?t=494
    # 0xE3AFD64B,
]
# write to 0x20
w20 = [
    0x40000001,
    0x0000090F,
    0xDF8C0020,
    0x0,  # 0x11223344,
    0x44332211,
    # 0x0975F1E4,
]
# read from addr 0x24 (8B non-aligned)
r24 = [
    0x00000001,
    0x001A080F,
    0xDF8C0024,
    0x0,
]

# write to addr 0x24 (8B non-aligned)
w24 = [
    0x40000001,
    0x00000A0F,
    0xDF8C0024,
    0x88776655,
]


class PcieUtils_TC(unittest.TestCase):

    def test_PcieTlpPretty_pcieTlpParse_DWs_RW(self):
        pkts = (
            ("r0", r0),
            ("r4", r4),
            ("w8", w8),
            ("w20", w20),
            ("r24", r24),
            ("w24", w24)
        )
        expectedPktRepr = [
            "<PcieTlpPretty MRd32, len=1, req_id=0x1a, tag=8, be=(0xf, 0), addr=0xdf8c0000>",
            "<PcieTlpPretty MRd32, len=1, req_id=0x1a, tag=8, be=(0xf, 0), addr=0xdf8c0004>",
            "<PcieTlpPretty MWr32, len=1, req_id=0x0, tag=11, be=(0xf, 0), addr=0xdf8c0008, b'\\xdd\\xcc\\xbb\\xaa'>",
            "<PcieTlpPretty MWr32, len=1, req_id=0x0, tag=9, be=(0xf, 0), addr=0xdf8c0020, b'\\x11\"3D'>",
            "<PcieTlpPretty MRd32, len=1, req_id=0x1a, tag=8, be=(0xf, 0), addr=0xdf8c0024>",
            "<PcieTlpPretty MWr32, len=1, req_id=0x0, tag=10, be=(0xf, 0), addr=0xdf8c0024, b'Ufw\\x88'>",
        ]
        for (name, pktRaw), expectedRepr in zip(pkts, expectedPktRepr):
            # print(name)
            p = PcieTlpPretty(pcieTlpParse_DWs(pktRaw, alignTo8B=True))
            self.assertEqual(repr(p), expectedRepr, name)

    # def test_MRd32(self):


if __name__ == "__main__":
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([PcieUtils_TC("test_ExampleFlushing0_allEn")])
    suite = testLoader.loadTestsFromTestCase(PcieUtils_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
