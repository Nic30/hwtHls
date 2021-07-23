# hwtHls

[![Travis-ci Build Status](https://travis-ci.org/Nic30/hwtHls.png?branch=master)](https://travis-ci.org/Nic30/hwtHls)[![PyPI version](https://badge.fury.io/py/hwtHls.svg)](http://badge.fury.io/py/hwtHls)[![Coverage Status](https://coveralls.io/repos/github/Nic30/hwtHls/badge.svg?branch=master)](https://coveralls.io/github/Nic30/hwtHls?branch=master)
[![Python version](https://img.shields.io/pypi/pyversions/hwtHls.svg)](https://img.shields.io/pypi/pyversions/hwtHls.svg)


HLS for [HWToolkit](https://github.com/Nic30/HWToolkit) (hardware devel. toolkit)

*As you can see in the section "related opensource" below there is tons of HLS synthesizers. If you are also interested in this area let us know! The HLS community has to be connected!*

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

* hwtHls solves problems of latency/resource/delay constrained scheduling/allocation
* uses separated CDFG with backward reference for representation of code
* operator tree balancing, support for non primitive operators (DSP etc., with multiple IO, latency, delay)
* default scheduling ALAP, ASAP, list based scheduling
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



## Related open-source
* :skull: [legup](http://legup.eecg.utoronto.ca/) (reborn as Microchip SmarthHLS in 2020) - 2011-2015, LLVM based c->verilog
* [PandA-bambu](http://panda.dei.polimi.it/?page_id=31) - 2003-?, GCC based c->verilog
* :skull: [augh](http://tima.imag.fr/sls/research-projects/augh/) - c->verilog, DSP support
* [gemmini](https://github.com/ucb-bar/gemmini) - scala, systolic array generator
* [utwente-fmt](https://github.com/utwente-fmt) - abstract hls, verification libraries
* :skull: [Shang](https://github.com/etherzhhb/Shang) - 2012-2014, LLVM based, c->verilog
* :skull: [xronos](https://github.com/endrix/xronos) [git2](https://github.com/endrix/xronos) - 2012-2016, java, simple HLS
* :skull: [Potholes](https://github.com/SamuelBayliss/Potholes) - 2012-2014 - polyhedral model preprocessor, Uses Vivado HLS, PET
* :skull: [hls_recurse](https://github.com/m8pple/hls_recurse) - 2015-2016 - conversion of recursive fn. for stackless architectures
* :skull: [hg_lvl_syn](https://github.com/funningboy/hg_lvl_syn) - 2010, ILP, Force Directed scheduler
* [abc](https://people.eecs.berkeley.edu/~alanmi/abc/) <2008-?, A System for Sequential Synthesis and Verification
* :skull: [polyphony](https://github.com/ktok07b6/polyphony) - 2015-2017, simple python to hdl
* :skull: [DelayGraph](https://github.com/ni/DelayGraph) - 2016, C#, register assignment alghorithms
* [PipelineC](https://github.com/JulianKemmerer/PipelineC) - 2018, Python, c -> hdl for a limited subset of c
* [coreir](https://github.com/rdaly525/coreir) - 2016-?, LLVM HW compiler
* [spatial](https://github.com/stanford-ppl/spatial)  - , scala
* :skull: [microcoder](https://github.com/ben-marshall/microcoder) - ?-2019, Python, ASM like lang. -> verilog
* :skull: [TAPAS](https://github.com/sfu-arch/TAPAS) - 2018-2019, c++, Generating Parallel Accelerators fromParallel Programs
* :skull: [DHLS](https://github.com/dillonhuff/DHLS) - 2019-?, C++, A Basic High Level Synthesis System Using LLVM
* :skull: [ahaHLS](https://github.com/dillonhuff/ahaHLS) - 2018-2019, A Basic High Level Synthesis System Using LLVM
* [pluto](https://github.com/bondhugula/pluto) -  An automatic polyhedral parallelizer and locality optimizer
* :skull: [ctoverilog](https://github.com/udif/ctoverilog) ?-2015 - A C to verilog compiler, LLVM
* :skull: [exprc](https://github.com/n-nez/exprc) - 2018-2018, C++, a toy HLS compiler
* :skull: [kiwi](https://www.cl.cam.ac.uk/~djg11/kiwi/) 2003-2017
* :skull: [ElasticC](https://github.com/daveshah1/ElasticC)  ?-2018 - C++, lightweight open HLS for FPGA rapid prototyping
* :skull: [c-ll-verilog](https://github.com/sabbaghm/c-ll-verilog) 2017-2017, C++, An LLVM based mini-C to Verilog High-level Synthesis tool
* [xls](https://github.com/google/xls) - 2020-?, C++ HLS compiler with JIT
* :skull: [Chips-2.0](https://github.com/dawsonjon/Chips-2.0) - 2011-2019, Python, C->Verilog HLS
* [tiramisu](https://github.com/Tiramisu-Compiler/tiramisu) - 2016-?, C++, A polyhedral compiler

## Useful publications
* [Efficient Pipelining of Nested Loops: Unroll-and-Squash](https://people.csail.mit.edu/saman/student_thesis/petkov-01.pdf)
* [Coordinated Parallelizing Compiler Optimizations and High-Level Synthesis](https://escholarship.org/uc/item/3421b3h6)
* [Parallel Programming for FPGAs](https://github.com/KastnerRG/pp4fpgas)
* [Speculative Dataflow Circuits](https://dl.acm.org/citation.cfm?id=3293914)
* 2012 [An overview of today's high-level synthesis tools](https://www.researchgate.net/publication/260432684_An_overview_of_today's_high-level_synthesis_tools)
* 2015 [A Survey and Evaluation of FPGA High-Level Synthesis Tools](https://ieeexplore.ieee.org/document/7368920)
* 2019 [Are We There Yet? A Study on the State of High-Level Synthesis](https://ieeexplore.ieee.org/document/8356004)
