# hwtHls

[![CircleCI](https://circleci.com/gh/Nic30/hwtHls/tree/master.svg?style=svg)](https://circleci.com/gh/Nic30/hwtHls/tree/master)[![PyPI version](https://badge.fury.io/py/hwtHls.svg)](http://badge.fury.io/py/hwtHls)[![Coverage Status](https://coveralls.io/repos/github/Nic30/hwtHls/badge.svg?branch=master)](https://coveralls.io/github/Nic30/hwtHls?branch=master)
[![Python version](https://img.shields.io/pypi/pyversions/hwtHls.svg)](https://img.shields.io/pypi/pyversions/hwtHls.svg)


A library for an automatic translation of algorithmic code to a hardware realization
based on [hwt](https://github.com/Nic30/hwt) (hwt is a library for circuit construction) and
[LLVM](https://llvm.org/) (a compiler infrastructure).

This library is build as a tool which lets you write code transformations
and provides variety of existing ones (from LLVM/hwt) in order to build efficient code generators.

* Powerful optimization passes form LLVM/HWT
* Target specification for common FPGAs
* Integration with HWT: SystemVerilog/VHDL export, various interfaces and components, verification API


### Current state

* This library is in alpha phase.

* Features
  * Python bytecode -> LLVM -> hwt -> vhdl/verilog/IP-exact
    * no exceptions, function calls must be explicitely marked for hw otherwise evaluated compile time
    * only static typing, limited use of iterators
    * (meant to be used for simple things, for the rest there are "statement-like objects")

  * Python statement-like objects -> LLVM -> hwt -> vhdl/verilog/IP-exact
    * Support for multithreaded programs
      (multiple hls programs with shared resources cooperating using shared memory or streams and
       with automatic constrains propagation on shared resource)
    * Supports for programs which are using resoruce shared with HDL code
     (e.g. bus mapped registers where bus mapping is done in HDL (hwt))

  * Support for precise latency/resources tuning
    * FSM/dataflow fine graded architecture
     (strategy specified as a sequence of transformations)

  * Precise operation scheduling using target device timing characteristics (any Xilinx, Intel and others after benchmark)

  * All optimizations aware of independent slice drivers
    * SsaPassExtractPartDrivers - splits the slices to individual variables to exploit real dependencies, splits also bitwise operations and casts
    * ConstantBitPropagationPass - recursively minimizes the number of bits used by variables

  * Any loop type with special care for:
    * Infinite top loops - with/without internal/external sync beeing involved
    * Loops where sync can be achieved only by data (no speculation, all inputs depends on every output)
    * Polyhedral, affine, unroll and other transformations
    * On demand speculations/out-of-order execution:
        * next iteration speculation before break
        * speculativele execution of multiple loop bodies
        * after loop code speculative execution before break
        * cascading of speculation
        * speculative IO access using LSU (for memory mapped IO) or buffers with confirmation (for IO streams)

  * Support for Handshake/ReadySynced/ValidSynced/Signal streams
    (= handshake and all its degenerated variants = any single channel interface)
    * arbitrary number of IO operations for any scheduling type
    * support for side channels, virtual channels, multiple packets per clock
      (e.g. xgmii)
    * explicit blocking, explicit dropping, explicit skipping
      (e.g. conditional read/write of data, read without consummer)
    * Support for read/write of packet(HStream) types
      * Per channel specific settings
      * Processing of arbitrary size types using cursor or index of limited size
      * Support for headers/footers in HStream
      * incremental packet parsing/deparsing, read/write chunk:
        * may not be alligned to word
        * may cause under/overflow
        * may be required to be end of stream or not
      * Optional check of input packet format
        (or synchronized by the input packet format which significantly reduce circuit complexity)


* Not done yet:
  * Complex operation reducing (DSP)
  * All platforms
  * Memory access pattern, partition API between Python and LLVM


## How it works?

* The input code is parsed into SSA objects defined in `hwtHls.ssa`.
  (The code is loaded using `HlsStreamProc` object in [hwt](https://github.com/Nic30/hwt) component (`Unit` class),
   the constraints and interface types are specified as [hwt](https://github.com/Nic30/hwt) objects.)
* There are several optimization SSA passes (common subexpression elimination, dead code elimination
  instruction combining, control optimization, ...). Full list of optimizations is specified in HlsPlatform.
* Optimized SSA is then converted to a `hwtHls.netlist` and scheduled to clock cycles.
  uses HDL objects from [hwt](https://github.com/Nic30/hwt).
* Secheduled netlist is then translated to [hwt](https://github.com/Nic30/hwt) netlist which handles all SystemVerilog/VHDL/simulator/verification related things.


### Why hwtHls is not a compiler?

* Nearly all HLS synthesizers performing conversion from source language and constraints to a target language.
  But there are many cases where a complex preprocessor code is required to generate efficient hardware because
  it is not possible to interfere everything and constraint computation may also be complex.
  Because of this this library uses python as a preprocessor and the input code is build from statement-like objects.
  The benefit of Python object is that user can generate/analyze/modify it on demand.


### Installation

Linux:
```
apt install build-essential python3-dev llvm-12-dev
pip3 install -r https://raw.githubusercontent.com/Nic30/hwtHls/master/doc/requirements.txt
pip3 install git+git://github.com/Nic30/hwtHls.git
```



## Related open-source
* :skull: [ahaHLS](https://github.com/dillonhuff/ahaHLS) - 2018-2019, A Basic High Level Synthesis System Using LLVM
* :skull: [augh](http://tima.imag.fr/sls/research-projects/augh/) - c->verilog, DSP support
* :skull: [c-ll-verilog](https://github.com/sabbaghm/c-ll-verilog) 2017-2017, C++, An LLVM based mini-C to Verilog High-level Synthesis tool
* :skull: [Chips-2.0](https://github.com/dawsonjon/Chips-2.0) - 2011-2019, Python, C->Verilog HLS
* :skull: [COMBA](https://github.com/zjru/COMBA) - 2017-2020, C++/LLVM, focused on resource constrained scheduling
* :skull: [ctoverilog](https://github.com/udif/ctoverilog) ?-2015 - A C to verilog compiler, LLVM
* :skull: [DelayGraph](https://github.com/ni/DelayGraph) - 2016, C#, register assignment alghorithms
* :skull: [DHLS](https://github.com/dillonhuff/DHLS) - 2019-?, C++, A Basic High Level Synthesis System Using LLVM
* :skull: [ElasticC](https://github.com/daveshah1/ElasticC)  ?-2018 - C++, lightweight open HLS for FPGA rapid prototyping
* :skull: [exprc](https://github.com/n-nez/exprc) - 2018-2018, C++, a toy HLS compiler
* :skull: [hg_lvl_syn](https://github.com/funningboy/hg_lvl_syn) - 2010, ILP, Force Directed scheduler
* :skull: [hls_recurse](https://github.com/m8pple/hls_recurse) - 2015-2016 - conversion of recursive fn. for stackless architectures
* :skull: [kiwi](https://www.cl.cam.ac.uk/~djg11/kiwi/) 2003-2017
* :skull: [LegUp](http://legup.eecg.utoronto.ca/) (reborn as Microchip SmarthHLS in 2020) - 2011-2015, LLVM based c->verilog
* :skull: [microcoder](https://github.com/ben-marshall/microcoder) - ?-2019, Python, ASM like lang. -> verilog
* :skull: [polyphony](https://github.com/ktok07b6/polyphony) - 2015-2017, simple python to hdl
* :skull: [Potholes](https://github.com/SamuelBayliss/Potholes) - 2012-2014 - polyhedral model preprocessor, Uses Vivado HLS, PET
* :skull: [Shang](https://github.com/etherzhhb/Shang) - 2012-2014, LLVM based, c->verilog
* :skull: [streamit-hls](https://github.com/stenzek/streamit-hls) - 2017, custom lang, based on micro kernels
* :skull: [TAPAS](https://github.com/sfu-arch/TAPAS) - 2018-2019, c++, Generating Parallel Accelerators fromParallel Programs
* :skull: [xronos](https://github.com/endrix/xronos) [git2](https://github.com/endrix/xronos) - 2012-2016, java, simple HLS
* [ahir](https://github.com/madhavPdesai/ahir) - LLVM, c->vhdl
* [abc](https://people.eecs.berkeley.edu/~alanmi/abc/) <2008-?, A System for Sequential Synthesis and Verification
* [blarney](https://github.com/blarney-lang/blarney)
* [calyx](https://github.com/cucapra/calyx) - , Rust - compiler infrastructure with custom lang focused on ML accelerators
* [clash-compiler](https://github.com/clash-lang/clash-compiler)
* [coreir](https://github.com/rdaly525/coreir) - 2016-?, LLVM HW compiler
* [dynamatic](https://github.com/lana555/dynamatic) - , C++/LLVM - set of LLVM passes for dynamically scheduled HLS
* [futil](https://github.com/cucapra/futil) - 2020-?, custom lang.
* [gemmini](https://github.com/ucb-bar/gemmini) - scala, systolic array generator
* [Hastlayer](https://github.com/Lombiq/Hastlayer-SDK) - 2012-2019, C# -> HW
* [heterocl](https://awesomeopensource.com/project/cornell-zhang/heterocl)
* [PandA-bambu](http://panda.dei.polimi.it/?page_id=31) - 2003-?, GCC based c->verilog
* [PipelineC](https://github.com/JulianKemmerer/PipelineC) - 2018, Python, c -> hdl for a limited subset of c
* [pluto](https://github.com/bondhugula/pluto) -  An automatic polyhedral parallelizer and locality optimizer
* [Slice](https://github.com/sylefeb/Silice)
* [spatial](https://github.com/stanford-ppl/spatial)  - , scala
* [tiramisu](https://github.com/Tiramisu-Compiler/tiramisu) - 2016-?, C++, A polyhedral compiler
* [utwente-fmt](https://github.com/utwente-fmt) - abstract hls, verification libraries
* [xls](https://github.com/google/xls) - 2020-?, C++ HLS compiler with JIT
* [binaryen](https://github.com/WebAssembly/binaryen) - , C++, WebAssembly compiler (implements some similar optimization passes)
* [Light-HLS](https://github.com/zslwyuan/Light-HLS) -, C++/LLVM, experimental HLS framework
* [DASS](https://github.com/JianyiCheng/DSS) - combination of dynamic and static scheduling
* [phism](https://github.com/kumasento/phism) - Python/C++/LLVM, Polyhedral High-Level Synthesis in MLIR
* [ICSC](https://github.com/intel/systemc-compiler) - C++/LLVM, systemC compiler
* [Xilinx/Vitis HLS](https://github.com/Xilinx/HLS) - C++/LLVM, partially opensource
* [circt-hls](https://github.com/circt-hls/circt-hls) - C++/LLVM/Python, set of hls libraries for circt
* [ScaleHLS](https://github.com/hanchenye/scalehls) - C++/LLVM, MLIR based HLS compiler, ML focused
* [DuroHLS](https://github.com/corelab-src/DuroHLS-opt) - C++/LLVM, set of hls passes
* [domino-compiler](https://github.com/packet-transactions/domino-compiler) 2016 -> C++, c like packet processing language and compiler
* [orcc](https://github.com/orcc/orcc) - C++/LLVM, Open RVC-CAL Compiler hw/sw dataflow and img processing focused

## Useful publications
* [Efficient Pipelining of Nested Loops: Unroll-and-Squash](https://people.csail.mit.edu/saman/student_thesis/petkov-01.pdf)
* [Coordinated Parallelizing Compiler Optimizations and High-Level Synthesis](https://escholarship.org/uc/item/3421b3h6)
* [Parallel Programming for FPGAs](https://github.com/KastnerRG/pp4fpgas)
* [Speculative Dataflow Circuits](https://dl.acm.org/citation.cfm?id=3293914)
* 2004 [Algorithm Synthesis by Lazy Thinking: Examples and Implementation in Theorema](https://doi.org/10.1016/j.entcs.2003.12.027)
* 2012 [An overview of today's high-level synthesis tools](https://www.researchgate.net/publication/260432684_An_overview_of_today's_high-level_synthesis_tools)
* 2015 [A Survey and Evaluation of FPGA High-Level Synthesis Tools](https://ieeexplore.ieee.org/document/7368920)
* 2019 [Are We There Yet? A Study on the State of High-Level Synthesis](https://ieeexplore.ieee.org/document/8356004)
* [LLVM dialect overview](https://llvm.discourse.group/t/codegen-dialect-overview/2723)
* [dynamatically scheduled circuits](https://dynamatic.epfl.ch/)
* [Stackifier algorithm](https://medium.com/leaningtech/solving-the-structured-control-flow-problem-once-and-for-all-5123117b1ee2) converts SSA back to cycles and conditions
* [DASS: Combining Dynamic and Static Scheduling in High-level Synthesis](https://www.researchgate.net/publication/350081168_DASS_Combining_Dynamic_and_Static_Scheduling_in_High-level_Synthesis)
* [Enabling adaptive loop pipelining in high-level synthesis](https://doi.org/10.1109/ACSSC.2017.8335152)
* SODA [Chi, ICCAD 18]
* Darkroom [Hegarty, TOG 14]
* Aetherling [Durst, PLDI 20]
* Polymage-FPGA [Chugh, PACT 16]
* Rigel [Hegarty, TOG 16]
* Halide-HLS [Pu, TACO 17]
* Hipacc-FPGA [Reiche, CODES + ISS 14] https://github.com/hipacc/hipacc-fpga
* Clokwork [Huff, FCCM 21] https://github.com/dillonhuff/clockwork

## Timing database generator scripts

* [Light-HLS](https://github.com/zslwyuan/Light-HLS/blob/master/HLS_Lib_Generator/LibGen.py)
