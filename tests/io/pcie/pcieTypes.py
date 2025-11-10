from typing import Union

from hwt.hdl.types.bitConstFunctions import AnyHBitsValue
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.defs import BIT
from hwt.hdl.types.struct import HStruct
from pyMathBitPrecise.bit_utils import get_bit


# [0] PCI Express Base Specification Revision 3.0 November 10, 2010
# https://picture.iczhiku.com/resource/eetop/wHiSRjtztkeJLnVc.pdf
# PCI Express System Architecture ISBN: 9780321156303
# TLP Packet Formats without Data Payload https://www.intel.com/content/www/us/en/docs/programmable/683647/18-0/tlp-packet-formats-without-data-payload.html
# https://www.fpga4fun.com/PCI-Express4.html
# https://pcisig.com/specifications
# Table 2-2
class PcieTlpFmt:
    DW3_NO_DATA = 0b000
    DW4_NO_DATA = 0b001
    DW3_DATA = 0b010
    DW4_DATA = 0b011
    TLP_PREFIX = 0b100


# Table 2-3: Fmt[2:0] and Type[4:0] Field Encodings
class PcieTlpTypeVal():
    M = 0b00000  # Memory Read/Write  Request
    MLk = 0b00001  # Memory Read Request Locked
    IO = 0b00010  # I/O Read/Write Request
    Cfg0 = 0b00100  # Configuration Read/Write Type 0
    Cfg1 = 0b00101  # Configuration Read/Write Type 1
    Cpl = 0b01010  # Completion without/without Data
    CplLk = 0b01011  # Completion for Locked Memory Read
    FetchAdd = 0b01100
    Swap = 0b01101
    CAS = 0b01110  # Compare and Swap AtomicOp Request (swap if equal)

    @staticmethod
    def isLPrfx(typeVal: Union[int, AnyHBitsValue]):
        # Local TLP Prefix – The sub-field L[4:0] specifies the Local TLP Prefix type
        if isinstance(int):
            return not get_bit(typeVal, 4)
        else:
            return ~typeVal[4]

    @staticmethod
    def isEPrfx(typeVal: Union[int, AnyHBitsValue]):
        # End-End TLP Prefix – The sub-field typeVal[4:0] specifies the End-End TLP Prefix type
        if isinstance(int):
            return not get_bit(typeVal, 4)
        else:
            return ~typeVal[4]


# Table 2-3: Fmt[2:0] and Type[4:0] Field Encodings
class PcieTlpType:
    MRd32 = (PcieTlpFmt.DW3_NO_DATA, PcieTlpTypeVal.M)  # Memory Read Request
    MRd64 = (PcieTlpFmt.DW4_NO_DATA, PcieTlpTypeVal.M)
    MRdLk32 = (PcieTlpFmt.DW3_NO_DATA, PcieTlpTypeVal.MLk)  # Memory Read Request-Locked
    MRdLk64 = (PcieTlpFmt.DW4_NO_DATA, PcieTlpTypeVal.MLk)

    MWr32 = (PcieTlpFmt.DW3_DATA, PcieTlpTypeVal.M)  # Memory Write Request
    MWr64 = (PcieTlpFmt.DW4_DATA, PcieTlpTypeVal.M)

    # :note: all IO/Cfg are non-posted
    IORd = (PcieTlpFmt.DW3_NO_DATA, PcieTlpTypeVal.IO)  # I/O Read Request
    IOWr = (PcieTlpFmt.DW3_DATA, PcieTlpTypeVal.IO)  # I/O Write Request
    # :note: Cfg are ID-routed
    CfgRd0 = (PcieTlpFmt.DW3_NO_DATA, PcieTlpTypeVal.Cfg0)  # Configuration Read Type 0
    CfgWr0 = (PcieTlpFmt.DW3_DATA, PcieTlpTypeVal.Cfg0)  # Configuration Write Type 0
    CfgRd1 = (PcieTlpFmt.DW3_NO_DATA, PcieTlpTypeVal.Cfg1)  # Configuration Read Type 1
    CfgWr1 = (PcieTlpFmt.DW3_DATA, PcieTlpTypeVal.Cfg1)  # Configuration Write Type 1
    # Type=0b10 r2 r1 r0, Message Request – The sub-field r[2:0]
    # specifies the Message routing mechanism, handled as memory, posted
    # id/address/implicit routed
    Msg = (PcieTlpFmt.DW4_NO_DATA, None)
    MsgD = (PcieTlpFmt.DW4_DATA, None)  #  Type= 0b10, r2 r1 r0, Message Request with data payload
    # Completion without Data - Used for I/O and
    # Configuration Write Completions with any
    # Completion Status. Also used for AtomicOp
    # Completions and Read Completions (I/O,
    # Configuration, or Memory) with Completion
    # Status other than Successful Completion.
    Cpl = (PcieTlpFmt.DW3_NO_DATA, PcieTlpTypeVal.Cpl)
    # Completion with Data, Used for Memory,
    # I/O, and Configuration Read Completions.
    # Also used for AtomicOp Completions.
    # CplLk = (PcieTlpFmt.DW3_NO_DATA, 0 1011 Completion for Locked Memory Read
    # without Data - Used only in error case.
    CplD = (PcieTlpFmt.DW3_DATA, PcieTlpTypeVal.Cpl)
    # Completion for Locked Memory Read - otherwise like CplD.
    CplDLk = (PcieTlpFmt.DW3_DATA, PcieTlpTypeVal.CplLk)

    FetchAdd32 = (PcieTlpFmt.DW3_DATA, PcieTlpTypeVal.FetchAdd)  # Fetch and Add AtomicOp Request
    FetchAdd64 = (PcieTlpFmt.DW4_DATA, PcieTlpTypeVal.FetchAdd)
    Swap32 = (PcieTlpFmt.DW3_DATA, PcieTlpTypeVal.Swap)  # Unconditional Swap AtomicOp Request
    Swap64 = (PcieTlpFmt.DW4_DATA, PcieTlpTypeVal.Swap)
    CAS32 = (PcieTlpFmt.DW3_DATA, PcieTlpTypeVal.CAS)  # Compare and Swap AtomicOp Request
    CAS64 = (PcieTlpFmt.DW4_DATA, PcieTlpTypeVal.CAS)

    NAMES = {
        MRd32: "MRd32",
        MRd64: "MRd64",
        MRdLk32: "MRdLk32",
        MRdLk64: "MRdLk64",
        MWr32: "MWr32",
        MWr64: "MWr64",
        IORd: "IORd",
        IOWr: "IOWr",
        CfgRd0: "CfgRd0",
        CfgWr0: "CfgWr0",
        CfgRd1: "CfgRd1",
        CfgWr1: "CfgWr1",
        Msg: "Msg",
        MsgD: "MsgD",
        Cpl: "Cpl",
        CplD: "CplD",
        CplDLk: "CplDLk",
        FetchAdd32: "FetchAdd32",
        FetchAdd64: "FetchAdd64",
        Swap32: "Swap32",
        Swap64: "Swap64",
        CAS32: "CAS32",
        CAS64: "CAS64",
    }

    @staticmethod
    def hasMemHeader(typ: int):
        return typ in (
            PcieTlpTypeVal.M,
            PcieTlpTypeVal.MLk,
            PcieTlpTypeVal.FetchAdd,
            PcieTlpTypeVal.Swap,
            PcieTlpTypeVal.CAS
        )

    @classmethod
    def has32bAddr(cls, fmt: int, typ: int):
        return (fmt, typ) in (
            cls.MRd32,
            cls.MRdLk32,
            cls.MWr32,
            cls.FetchAdd32,
            cls.Swap32,
            cls.CAS32
        )

    @classmethod
    def has64bAddr(cls, fmt: int, typ: int):
        return (fmt, typ) in (
            cls.MRd64,
            cls.MRdLk64,
            cls.MWr64,
            cls.FetchAdd64,
            cls.Swap64,
            cls.CAS64
        )

    @staticmethod
    def hasData(fmt: int):
        return fmt in (PcieTlpFmt.DW3_DATA, PcieTlpFmt.DW4_DATA)

"""

:attenton:
    Structures defined in this module have native byte order with 
    byte0 at st_data[8:0], byte1 at st_data[16:8] etc.
    PCIe spec however pack fields in words in big endian maner.
    The word has 4B (PcieWord_t) and the byte 0 is at data[32:24].
    
    For example 64b data is divided into Concat(header1, header0)
    If the segment is a header header0=Concat(byte0, byte1, byte2, byte3).
    But if the segment represents data it is formated as data0=(byte3, byte2, byte1, byte0).
    :see: [0] Figure 2-3: Generic TLP Format
    :see: UG-01097_avst 7-22 Data Alignment and Timing
    :see: pg054-7series-pcie TLP Format in the AXI4-Stream Interface
    :note: values itself are litlendian
    
:note: from https://xillybus.com/tutorials/pci-express-tlp-pcie-primer-tutorial-guide-1
    MWr32 fmt=2,length=1, first_be=0xf, addr=0x3f6bfc10, data=0x12345678 and all other fields set to 0
    is send on bus as 0x40000001, 0x0000000f, 0xfdaff040 (=addr<<2), 0x12345678 (=data).
"""
PcieTlpWord_t = HBits(32)
# https://indico.cern.ch/event/121654/attachments/68430/98164/Practical_introduction_to_PCI_Express_with_FPGAs_-_Extended.pdf
# Figure 2-4: Fields Present in All TLPs
PcieTlpCommonHdr_t = HStruct(
    # pcie Byte 1-3
    (HBits(3 * 8), "fields"),  # specific to each fmt/typ variant, :see: PcieTlpCommonHdrFields_t
    # pcie Byte 0
    (HBits(3), "fmt"),  # format
    (HBits(5), "typ"),
    name="PcieCommonHdr_t"
)

# :note: PCIe length is in DW units, 1=1DW, 2=2DW, 0=1024DW, Table 2-4: Length[9:0] Field Encoding
# pcie byte 2 (w/o length9_8)
PcieTlpLength_t = HBits(10)
PcieTlpLengthDecoded_t = HBits(PcieTlpLength_t.bit_length() + 1)
PcieTlpByteLengthDecoded_t = HBits(PcieTlpLength_t.bit_length() + 1 + 2) # :note: max 4096B

# Figure 2-5: Fields Present in All TLP Headers
PcieTlpCommonHdrFields_t = HStruct(
    # pcie byte 3 + byte 2 [2:0]
    (PcieTlpLength_t, "length"), # 1== 1DW word, 0 == max DWs (1024)
    (HBits(2), "at"),  # :see: PcieAddressType
    (HBits(2), "attr0_2"),  # ([1]=relaxedOrdering, [0]=no Snoop) # Table 2-10: Ordering Attributes
    (BIT, "ep"),  # indicates the TLP is poisoned
    (BIT, "td"),  # TLP digest – ECRC field
    # pcie byte 1
    (BIT, "th"),  # indicates the presence of TLP Processing Hints
    (BIT, "r1"),
    (BIT, "attr2"),  # ID-based ordring
    (BIT, "r2"),
    (HBits(3), "tc"),  # Traffic class
    (BIT, "r3"),
    name="PcieTlpCommonHdrFields_t"
)
PcieTlpCommonHdrUnpacked_t = HStruct(
    # pcie byte 1-3
    (PcieTlpCommonHdrFields_t, "fields"),
    # pcie byte 0
    (HBits(5), "typ"),
    (HBits(3), "fmt"),  # format
    name="PcieTlpCommonHdrUnpacked_t"
)


# PcieCommonHdrCommonFields.attr1downto0
class PcieAttr_ordering:
    DEFAULT = 0b00  # PCI Strongly Ordered Model
    RELAXED = 0b01  # PCI-X Relaxed Ordering Model
    ID_BASED = 0b10  # independent ordering based on Requester/Completer ID
    RELAXED_PLUS_ID_BASED = 0b11  # Logical ”OR” of Relaxed Ordering and IDO


class PcieAddressType():
    UNTRANSLATED = 0b00  # default
    TRANSLATION_REQUEST = 0b01
    TRANSLATED = 0b10


PcieTlpTag_t = HBits(8)

# :note: Address/Length combination which causes a Memory Space access to cross a 4-KB boundary
# Figure 2-15: Request Header Format for 64-bit Addressing of Memory (without address part)
PcieTlpMemRequest_t = HStruct(
  # pcie byte 7
  (HBits(4), "first_be"),  # first DW byte enable, for full 1DW = 0b1111
  (HBits(4), "last_be"),  # last DW byte enable, for full 1DW = 0b0000
  # pcie byte 6
  (PcieTlpTag_t, "tag"),
  # pcie byte 4, 5
  (HBits(16), "req_id"),
  name="MemRequest_t"
)
# :attention: Altera has additional 4B padding https://www.intel.com/content/www/us/en/docs/programmable/683647/18-0/tlp-packet-formats-without-data-payload.html

# :note: all <4G transactions must be in 32b format
PcieTlpAddr32_t = HStruct(
 #  pcie byte 11 - 8
 (HBits(2), "ph"),
 (HBits(30), "addr"),
 name="PcieTlpAddr32_t"
)

PcieTlpAddr64_t = HStruct(
  # pcie byte 11 - 8
  (HBits(32), "addr64_32"),
  # pcie byte 15 - 12
  (HBits(2), "ph"),
  (HBits(30), "addr32_2"),
  name="PcieTlpAddr64_t"
)

# MRd32_t = MemRequest32_t
# MWr32_t = MemRequest32_t followed by proper number of data words

# [0] Non-ARI # Table 2-7: Header Field Locations for non-ARI ID Routing
PcieTlpRequestorId_t = HStruct(
    (HBits(3), "function"),
    (HBits(5), "device"),
    (HBits(8), "bus"),
    name="PcieTlpRequestorId_t"
)
# [0] Table 2-8: Header Field Locations for ARI ID Routing
PcieTlpRequestorAriId_t = HStruct(
    (HBits(8), "function"),
    (HBits(8), "bus"),
    name="PcieTlpRequestorAriId_t"
)


# [0] Table 2-29: Completion Status Field Values
class PcieTlpCompletitionStatus:
    SC = 0b000  # Successful Completion
    UR = 0b001  # Unsupported Request
    CRS = 0b010  # Configuration Request Retry Status
    CA = 0b100  # Completer Abor


# [0] Figure 2-28: Completion Header Format
# previous header: PcieTlpCommonHdrUnpacked_t
# :note: packets with the same tag are ordered
PcieTlpCpl_t = HStruct(
  # pcie byte 6, 7
  (HBits(12), "byte_count"), # (total data bytes - data bytes in all previous Cpls)
  # pcie byte 6
  (BIT, "bcm"),  # Byte Count Modified, this bit must not set by PCIe Completers, PCI-X only
  (HBits(3), "compl_status"),  # :see: PcieTlpCompletitionStatus
  # pcie byte 4, 5
  (HBits(16), "compl_id"),  # :see: RequestorId_t/RequestorAriId_t
  # pcie byte 11
  (HBits(7), "lo_addr"),  # [0] 2.2.9. Completion Rules,
                          # byte address for the first enabled byte of data returned with the Completion
                          # [0] 2.3.1.1. Data Return for Read Requests
                          # 1st Cpl it is computed from lower bits of address, for all subsequent it is 0
                          # (start of the second completition is always aligned to RCB (Read Completion Boundary))
                          # [0] Table 2-33: Calculating Lower Address from 1st DW BE
                          # lo_addr[7:2]=addr[5:], lo_addr[2:0] = ctlz(first_be)
  (BIT, "r"),
  # pcie byte 10
  (HBits(8), "tag"),
  # pcie byte 8, 9
  (HBits(16), "req_id"),  # :see: RequestorId_t/RequestorAriId_t
  name="PcieTlpCpl_t",
)
# :attention: Altera has additional 4B padding https://www.intel.com/content/www/us/en/docs/programmable/683647/18-0/tlp-packet-formats-without-data-payload.html
# Cpl_t may be followed by data to form CplD_t

# IO Figure 2-17: Request Header Format for I/O Transactions
# Cfg Figure 2-18: Request Header Format for Configuration Transactions
