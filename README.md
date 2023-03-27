# hwtHls

[![CircleCI](https://circleci.com/gh/Nic30/hwtHls/tree/master.svg?style=svg)](https://circleci.com/gh/Nic30/hwtHls/tree/master)[![PyPI version](https://badge.fury.io/py/hwtHls.svg)](http://badge.fury.io/py/hwtHls)[![Coverage Status](https://coveralls.io/repos/github/Nic30/hwtHls/badge.svg?branch=master)](https://coveralls.io/github/Nic30/hwtHls?branch=master)


A library for an automatic translation of algorithmic code to a hardware realization
based on [hwt](https://github.com/Nic30/hwt) (hwt is a library for circuit construction) and
[LLVM](https://llvm.org/) (a compiler infrastructure).

This library is build as a tool which lets you write code transformations
and provides variety of existing ones (from LLVM/hwt) in order to build efficient code generators.

* Powerful optimization passes form LLVM/HWT/ABC
* Target specification for common FPGAs with possiblity for user to specify any custom target
* Integration with HWT: SystemVerilog/VHDL export, various interfaces and components, verification API, build automation


A typical project where you would use this project is a hash table in HBM2 memory with cache.
* HBM2 may have 32 AXI4 ports, you need to use eta 64*32 transactions at once to saturate memory throughput.
* All transactions must assert consistency.
* Due to timing, everything needs to be pipelined and the hash table must support multiple operations in a single clock.

In this case you would just write a generic algorithm of a hash table and then configure numbers of ports, latencies
coherency domains and it is all done. Take look at FlowCache example. Because everything is generated, it is asserted that
no consistency check is missing and any deadlock or synchronization error may happen internally.
This is a big difference from hand crafted hardware, where it is assured, that you would make mistakes of this type.


### Current state

* This library is in an alpha phase.
* You can try it online at [![Binder](https://mybinder.org/badge_logo.svg)](https://notebooks.gesis.org/binder/v2/gh/Nic30/hwtHls/HEAD) (From jupyterlab you can also run examples in tests.)

* Features
  * Python bytecode -> LLVM -> hwt -> vhdl/verilog/IP-exact
    * Bytecode of any Python can be translated to hardware
       * Bytecode is symbolically executed and the code which does not depend on HW evaluated value is executed immediately.
         This means that the python runs as a preprocessors and it generates HW code.
       * As this part translates bytecode to SSA the input syntax does not matter.

    * No exception handling, function calls must be explicitly marked to be translated to HW otherwise calls are evaluated compile time
    * Only static typing for HW code, limited use of iterators
    * (meant to be used for simple things, for the rest you should construct AST or SSA directly.)

  * Python statement-like objects/AST -> LLVM -> hwt -> vhdl/verilog/IP-exact
    * Support for multithreaded programs
      (multiple hls programs with shared resources cooperating using shared memory or streams and
       with automatic constrains propagation on shared resource)
    * Supports for programs which are using resoruce shared with HDL code
     (e.g. bus mapped registers where bus mapping is done in HDL (hwt))

  * Support for precise latency/resources tuning
    * Operation chaining
    * FSM/dataflow fine-graded architecture extraction with different optimization strategies
     (extraction strategy specified as a sequence of transformations)

  * Precise operation scheduling using target device timing characteristics (any Xilinx, Intel and others after benchmark)

  * Fine-graded HW resource optimizations
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

* see doc in `hwtHls/__init__.py`


### Installation

Linux:
```
apt install build-essential python3-dev llvm-14 llvm-14-dev
# you need also make llvm-14 as a default llvm, https://github.com/mesonbuild/meson/issues/10396
update-alternatives --install /usr/bin/llvm-config llvm-config /usr/bin/llvm-config-14 100
pip3 install -r https://raw.githubusercontent.com/Nic30/hwtHls/master/doc/requirements.txt
# if you do not run previous command you will install dependencies from pip which may outdated
pip3 install git+https://github.com/Nic30/hwtHls.git
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
* :skull: [Trident](https://sourceforge.net/projects/trident/) - 2006, java/C++/LLVM
* :skull: [FPGA C Compiler](https://sourceforge.net/projects/fpgac/) - 2005-2006, trivial 1:1 c->vhdl
* :skull: [hpiasg](https://github.com/hpiasg) - , set of tools for asynchronous and handshake circuit synthesis
* [abc](https://people.eecs.berkeley.edu/~alanmi/abc/) <2008-?, A System for Sequential Synthesis and Verification
* [ahir](https://github.com/madhavPdesai/ahir) - LLVM, c->vhdl
* [binaryen](https://github.com/WebAssembly/binaryen) - , C++, WebAssembly compiler (implements some similar optimization passes)
* [blarney](https://github.com/blarney-lang/blarney)
* [calyx](https://github.com/cucapra/calyx) - , Rust - compiler infrastructure with custom lang focused on ML accelerators
* [CirC](https://github.com/circify/circ) - Rust - compiler infrastructure for HLS
* [circt-hls](https://github.com/circt-hls/circt-hls) - C++/LLVM/Python, set of hls libraries for circt
* [clash-compiler](https://github.com/clash-lang/clash-compiler)
* [coreir](https://github.com/rdaly525/coreir) - 2016-?, LLVM HW compiler
* [DASS](https://github.com/JianyiCheng/DSS) - combination of dynamic and static scheduling
* [domino-compiler](https://github.com/packet-transactions/domino-compiler) 2016 -> C++, c like packet processing language and compiler
* [DPC++](https://github.com/intel/llvm/tree/sycl) - C++/LLVM,
* [DuroHLS](https://github.com/corelab-src/DuroHLS-opt) [CorelabVerilog](https://github.com/corelab-src/CorelabVerilog) - C++/LLVM, set of hls passes
* [dynamatic](https://github.com/lana555/dynamatic) - , C++/LLVM - set of LLVM passes for dynamically scheduled HLS
* [FloPoCo](https://gitlab.com/flopoco/flopoco) - C++, arithmetic core generator
* [futil](https://github.com/cucapra/futil) - 2020-?, custom lang.
* [gemmini](https://github.com/ucb-bar/gemmini) - scala, systolic array generator
* [Hastlayer](https://github.com/Lombiq/Hastlayer-SDK) - 2012-2019, C# -> HW
* [heterocl](https://awesomeopensource.com/project/cornell-zhang/heterocl)
* [ICSC](https://github.com/intel/systemc-compiler) - C++/LLVM, systemC compiler
* [Light-HLS](https://github.com/zslwyuan/Light-HLS) -, C++/LLVM, experimental HLS framework
* [mockturtle](https://github.com/lsils/mockturtle) - C++, logic network lib. with project similar to HLS
* [orcc](https://github.com/orcc/orcc) - C++/LLVM, Open RVC-CAL Compiler hw/sw dataflow and img processing focused
* [PandA-bambu](http://panda.dei.polimi.it/?page_id=31) - 2003-?, GCC based c->verilog
* [phism](https://github.com/kumasento/phism) - Python/C++/LLVM, Polyhedral High-Level Synthesis in MLIR
* [PipelineC](https://github.com/JulianKemmerer/PipelineC) - 2018, Python, c -> hdl for a limited subset of c
* [pluto](https://github.com/bondhugula/pluto) -  An automatic polyhedral parallelizer and locality optimizer
* [ROCCC](https://github.com/nxt4hll/roccc-2.0), http://roccc.cs.ucr.edu/ - 2009-2013, C++/LLVM/suif c -> vhdl
* [ScaleHLS](https://github.com/hanchenye/scalehls) - C++/LLVM, MLIR based HLS compiler, ML focused
* [Slice](https://github.com/sylefeb/Silice)
* [spatial](https://github.com/stanford-ppl/spatial)  - , scala
* [TCE](https://github.com/cpc/tce)- C++/LLVM, environment for development of application specific processors
* [tiramisu](https://github.com/Tiramisu-Compiler/tiramisu) - 2016-?, C++, A polyhedral compiler
* [Tydi](https://github.com/abs-tudelft/tydi) - Rust, specification for complex data structures over hardware streams
* [UCLA-VAST/TAPA](https://github.com/UCLA-VAST/tapa) - C++, HLS tool build on the top of VivadoHLS with explicit paralelism
* [utwente-fmt](https://github.com/utwente-fmt) - abstract hls, verification libraries
* [Xilinx/Vitis HLS](https://github.com/Xilinx/HLS) - C++/LLVM, partially opensource
* [xls](https://github.com/google/xls) - 2020-?, C++ HLS compiler with JIT

## Useful publications
* [Efficient Pipelining of Nested Loops: Unroll-and-Squash](https://people.csail.mit.edu/saman/student_thesis/petkov-01.pdf)
* [Coordinated Parallelizing Compiler Optimizations and High-Level Synthesis](https://escholarship.org/uc/item/3421b3h6)
* [Parallel Programming for FPGAs](https://github.com/KastnerRG/pp4fpgas)
* [Speculative Dataflow Circuits](https://dl.acm.org/citation.cfm?id=3293914)
* 2004 [Algorithm Synthesis by Lazy Thinking: Examples and Implementation in Theorema](https://doi.org/10.1016/j.entcs.2003.12.027)
* 2010 [Impact of High-Level Transformations within the ROCCC Framework](https://www.cs.ucr.edu/~najjar/papers/2010/TACO-2010.pdf)
* 2012 [An overview of today's high-level synthesis tools](https://www.researchgate.net/publication/260432684_An_overview_of_today's_high-level_synthesis_tools)
* [c-to-verilog publications](https://cs.haifa.ac.il/~rotemn/pubs.html)
* 2015 [A Survey and Evaluation of FPGA High-Level Synthesis Tools](https://ieeexplore.ieee.org/document/7368920)
* 2019 [Are We There Yet? A Study on the State of High-Level Synthesis](https://ieeexplore.ieee.org/document/8356004)
* [LLVM dialect overview](https://llvm.discourse.group/t/codegen-dialect-overview/2723)
* [dynamatically scheduled circuits](https://dynamatic.epfl.ch/)
* [Stackifier algorithm](https://medium.com/leaningtech/solving-the-structured-control-flow-problem-once-and-for-all-5123117b1ee2) converts SSA back to cycles and conditions
* [DASS: Combining Dynamic and Static Scheduling in High-level Synthesis](https://www.researchgate.net/publication/350081168_DASS_Combining_Dynamic_and_Static_Scheduling_in_High-level_Synthesis)
* [Enabling adaptive loop pipelining in high-level synthesis](https://doi.org/10.1109/ACSSC.2017.8335152)
* SODA (Chi, ICCAD 18)
* Darkroom (Hegarty, TOG 14)
* Aetherling (Durst, PLDI 20)
* Polymage-FPGA (Chugh, PACT 16)
* Rigel (Hegarty, TOG 16)
* Halide-HLS (Pu, TACO 17)
* [Hipacc-FPGA (Reiche, CODES + ISS 14)](https://github.com/hipacc/hipacc-fpga)
* [Clokwork (Huff, FCCM 21)](https://github.com/dillonhuff/clockwork)

## Timing database generator scripts

* [Light-HLS](https://github.com/zslwyuan/Light-HLS/blob/master/HLS_Lib_Generator/LibGen.py)
