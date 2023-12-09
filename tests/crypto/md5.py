from hwt.code import Concat, rol
from hwt.hdl.types.bits import Bits
from hwt.hdl.types.struct import HStruct
from hwt.math import log2ceil
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.markers import PyBytecodeLLVMLoopUnroll
from hwtLib.types.ctypes import uint32_t


# for i in range(64)
#     SINES_OF_INTEGERS[i] = floor(23**2 * abs(sin(i + 1)))
MD5_SINES_OF_INTEGERS = [uint32_t.from_py(n) for n in [
    0xd76aa478, 0xe8c7b756, 0x242070db, 0xc1bdceee,
    0xf57c0faf, 0x4787c62a, 0xa8304613, 0xfd469501,
    0x698098d8, 0x8b44f7af, 0xffff5bb1, 0x895cd7be,
    0x6b901122, 0xfd987193, 0xa679438e, 0x49b40821,
    0xf61e2562, 0xc040b340, 0x265e5a51, 0xe9b6c7aa,
    0xd62f105d, 0x02441453, 0xd8a1e681, 0xe7d3fbc8,
    0x21e1cde6, 0xc33707d6, 0xf4d50d87, 0x455a14ed,
    0xa9e3e905, 0xfcefa3f8, 0x676f02d9, 0x8d2a4c8a,
    0xfffa3942, 0x8771f681, 0x6d9d6122, 0xfde5380c,
    0xa4beea44, 0x4bdecfa9, 0xf6bb4b60, 0xbebfbc70,
    0x289b7ec6, 0xeaa127fa, 0xd4ef3085, 0x04881d05,
    0xd9d4d039, 0xe6db99e5, 0x1fa27cf8, 0xc4ac5665,
    0xf4292244, 0x432aff97, 0xab9423a7, 0xfc93a039,
    0x655b59c3, 0x8f0ccc92, 0xffeff47d, 0x85845dd1,
    0x6fa87e4f, 0xfe2ce6e0, 0xa3014314, 0x4e0811a1,
    0xf7537e82, 0xbd3af235, 0x2ad7d2bb, 0xeb86d391,
]]

# s specifies the per-round shift amounts
MD5_s = [Bits(5).from_py(n) for n in [
    7, 12, 17, 22, 7, 12, 17, 22, 7, 12, 17, 22, 7, 12, 17, 22,
    5, 9, 14, 20, 5, 9, 14, 20, 5, 9, 14, 20, 5, 9, 14, 20,
    4, 11, 16, 23, 4, 11, 16, 23, 4, 11, 16, 23, 4, 11, 16, 23,
    6, 10, 15, 21, 6, 10, 15, 21, 6, 10, 15, 21, 6, 10, 15, 21,
]]

# init for A, B, C, D variables used in MD6 computation
MD5_INIT = [uint32_t.from_py(n) for n in [0x67452301, 0xefcdab89, 0x98badcfe, 0x10325476]]

md5_accumulator_t = HStruct(
    (Bits(32), "a0"),
    (Bits(32), "b0"),
    (Bits(32), "c0"),
    (Bits(32), "d0"),
    name="md5_accumulator_t"
)


@hlsBytecode
def md5ProcessChunk(chunk: RtlSignal, acc: RtlSignal, unrollFactor=1):
    """
    Based on https://github.com/jcastillo4/systemc-verilog-md5/blob/master/rtl/verilog/md5.v

    The message is padded so that its length is divisible by 512
     * First, a single bit, 1, is appended to the end of the message.
       This is followed by as many zeros as are required to bring the length of the message
       up to 64 bits fewer than a multiple of 512.
       The remaining bits are filled up with 64 bits representing the length
       of the original message, modulo 2**64.
    """

    assert chunk._dtype.bit_length() == 32 * 16
    assert unrollFactor >= 1 and unrollFactor <= 64
    M = [chunk[32 * (i + 1):32 * i] for i in range(16)]
    T = Bits(32)
    MIndex_t = Bits(4)
    A = acc.a0
    B = acc.b0
    C = acc.c0
    D = acc.d0
    i = Bits(log2ceil(64 + 1)).from_py(0)
    # for i in range(64):
    while i != 64:
        F = T.from_py(None)
        g = MIndex_t.from_py(None)
        if i < 16:
            F = (B & C) | (~B & D)
            g = i[4:]
        elif i < 32:
            F = (D & B) | (~D & C)
            g = (i * 5 + 1)[4:]
        elif i < 48:
            F = B ^ C ^ D
            g = (i * 3 + 5)[4:]
        else:
            F = C ^ (B | ~D)
            g = (i * 7)[4:]

        F = F + A + MD5_SINES_OF_INTEGERS[i] + M[g]
        A = D
        D = C
        C = B
        B = B + rol(F, MD5_s[i])
        # del is just used to simplify analysis of loop body
        del g
        del F
        i += 1
        PyBytecodeLLVMLoopUnroll(unrollFactor > 1, unrollFactor)

    # Add this chunk's hash to result so far:
    acc.a0 += A
    acc.b0 += B
    acc.c0 += C
    acc.d0 += D


@hlsBytecode
def md5BuildDigist(acc):
    ":note: output is 128b wide"
    return Concat(acc.a0, acc.b0, acc.c0, acc.d0)
