from hwt.hdl.operatorDefs import AllOps
from hwt.serializer.resourceAnalyzer.resourceTypes import ResourceFF,\
    ResourceMUX
from hwtHls.platform.xilinx.abstract import AbstractXilinxPlatform


class Artix7Slow(AbstractXilinxPlatform):
    """
    https://www.xilinx.com/support/documentation/data_sheets/ds181_Artix_7_Data_Sheet.pdf
    """

    def _initDelayCoefs(self):
        self.ARC_DELAY = 1.447
        self.LUT6_DELAY = 0.124
        self.MUXF7_DELAY = 0.368
        self.MUXF8_DELAY = 0.296
        self.NET_DELAY = 0.776
        self.MUL_DSP_WIDTH_THRESHOLD = 5
        self.FF_DELAY_SETUP = 0.53
        self.FF_DELAY_HOLD = 0.07

        self.MUL_COMB_DELAYS = [0.6, 0.9, 1.1, 1.4, 2.6]
        self.ADD_COMB_DELAYS = {1.0: [1.0, 1.544], 2.0: [1.0, 2.276], 3.0: [
            1.0, 2.633], 4.0: [1.0, 2.797], 5.0: [1.0, 3.468], 6.0: [1.0, 4.439]}
        self.CMP_DELAY = {1.0: [1.0, 1.544], 2.0: [1.0, 2.331], 3.0: [1.0, 2.469], 4.0: [
            1.0, 2.774], 5.0: [1.0, 2.931], 6.0: [1.0, 3.353], 7.0: [1.0, 4.419]}
        self.BITWISE_DELAY = self.LUT6_DELAY + self.MUXF7_DELAY + self.NET_DELAY

        self.OP_COMB_DELAYS = {

            AllOps.AND: self.get_bitwise_op_delay,
            AllOps.OR: self.get_bitwise_op_delay,
            AllOps.XOR: self.get_bitwise_op_delay,
            AllOps.NOT: self.get_bitwise_op_delay,

            AllOps.NEG: self.get_bitwise_op_delay,
            AllOps.ADD: self.get_add_op_delay,
            AllOps.SUB: self.get_add_op_delay,

            AllOps.MUL: self.get_mul_delay,
            ResourceMUX: self.get_mux_delay,
            ResourceFF: self.get_ff_delay,
        }
