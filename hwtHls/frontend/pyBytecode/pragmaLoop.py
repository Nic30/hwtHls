from math import inf
from typing import Union, Literal, Optional

from hwt.hwIO import HwIO
from hwtHls.frontend.pyBytecode.ioProxyStream import IoProxyStream
from hwtHls.frontend.pyBytecode.pragma import _PyBytecodeLoopPragma
from hwtHls.llvm.llvmIr import Argument


class PyBytecodeLLVMLoopUnroll(_PyBytecodeLoopPragma):
    """
    https://releases.llvm.org/16.0.0/docs/LangRef.html#llvm-loop-unroll
    llvm/lib/Transforms/Utils/LoopUtils.cpp

    This adds llvm.loop.unroll pragma. For example:

    .. code-block:: llvm

        br i1 %exitcond, label %._crit_edge, label %.lr.ph, !llvm.loop !0
        ...
        !0 = !{!0, !1, !2}
        !1 = !{!"llvm.loop.unroll.enable"}
        !2 = !{!"llvm.loop.unroll.count", i32 4}
    
    
    :see: llvm::makeFollowupLoopID
    
    llvm.loop.unroll.followup_unrolled will set the loop attributes of the unrolled loop.
    If not specified, the attributes of the original loop without the llvm.loop.unroll.*
    attributes are copied and llvm.loop.unroll.disable added to it.

    llvm.loop.unroll.followup_remainder defines the attributes of the remainder loop.
    If not specified the remainder loop will have no attributes. The remainder loop 
    might not be present due to being fully unrolled in which case this attribute has no effect.

    Attributes defined in llvm.loop.unroll.followup_all are added to the unrolled and remainder loops.
    
    https://yashwantsingh.in/posts/loop-unroll/
    
    .. code-block:: llvm
        ; https://reviews.llvm.org/D49281?id=155318
        !1 = !{!1, !3, !11}
        !2 = !{!"llvm.loop.vectorize.enable", i1 true}
        !3 = !{!"llvm.loop.unroll.count", i32 4}
        !4 = !{!"llvm.loop.vectorize.width", i32 8}
        !11 = !{!"llvm.loop.unroll.followup_unrolled", !2, !4, !{!"llvm.loop.unroll.disable"}}
    
    """

    def __init__(self, enable: bool, count: Union[int, Literal[inf], None],
                 followup_unrolled:Optional[_PyBytecodeLoopPragma]=None,
                 followup_remainder:Optional[_PyBytecodeLoopPragma]=None,
                 followup_all:Optional[_PyBytecodeLoopPragma]=None):
        _PyBytecodeLoopPragma.__init__(self)
        if not enable:
            if count == 1:
                count = None
            else:
                assert count is None, "If this is disable count must not be specified"

        self.enable = enable
        self.count = count
        self.followup_unrolled = followup_unrolled
        self.followup_remainder = followup_remainder
        self.followup_all = followup_all

    def getLlvmLoopMetadataItems(self, irTranslator: "ToLlvmIrTranslator"):
        getStr = irTranslator.mdGetStr
        getInt = irTranslator.mdGetUInt32
        getTuple = irTranslator.mdGetTuple

        items = [
            getTuple([getStr("llvm.loop.unroll.enable" if self.enable else "llvm.loop.unroll.dissable"), ], False),
        ]
        if self.enable:
            count = self.count
            if count is not None:
                if count is inf:
                    md = getTuple([getStr("llvm.loop.unroll.full"), ], False)
                else:
                    md = getTuple([
                            getStr("llvm.loop.unroll.count"),
                            getInt(self.count)
                        ],
                        False)
                items.append(md)
            for followup, followupName in ((self.followup_unrolled, "unrolled"),
                                           (self.followup_remainder, "remainder"),
                                           (self.followup_all, "all")):
                if followup is not None:
                    followup: _PyBytecodeLoopPragma
                    md = getTuple([
                            getStr("llvm.loop.unroll.followup_" + followupName),
                            *followup.getLlvmLoopMetadataItems(irTranslator),
                        ], False)
                    items.append(md)

        return items


class PyBytecodeStreamLoopUnroll(_PyBytecodeLoopPragma):
    """
    Unrolls the loop to meet IO throughput criteria.
    This adds hwthls.loop.streamunroll pragma. For example:

    .. code-block:: llvm

        br i1 %exitcond, label %._crit_edge, label %.lr.ph, !llvm.loop !0
        ...
        !0 = !{!0, !1}
        !1 = !{!"hwthls.loop.streamunroll.io", i32 0}
    
    """

    def __init__(self, io_: Union[HwIO, IoProxyStream], followup:Optional[_PyBytecodeLoopPragma]=None):
        _PyBytecodeLoopPragma.__init__(self)
        self.io = io_
        self.followup = followup

    def getLlvmLoopMetadataItems(self, irTranslator:"ToLlvmIrTranslator"):
        getStr = irTranslator.mdGetStr
        getInt = irTranslator.mdGetUInt32
        getTuple = irTranslator.mdGetTuple
        io_ = self.io
        if isinstance(io_, IoProxyStream):
            io_ = io_.interface
        ioArg: Argument = irTranslator.ioToVar[io_][0]
        ioArgIndex = ioArg.getArgNo();
        items = [
            getTuple([
                    getStr("hwthls.loop.streamunroll.io"),
                    getInt(ioArgIndex)
                ],
                False)
        ]
        if self.followup is not None:
            md = getTuple([
                    getStr("hwthls.loop.streamunroll.followup"),
                    *self.followup.getLlvmLoopMetadataItems(irTranslator),
                ], False)
            items.append(md)

        return items


class PyBytecodeLoopFlattenUsingIf(_PyBytecodeLoopPragma):
    """
    Merge child loop into parent loop.
    """

    def __init__(self, followup:Optional[_PyBytecodeLoopPragma]=None):
        _PyBytecodeLoopPragma.__init__(self)
        self.followup = followup

    def getLlvmLoopMetadataItems(self, irTranslator: "ToLlvmIrTranslator"):
        getStr = irTranslator.mdGetStr
        getInt = irTranslator.mdGetUInt32
        getTuple = irTranslator.mdGetTuple
        items = [
            getTuple([
                    getStr("hwthls.loop.flattenusingif.enable"),
                    getInt(1)
                ],
                False)
        ]
        if self.followup is not None:
            md = getTuple([
                    getStr("hwthls.loop.flattenusingif.followup"),
                    *self.followup.getLlvmLoopMetadataItems(irTranslator),
                ], False)
            items.append(md)

        return items
