from collections import deque
from typing import Optional, Sequence, Union

from hwt.code import Concat
from hwt.constants import NOT_SPECIFIED
from hwt.hdl.commonConstants import b1
from hwt.hdl.const import HConst
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.hdl.types.hdlType import HdlType
from hwtHls.ssa.analysis.llvmIrInterpretUtils import SimIoUnderflowErr
from hwtLib.abstract.simFrameUtils import SimFrameUtils
from pyMathBitPrecise.bit_utils import mask
from tests.utils.testQueue import TestRead


class TestQueueInStream(deque[deque[Union[int, HBitsConst]]]):
    """
    :note: frame data are deques of bytes in int or HBitsConst format
        the byte width is specified in frameUtils
    
    """

    def __init__(self, frameUtils: SimFrameUtils):
        self._frameUtils = frameUtils
        self._BYTE_WIDTH = frameUtils.BYTE_WIDTH
        self._consumedBitsFromLastByte = 0
        self._currentFrame: Optional[deque[Union[int, HBitsConst]]] = None
        self._BYTE_BIT_MASK = mask(self._BYTE_WIDTH)

    def appendFrame(self, frameBytes: Sequence[Union[int, HBitsConst]]):
        self.append(deque(frameBytes))

    def read(self, t: HdlType):
        w = 0
        val = 0
        val_vld = 0
        reqW = t.bit_length()
        BYTE_WIDTH = self._BYTE_WIDTH
        BYTE_BIT_MASK = self._BYTE_BIT_MASK
        while w < reqW:
            consumedBitsFromLastByte = self._consumedBitsFromLastByte
            toConsumme = reqW - w
            if toConsumme >= BYTE_WIDTH - consumedBitsFromLastByte:
                # consume complete byte or leftover
                byte = self._currentFrame.popleft()
            else:
                # only peek on current last byte
                byte = self._currentFrame[0]

            if isinstance(byte, int):
                byte_v = byte
                byte_vld = BYTE_BIT_MASK
            else:
                byte_v = byte.val
                byte_vld = byte.vld_mask

            if w == 0 and consumedBitsFromLastByte != 0:
                # cut off lsb bits which were already consumed
                byte_v >>= consumedBitsFromLastByte
                byte_vld >>= consumedBitsFromLastByte
                w = BYTE_WIDTH - consumedBitsFromLastByte
                if w > reqW:
                    self._consumedBitsFromLastByte += reqW
                    w = reqW
                else:
                    self._consumedBitsFromLastByte = 0

                m = mask(w)
                val = byte_v & m
                val_vld = byte_vld & m
            else:
                # append to msb bytes of the val
                byte_v = (byte_v << w)
                byte_vld = (byte_vld << w)
                toConsumme = reqW - w
                if toConsumme < BYTE_WIDTH:
                    m = mask(toConsumme)
                    byte_v &= m
                    byte_vld &= m
                    self._consumedBitsFromLastByte = toConsumme
                    w += toConsumme
                else:
                    w += BYTE_WIDTH
                val |= byte_v
                val_vld |= byte_vld

        data = HBits(w).from_py(val, val_vld)._reinterpret_cast(t)
        return TestRead(data, b1)

    def readStartOfFrame(self):
        assert self._currentFrame is None, ("Read of previous frame did not end yet")
        if not self:
            return SimIoUnderflowErr(self)
        self._currentFrame = self.pop()
        self._consumedBitsFromLastByte = 0

    def readEndOfFrame(self):
        assert self._currentFrame is not None and not self._currentFrame, (
            "All data must be consumed", self._currentFrame)
        self._currentFrame = None
        self._consumedBitsFromLastByte = 0


class TestQueueOutStream(deque[list[Union[int, HBitsConst]]]):
    """
    :see: :class:`TestQueueInStream`
    """

    # class State(Enum):
    #     NO_PKT = auto()  # writeEndOfFrame -> writeStartOfFrame
    #     SOF = auto()  # writeStartOfFrame -> first write
    #     DATA = auto()
    #     EOF = auto()  # write with eof=1 -> writeEndOfFrame

    def __init__(self, frameUtils: SimFrameUtils):
        self._frameUtils = frameUtils
        self._BYTE_WIDTH = frameUtils.BYTE_WIDTH
        self._toBeFilledInLastByte = self._BYTE_WIDTH
        self._BYTE_BIT_MASK = mask(self._BYTE_WIDTH)
        self._byteTy = HBits(self._BYTE_WIDTH)
        self._currentFrame: Optional[deque[Union[int, HBitsConst]]] = None
        self._currentFrameSeenEoF = False

    def write(self, v: HConst, sof=NOT_SPECIFIED, eof=NOT_SPECIFIED):
        frame = self._currentFrame
        if sof is not NOT_SPECIFIED:
            if sof:
                assert not frame
        # print(v, sof, eof)
        assert not self._currentFrameSeenEoF, (self, "Check that no previous data word set EoF")

        w = v._dtype.bit_length()
        if not isinstance(v, HBitsConst):
            v = v._reinterpret_cast(HBits(w))

        val = v.val
        val_vld = v.vld_mask
        toBeFilledInLastByte = self._toBeFilledInLastByte
        BYTE_WIDTH = self._BYTE_WIDTH

        if toBeFilledInLastByte != BYTE_WIDTH:
            # optionally fill the bits in last incomplete byte
            toConsumme = min(toBeFilledInLastByte, w)
            lastB = frame[-1]
            if isinstance(lastB, HConst):
                lastB = Concat(v._trunc(toConsumme), lastB)
            else:
                m = mask(toConsumme)
                bitsAlreadyFilled = BYTE_WIDTH - toBeFilledInLastByte
                _val = val & m
                _val_vld = val_vld & m
                if _val_vld == m:
                    lastB |= _val << bitsAlreadyFilled
                else:
                    # need to convert to HBitsConst because not all bits are valid
                    lastB = HBits(bitsAlreadyFilled + toConsumme).from_py(
                        (val << bitsAlreadyFilled) | lastB,
                        (_val_vld << bitsAlreadyFilled) | mask(bitsAlreadyFilled))
            frame[-1] = lastB
            if toBeFilledInLastByte == toConsumme:
                self._toBeFilledInLastByte = BYTE_WIDTH
            else:
                self._toBeFilledInLastByte -= toConsumme

            val >>= toConsumme
            val_vld >>= toConsumme

            if toConsumme == w:
                w = 0
            else:
                self._toBeFilledInLastByte = BYTE_WIDTH
                w -= toConsumme

        BYTE_BIT_MASK = self._BYTE_BIT_MASK
        byteTy = self._byteTy
        while w:
            # fill complete bytes + potentially incomplete byte at the end
            toConsumme = min(w, BYTE_WIDTH)
            _val = val & BYTE_BIT_MASK
            _val_vld = val_vld & BYTE_BIT_MASK

            if toConsumme == BYTE_WIDTH:
                if _val_vld == BYTE_BIT_MASK:
                    frame.append(_val)
                else:
                    frame.append(byteTy.from_py(_val, _val_vld))
            else:
                m = mask(toConsumme)
                self._toBeFilledInLastByte = BYTE_WIDTH - toConsumme
                if _val_vld == m:
                    frame.append(_val)
                else:
                    frame.append(HBits(toConsumme).from_py(_val, _val_vld))

            val >>= toConsumme
            val_vld >>= toConsumme
            w -= toConsumme
        if eof is not NOT_SPECIFIED:
            if eof:
                self._currentFrameSeenEoF = True

    def writeStartOfFrame(self):
        assert self._currentFrame is None, ("write of previous frame did not end yet")
        self._currentFrame = deque()

    def writeEndOfFrame(self):
        assert self._currentFrame is not None and self._currentFrame, ("There must be some actual words in the frame (enabled or not)", self._currentFrame)
        assert self._currentFrameSeenEoF, ("Data of frame must end with word with eof=1", self._currentFrame)
        self.append(self._currentFrame)
        self._currentFrame = None
        self._currentFrameSeenEoF = False
