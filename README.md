# hwtHls

[![Travis-ci Build Status](https://travis-ci.org/Nic30/hwtHls.png?branch=master)](https://travis-ci.org/Nic30/hwtHls)[![PyPI version](https://badge.fury.io/py/hwtHls.svg)](http://badge.fury.io/py/hwtHls)[![Coverage Status](https://coveralls.io/repos/github/Nic30/hwtHls/badge.svg?branch=master)](https://coveralls.io/github/Nic30/hwtHls?branch=master)


HLS for [HWToolkit](https://github.com/Nic30/HWToolkit) (hardware devel. toolkit)

### Current state

* This library is in alpha phase.

* Not done yet:
  * Complex operation reducing (DSP, LUT, CLB ...)
  * Universal tree balancing, operation reordering
  * All platforms
  * Loop agenda
  * memory access pattern recognization, partition (fifo, single/double port ram ...)
  * allocation, scheduling solved by temporary solutions (partial true)
  * netlist query
  * DMA logic for generic bus access
  * automatic micro kernels

## How it works.
* hwtHls uses HDL objects from [HWToolkit](https://github.com/Nic30/HWToolkit). 
  It means that generation target HDL and simulation is solved by [HWToolkit](https://github.com/Nic30/HWToolkit).

* hwtHls solves problems of latency/resource/delay constrained schedueling/allocation
* uses separated CDFG with backward reference for representation of code
* operator tree balancing, support for non primitive operators (DSP etc., with multiple IO, latency, delay)
* default scheduling ALAP, ASAP, list based schedueling
* default allocating Left edge
* loop unroll, pipeline
* Support for Bus, Handshaked, Rd/VldSynced, Signal interfaces

* Meta-informations about target platform are classes derived from Platform class.
  This class is container of HLS settings (Scheduler/Allocator...),
  information about resources and capabilities of target and target specific components (transceiver, PLL wrapper).

* All parts of hwtHls can be modified, there are is no magic. All parts can be used separately.

### Why hwtHls is not compiler
* Nearly all HLS synthesizers performing conversion from source language to target language. HwtHls is different.
* In HwtHls code is written in meta-language.
* Reason for this is that #pragmas and other compiler directives became major part of code and #pragmas can not contain any code which can run at compilation time. One solution is to use external language for example TCL to control HLS synthesiser, but still retrospectivity is greatly limited.
* Metalanguage description allows very precise driving of HLS process with minimum effort. 


# Example MAC operation

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-


from hwt.interfaces.std import VectSignal
from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.param import Param
from hwt.synthesizer.unit import Unit
from hwtHls.hls import Hls



class HlsMAC_example(Unit):
    def _config(self):
        self.CLK_FREQ = Param(int(100e6))

    def _declr(self):
        addClkRstn(self)
        self.a = VectSignal(32, signed=False)
        self.b = VectSignal(32, signed=False)
        self.c = VectSignal(32, signed=False)
        self.d = VectSignal(32, signed=False)
        self.e = VectSignal(64, signed=False)

    def _impl(self):
        with Hls(self, freq=self.CLK_FREQ) as hls:
            # inputs has to be readed to enter hls scope
            # (without read() operation will not be schedueled by HLS
            #  but they will be directly synthesized)
            a, b, c, d = [hls.read(intf)
                          for intf in [self.a, self.b, self.c, self.d]]

            # depending on target platform this expresion
            # can be mapped to DPS, LUT, etc...
            # no constrains are specified => default strategy is
            # to achieve zero delay and minimum latency, for this CLK_FREQ
            e = a * b + c * d

            hls.write(e, self.e)

if __name__ == "__main__":
    import unittest
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synthesizer.utils import toRtl
    
    u = HlsMAC_example()
    print(toRtl(u, targetPlatform=VirtualHlsPlatform()))
```



# related opensource

http://legup.eecg.utoronto.ca/

http://panda.dei.polimi.it/?page_id=31

http://tima.imag.fr/sls/research-projects/augh/

https://github.com/utwente-fmt

https://github.com/etherzhhb/Shang

https://github.com/endrix/xronos

https://github.com/SamuelBayliss/Potholes

https://github.com/m8pple/hls_recurse

https://github.com/funningboy/hg_lvl_syn

https://people.eecs.berkeley.edu/~alanmi/abc/



# related papers

https://people.csail.mit.edu/saman/student_thesis/petkov-01.pdf

https://escholarship.org/uc/item/3421b3h6
