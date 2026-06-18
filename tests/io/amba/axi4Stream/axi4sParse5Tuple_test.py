#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.defs import BIT
from hwt.hdl.types.struct import HStruct
from hwt.hdl.types.structValBase import HStructConstBase
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.platform.debugBundle import HlsDebugBundle, LLVM_CLI_COMMON_OPTS
from hwtLib.amba.axi4sSimFrameUtils import Axi4StreamSimFrameUtils
from hwtLib.types.ctypes import uint8_t
from hwtLib.types.net.ethernet import Eth2Header_t, ETHER_TYPE, eth_mac_t
from hwtLib.types.net.ip import IPv4Header_t, IPv6Header_t, IP_PROTOCOL, \
    IPv6ExtCommonHeader_t, l4port_t, ipv6_t
from hwtLib.types.net.tcp import TCP_header_t
from hwtLib.types.net.udp import UDP_header_t
from tests.io.amba.axi4Stream.axi4sParse5Tuple import Axi4SParse5Tuple
from tests.passTestInjectorForDInDOutHwModule import PassTestInjectorForDInDOutHwModule
from tests.passTestIoStream import PassTestIoInStream
from tests.passTestIoStruct import PassTestIoOutStruct


class Axi4SParse5Tuple_TC(SimTestCase):
    ipv4tcp_t = HStruct(
        (Eth2Header_t, "eth"),
        (IPv4Header_t, "ip"),
        (TCP_header_t, "tcp")
    )
    ipv4udp_t = HStruct(
        (Eth2Header_t, "eth"),
        (IPv4Header_t, "ip"),
        (UDP_header_t, "udp")
    )
    ipv6tcp_t = HStruct(
        (Eth2Header_t, "eth"),
        (IPv6Header_t, "ip"),
        (TCP_header_t, "tcp")
    )
    ipv6udp_t = HStruct(
        (Eth2Header_t, "eth"),
        (IPv6Header_t, "ip"),
        (UDP_header_t, "udp")
    )
    ipv6ext1udp_t = HStruct(
        (Eth2Header_t, "eth"),
        (IPv6Header_t, "ip"),
        (IPv6ExtCommonHeader_t, "ext0"),
        (UDP_header_t, "udp")
    )
    ipv6ext2udp_t = HStruct(
        (Eth2Header_t, "eth"),
        (IPv6Header_t, "ip"),
        (IPv6ExtCommonHeader_t, "ext0"),
        (IPv6ExtCommonHeader_t, "ext1"),
        (UDP_header_t, "udp")
    )
    StreamSimFrameUtils = Axi4StreamSimFrameUtils

    def _test(self, inputs: list[HStructConstBase], DATA_WIDTH:int, CLK_FREQ=int(1e6)):
        dut = Axi4SParse5Tuple()
        dut.DATA_WIDTH = DATA_WIDTH
        dut.CLK_FREQ = CLK_FREQ
        b8 = HBits(8)
        rxFramesIn: list[list[int]] = []
        rxUseMask = dut.USE_KEEP or dut.USE_STRB
        refFrames: list[HStructConstBase] = []
        resT = HStruct(
            (uint8_t, "proto"),
            (BIT, "isIPv6"),
            (ipv6_t, "src"),
            (ipv6_t, "dst"),
            (l4port_t, "srcp"),
            (l4port_t, "dstp"),
        )
        for inp in inputs:
            inpWidth = inp._dtype.bit_length()
            arrTy = b8[inpWidth // 8]
            inpAsArr = [int(d) for d in inp._reinterpret_cast(arrTy)]
            if rxUseMask:
                pass
            else:
                # must extend to full words otherwise agent will raise error because last word will contain non valid
                # data and the packet will not end exactly at the end of the word thus EoF will not be correct
                inpWordCnt = inpWidth // DATA_WIDTH
                if inpWordCnt * DATA_WIDTH < inpWidth:
                    inpWordCnt += 1
                assert inpWordCnt * DATA_WIDTH >= inpWidth
                paddingByteCnt = (inpWordCnt * DATA_WIDTH - inpWidth) // 8
                for _ in range(paddingByteCnt):
                    # add padding bytes
                    inpAsArr.append(None)

            rxFramesIn.append(inpAsArr)
            isIPv4 = int(inp.eth.type) == ETHER_TYPE.IPv4
            proto = int(inp.ip.protocol if isIPv4 else inp.ip.nextHeader)
            if proto == IP_PROTOCOL.IPv6_opts:
                proto = int(inp.ext0.nextHeader)
                if proto == IP_PROTOCOL.IPv6_opts:
                    proto = int(inp.ext1.nextHeader)

            isUdp = proto == IP_PROTOCOL.UDP
            if not isUdp:
                assert int(proto) == IP_PROTOCOL.TCP, (proto, inp)
            ref = tuple(int(d) for d in resT.from_py(dict(
                proto=proto,
                isIPv6=int(inp.eth.type) == ETHER_TYPE.IPv6,
                src=inp.ip.src._zext(128),
                dst=inp.ip.dst._zext(128),
                srcp=inp.udp.srcp if isUdp else inp.tcp.srcp,
                dstp=inp.udp.dstp if isUdp else inp.tcp.dstp,
            )))
            refFrames.append(ref)

        passTests = PassTestInjectorForDInDOutHwModule(dut, self)
        passTests.bindDataByInOut((PassTestIoInStream(self.StreamSimFrameUtils, rxFramesIn),),
                                  (PassTestIoOutStruct(resT, refFrames),),
                                  PORT_NAMES=('rx', 'tx'))
        passTests.setTimeLimits(wallTimeRtlDefaultMultiplier=2.1)
        passTests.test_allInOne(
            platformKwArgs=dict(
              # debugFilter=HlsDebugBundle.ALL_RELIABLE,
              # llvmCliArgs=[LLVM_CLI_COMMON_OPTS.PRINT_CHANGED],
              # runTestAfterEachPass=True,
              # runTestAfterEachMirPass=True,
            ),
            )

    def _getRandEth(self, type_: ETHER_TYPE):
        rand = self._rand
        return {
            "src": rand.getrandbits(eth_mac_t.bit_length()),
            "dst": rand.getrandbits(eth_mac_t.bit_length()),
            "type": type_
        }

    def _getRandIPv4(self, protocol: IP_PROTOCOL):
        rand = self._rand
        return {
            f.name: (rand.getrandbits(f.dtype.bit_length())
                        if f.name != "protocol"
                        else protocol)
            for f in IPv4Header_t.fields
        }

    def _getRandIPv6(self, nextHeader: IP_PROTOCOL):
        rand = self._rand
        return {
            f.name: (rand.getrandbits(f.dtype.bit_length())
                        if f.name != "nextHeader"
                        else nextHeader)
            for f in IPv6Header_t.fields
        }

    def _getRandStruct(self, struct: HStruct):
        rand = self._rand
        return {f.name: rand.getrandbits(f.dtype.bit_length())
                for f in struct.fields}

    def _getRandIPv6Ext(self, nextHeader: IP_PROTOCOL, headerExtensionLen=0):
        rand = self._rand
        if headerExtensionLen != 0:
            raise NotImplementedError()
        return IPv6ExtCommonHeader_t.from_py({
            "nextHeader": nextHeader,
            "headerExtensionLen": headerExtensionLen,
            "data": rand.getrandbits(16 + 32),
        })

    def _getRandPacket(self):
        T = self._rand.choice([
            self.ipv4tcp_t,
            self.ipv4udp_t,
            self.ipv6tcp_t,
            self.ipv6udp_t,
            self.ipv6ext1udp_t,
            self.ipv6ext2udp_t,
        ])
        isIPv4 = T.fields[1].dtype == IPv4Header_t
        isUdp = T.fields[-1].dtype == UDP_header_t

        d = {
          "eth": self._getRandEth(ETHER_TYPE.IPv4 if isIPv4 else ETHER_TYPE.IPv6)
        }
        protocol = IP_PROTOCOL.UDP if isUdp else IP_PROTOCOL.TCP
        if isIPv4:
            d["ip"] = self._getRandIPv4(protocol)
        else:
            extCnt = len(T.fields) - 3
            d["ip"] = self._getRandIPv6(protocol if extCnt == 0 else IP_PROTOCOL.IPv6_opts)
            extNames = ("ext0", "ext1")
            if extCnt > 2:
                raise NotImplementedError()
            for isLast, (_, hName) in iter_with_last(zip(range(extCnt), extNames)):
                d[hName] = self._getRandIPv6Ext(protocol if isLast else IP_PROTOCOL.IPv6_opts)
        if isUdp:
            d["udp"] = self._getRandStruct(UDP_header_t)
        else:
            d["tcp"] = self._getRandStruct(TCP_header_t)
        return T.from_py(d)

    def test_ipv4tcp_t_2048b(self, DATA_WIDTH=2048, N: int=5):
        inp = [
            self.ipv4tcp_t.from_py({
                "eth": self._getRandEth(ETHER_TYPE.IPv4),
                "ip": self._getRandIPv4(IP_PROTOCOL.TCP),
                "tcp": self._getRandStruct(TCP_header_t),
            }) for _ in range(N)
        ]
        self._test(inp, DATA_WIDTH)

    def test_ipv4tcp_t_128b(self, DATA_WIDTH=128, N: int=5):
        self.test_ipv4tcp_t_2048b(DATA_WIDTH=DATA_WIDTH, N=N)

    def test_ipv4tcp_t_96b(self, DATA_WIDTH=96, N: int=5):
        self.test_ipv4tcp_t_2048b(DATA_WIDTH=DATA_WIDTH, N=N)

    def test_rand_t_2048b(self, DATA_WIDTH=2048, N: int=16):
        inp = [
            self._getRandPacket() for _ in range(N)
        ]
        self._test(inp, DATA_WIDTH)

    def test_rand_t_128b(self, DATA_WIDTH=128, N: int=16):
        self.test_rand_t_2048b(DATA_WIDTH, N)

    def test_rand_t_96b(self, DATA_WIDTH=128, N: int=16):
        self.test_rand_t_2048b(DATA_WIDTH, N)


if __name__ == "__main__":
    import unittest

    testLoader = unittest.TestLoader()
    suite = testLoader.loadTestsFromTestCase(Axi4SParse5Tuple_TC)
    # suite = unittest.TestSuite([Axi4SParse5Tuple_TC("test_ipv4tcp_t_2048b")])
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
