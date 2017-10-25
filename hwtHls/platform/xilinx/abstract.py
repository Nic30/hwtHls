from functools import lru_cache
from hwtHls.platform.interpolations import interpolate_area_2d, downscale_width


class AbstractXilinxPlatform():
    def __init__(self):
        # {inputCnt: (lut6_coef, mux7f_coef, mux8f_coef)}
        self.mux_coefs = self._initMuxCoefs()
        self.mux_coefs_inputs = list(self.mux_coefs.keys())
        self.mux_coefs_inputs.sort()
        self._initDelayCoefs()

    def _initMuxCoefs(self):
        """
        get mux coefs dict

        :return: {inputCnt: (lut6_coef, mux7f_coef, mux8f_coef)}
        """
        raise NotImplementedError(
            "Override this in your implementation of platform")

    def _initDelayCoefs(self):
        """
        set delay coefficients
        """
        raise NotImplementedError(
            "Override this in your implementation of platform")
        # example values to allow IDE to gues attribute types
        self.ARC_DELAY = 1
        self.LUT6_DELAY = 1
        self.MUXF7_DELAY = 1
        self.MUXF8_DELAY = 1
        self.NET_DELAY = 1
        self.CMP_DELAY = {1.0: (1, 1)}

    @lru_cache()
    def get_op_delay(self, op, bit_width: int, clk_period: float):
        w = downscale_width(bit_width)
        data = self.OP_DELAYS[op]
        return interpolate_area_2d(data, w, clk_period)

    def get_bitwise_op_delay(self, input_cnt: int, clk_period: float):
        """
        delay for bitwise AND, OR, XOR etc
        """
        return self.NET_DELAY + self.LUT6_DELAY + self.MUXF7_DELAY

    def get_cmp_delay(self, bit_width: int, clk_period: float):
        interpolate_area_2d(self.CMP_DELAY, bit_width, clk_period)

    @lru_cache()
    def get_mux_delay(self, input_cnt: int, clk_period: float):
        """
        Formula-based delay lookup for multiplexer

        :return: delay of a mux based on the following formula:
            delay = ARC + K1*LUT6 + K2*MUX7F + K3*MUX8F + (K1-1)*NET
        """
        input_number_list = self.mux_coefs

        # get the delay parameters
        ARC = self.ARC_DELAY
        LUT6 = self.LUT6_DELAY
        MUXF7 = self.MUXF7_DELAY
        MUXF8 = self.MUXF8_DELAY
        NET = self.NET_DELAY

        delay = 0
        while input_cnt > 1:
            # if input_cnt > input_number_max, we divide the mux into several
            # pieces the last piece's input number <= input_number_max,
            # others = input_number_max.
            for piece_input_number in input_number_list:
                if input_cnt <= piece_input_number:
                    break

            # now we get the input number of current piece,
            # calculate the remaining input number
            input_cnt = (input_cnt + piece_input_number -
                         1) / piece_input_number

            K1, K2, K3 = self.mux_coefs[piece_input_number]

            # add delay of current piece
            piece_delay = (ARC +
                           K1 * LUT6 +
                           K2 * MUXF7 +
                           K3 * MUXF8 +
                           (K1 - 1) * NET)
            delay = delay + piece_delay

            # add net delay if it's not the last piece
            if input_cnt > 1:
                delay = delay + NET

        return delay
