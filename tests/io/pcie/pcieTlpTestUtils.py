from hwt.constants import NOT_SPECIFIED
from hwt.hdl.const import HConst
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.structValBase import HStructConstBase
from pyMathBitPrecise.bit_utils import int_to_int_list
from tests.io.pcie.pcieTypes import PcieTlpWord_t, PcieTlpType, PcieTlpMemRequest_t, \
    PcieTlpAddr64_t, PcieTlpAddr32_t, PcieTlpCpl_t, PcieTlpCommonHdrUnpacked_t


def pcieTlpParse_DWs(dataWords: list[int], alteraAlignTo8B:bool=False):
    """
    :param dataWords: list of 4B ints for each word in pcie TLP transaction
    :param alteraAlignTo8B: (qword) pad 3DW headers to 4DW if data address is aligned to 8B,
        used for Altera Stattix V, Arria 10 and alike  
    """

    parsed: list[HConst] = []
    wordIt = iter(dataWords)
    dw = next(wordIt)

    common = PcieTlpWord_t.from_py(dw)._reinterpret_cast(PcieTlpCommonHdrUnpacked_t)
    fmt, typ = int(common.fmt), int(common.typ)
    tlpTy = (fmt, typ)
    # assert tlpTy == PcieTlpType.MWr32, (tlpTy, PcieTlpType.MWr32, hex(dw))
    parsed.append(common)
    if PcieTlpType.hasMemHeader(typ):
        dw = next(wordIt)
        memReq = PcieTlpWord_t.from_py(dw)._reinterpret_cast(PcieTlpMemRequest_t)
        parsed.append(memReq)

    if PcieTlpType.has64bAddr(fmt, typ):
        dw0 = next(wordIt)
        dw1 = next(wordIt)
        addr = HBits(64).from_py((dw1 << 32) | dw0)._reinterpret_cast(PcieTlpAddr64_t)
        parsed.append(addr)

    elif PcieTlpType.has32bAddr(fmt, typ):
        dw = next(wordIt)
        addr = PcieTlpWord_t.from_py(dw)._reinterpret_cast(PcieTlpAddr32_t)
        parsed.append(addr)
        if alteraAlignTo8B and (not int(addr.addr[0]) or not PcieTlpType.hasData(fmt)):
            dw = next(wordIt)
            assert dw == 0, ("expect padding", hex(dw), parsed)

    elif tlpTy == PcieTlpType.Cpl or tlpTy == PcieTlpType.CplD or tlpTy == PcieTlpType.CplDLk:
        dw0 = next(wordIt)
        dw1 = next(wordIt)
        cpl = HBits(64).from_py((dw1 << 32) | dw0)._reinterpret_cast(PcieTlpCpl_t)
        parsed.append(cpl)
        if alteraAlignTo8B and not PcieTlpType.hasData(fmt):
            dw = next(wordIt)
            assert dw == 0, ("expect padding", hex(dw), parsed)

    else:
        raise NotImplementedError(tlpTy)

    if PcieTlpType.hasData(fmt):
        data: list[int] = []
        dataWords = 0
        expectedLen = int(common.fields.length)
        if expectedLen == 0:
            expectedLen = 1024
        for dw in wordIt:
            data.extend(int_to_int_list(dw, 8, 4))
            dataWords += 1
        assert dataWords == expectedLen, (dataWords, expectedLen)
        parsed.append(data)
    else:
        dw = next(wordIt, NOT_SPECIFIED)
        assert dw is NOT_SPECIFIED, ("No data expected", hex(dw), parsed)

    return parsed



class PcieTlpPretty():

    def __init__(self, data: list[HStructConstBase, list[int]]):
        self.data = data

    def __repr__(self):
        valBuff = []
        com = self.data[0]
        length = int(com.fields.length)
        valBuff.append(PcieTlpType.NAMES[(int(com.fmt), int(com.typ))])
        valBuff.append(f"len={length:d}")
        for flag in ("ep", "td", "th"):
            if int(getattr(com.fields, flag)):
                valBuff.append(flag)
        attr = (int(com.fields.attr2) << 2) | int(com.fields.attr0_2)
        if attr:
            valBuff.append(f"attr:{attr:b}")
        for reserved in ("r1", "r2", "r3"):
            assert int(getattr(com.fields, reserved)) == 0, (reserved, com)

        if len(self.data) > 1:
            mem = self.data[1]
            be = int(mem.first_be), int(mem.last_be)
            tag = int(mem.tag)
            req_id = int(mem.req_id)
            valBuff.append(f"req_id=0x{req_id:x}, tag={tag:d}, be=(0x{be[0]:x}, {be[1]:x})")

            addr = self.data[2]
            assert int(addr.ph) == 0, addr.ph
            if addr._dtype == PcieTlpAddr32_t:
                valBuff.append(f"addr=0x{int(addr.addr)<<2:08x}")
            else:
                addr = (int(addr.addr64_32) << 32) | int(addr.addr32_2)
                valBuff.append(f"addr=0x{int(addr.addr)<<2:016x}")
            if len(self.data) > 3:
                data = self.data[3]
                valBuff.append(str(bytes(data)))
                if len(self.data) > 4:
                    raise NotImplementedError()

        return f"<{self.__class__.__name__:s} {', '.join(valBuff):s}>"
