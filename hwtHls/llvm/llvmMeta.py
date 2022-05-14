

class UNROLL():
    """
    llvm/lib/Transforms/Utils/LoopUtils.cpp
    """
    DISABLE_NONFORCED = "llvm.loop.disable_nonforced"
    DISABLE = "llvm.loop.unroll.disable"

    @staticmethod
    def COUNT(n:int):
        return ("llvm.loop.unroll.count", n);

    ENABLE = "llvm.loop.unroll.enable"
    FULL = "llvm.loop.unroll.full"
