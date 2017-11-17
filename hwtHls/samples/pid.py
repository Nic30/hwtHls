from hwt.code import Add
from hwt.synthesizer.param import Param
from hwt.synthesizer.utils import toRtl
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.hls import Hls
from hwtLib.logic.pid import PidController


class PidControllerHls(PidController):
    def _config(self):
        super(PidControllerHls, self)._config()
        self.CLK_FREQ = Param(int(100e6))

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
