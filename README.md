# hwtHls

HLS for [HWToolkit](https://github.com/Nic30/HWToolkit) (hardware devel. toolkit)

### Current state

* This library is in state of prototype. Many features are left out due unfinished code port

* Not ported yet:
 
  * Complex operation reducing (DSP)
  * Universal tree balancing
  * All platfoms
  * Loop agenda
  * memory acess pattern recognizition
  * allocation, schedueling solved by temporary solutions

* This library used to be part of [HWToolkit](https://github.com/Nic30/HWToolkit), in 2017 Q1 it was decided that it needs to be separated library due it's instability and complexity. This rewrite will be finished 15.12.2017.



## How it works.

* hwtHls uses HDL objects from [HWToolkit](https://github.com/Nic30/HWToolkit). 
  It means that generation target HDL and simulation is solved by [HWToolkit](https://github.com/Nic30/HWToolkit).

* hwtHls solves problems latency/resource/delay constrained schedueling/allocation
* uses separated CDFG with backward reference for representation of code
* operator tree balancing, support for non primitive operators (DSP etc., with multiple IO, latency, delay)
* default scheduling ALAP, ASAP, ILP, list based schedueling
* default allocating Left edge, ILP
* loop unroll, pipeline
* Support for Bus, Handshaked, Rd/VldSynced, Signal interfaces

* Metainformations about target platform are classes derived from Platfom class.
  This class is container of HLS settings (Scheduler/Alocator...),
  information about resources and capabilities of target and target specific components (transceiver, PLL wrapper).

* All parts of hwtHls can be modified, there are is no magic. All parts can be used separately.

### Why hwtHls is not compiler
* Nearly all HLS synthesizers performing conversion from source language to target language. HwtHls is different.
* In HwtHls code is written in metalanguage.
* Reason for this is that #pragmas and other compilator directives became major part of code and #pragmas can not contain any code which can run at compilation time. One solution is to use external language for example TCL to controll HLS synthesiser, but still retrospectivity is greatly limited.
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


# related papers

https://people.csail.mit.edu/saman/student_thesis/petkov-01.pdf
