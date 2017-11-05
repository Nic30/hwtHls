from hwt.code import Add
from hwt.interfaces.std import VectSignal
from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.param import Param
from hwt.synthesizer.unit import Unit
from hwt.synthesizer.utils import toRtl
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.hls import Hls


class PidController(Unit):
    """
    The PID Control block compares the input to the target
    and calculates an error. Based on this error, a output value is calculated
    that should result in a smaller error on the next iteration of the loop,
    assuming your parameters are tuned properly.

    u(k) = u(k-1) + a0*e(k) + a1*y(k) + a2*y(k-1) + a3*y(k-2)

    e(k): error in this step (= target value - input)
    y(k): input in step k
    ax: PID coeficient

    The PID parameter inputs for this equation are slightly different
    from the traditional K_p, K_i, and K_d.

    a0 = K_i * T_s
    a1 = -K_p - K_d / T_s
    a2 = K_p + 2K_d/T_s
    a3 = - K_d / T_s

    :note: You can obtain coeficiet f.e. by Ziegler-Nichols method.
    """

    def _config(self):
        self.DATAIN_WIDTH = Param(16)
        self.DATAOUT_WIDTH = Param(16)
        self.COEF_WIDTH = Param(16)
        self.CLK_FREQ = Param(int(100e6))

    def _declr(self):
        addClkRstn(self)
        self.input = VectSignal(self.DATAIN_WIDTH, signed=True)
        self.output = VectSignal(self.DATAIN_WIDTH, signed=True)
        self.target = VectSignal(self.DATAIN_WIDTH, signed=True)
        self.coefs = [VectSignal(self.COEF_WIDTH, signed=True)
                      for _ in range(4)]
        self._registerArray("coefs", self.coefs)

    def _impl(self):
        u = self._reg("u", dtype=self.output._dtype, defVal=0)
        err = self._sig("err", dtype=self.input._dtype)
        err(self.input - self.target)

        # create y-pipeline
        y = [self.input, ]
        for i in range(2):
            _y = self._reg("y%d" % i, dtype=self.input._dtype, defVal=0)
            _y(y[-1])
            y.append(_y)

        a = self.coefs

        def trim(signal):
            return signal._reinterpret_cast(self.output._dtype)

        u(Add(u, a[0] * err, a[1] * y[0], a[2] * y[1], a[3] * y[2], key=trim))
        self.output(u)


class PidControllerHls(PidController):
    def _impl(self):
        u = self._reg("u", dtype=self.output._dtype, defVal=0)
        # create y-pipeline
        y = [self.input, ]
        for i in range(2):
            _y = self._reg("y%d" % i, dtype=self.input._dtype, defVal=0)
            # feed data from last register
            _y(y[-1])
            y.append(_y)

        def trim(signal):
            return signal._reinterpret_cast(self.output._dtype)

        with Hls(self, freq=self.CLK_FREQ) as hls:
            r = hls.read
            err = r(self.input) - r(self.target)
            a = [r(c) for c in self.coefs]
            y = [r(_y) for _y in y]

            _u = Add(r(u), a[0] * err, a[1] * y[0],
                     a[2] * y[1], a[3] * y[2], key=trim)
            hls.write(_u, u)
        self.output(u)


if __name__ == "__main__":
    u = PidController()
    print(toRtl(u))
    u = PidControllerHls()
    print(toRtl(u, targetPlatform=VirtualHlsPlatform()))
