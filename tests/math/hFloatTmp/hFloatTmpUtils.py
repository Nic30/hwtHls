from hwtHls.llvm.llvmIr import HFloatTmpConfig
from tests.math.fixp.fixpTypes import HFixedPointQ
from tests.math.fp.fptypes import IEEE754Fp


def HFloatTmpConfigToHType(cfg: HFloatTmpConfig):
    if cfg.isInQFormat:
        return HFixedPointQ.fromHFloatTmpConfig(cfg)
    else:
        return IEEE754Fp.fromHFloatTmpConfig(cfg)
