# hwtHls

[![CircleCI](https://circleci.com/gh/Nic30/hwtHls/tree/master.svg?style=svg)](https://circleci.com/gh/Nic30/hwtHls/tree/master)[![PyPI version](https://badge.fury.io/py/hwtHls.svg)](http://badge.fury.io/py/hwtHls)[![Coverage Status](https://coveralls.io/repos/github/Nic30/hwtHls/badge.svg?branch=master)](https://coveralls.io/github/Nic30/hwtHls?branch=master)


A library for an automatic translation of algorithmic code to a hardware realization
based on [hwt](https://github.com/Nic30/hwt) (hwt is a library for circuit construction) and
[LLVM](https://llvm.org/) (a compiler infrastructure).

![hwtHls_overview](./doc/_static/hwtHls_overview.png)

This library is a tool which lets you write code transformations for fast and efficient hardware architecture generators.

* Modular compiler build as a sequence of powerful optimization passes for LLVM IR/MIR/ABC
* Fully compatible with LLVM/HWT/ABC/Z3
* Powerful debugging features on every level
* Target specification for common FPGAs with possiblity for user to specify any custom target


![hwtHls_overview](./doc/_static/hwtHls_overview_debug.png)

A typical project where you would use this project is a hash table in HBM2 memory with cache.
* HBM2 may have 32 AXI4 ports, you need to use eta 64*32 transactions at once to saturate memory throughput.
* All transactions must assert consistency.
* Due to timing, everything needs to be pipelined and the hash table must support multiple operations in a single clock.

* How you write it?
  * Construct a hdl wrapper and declare control registers (using HWT, e.g. for AXI4-lite, 0.5MH)
  * Pick a hash table alg., e.g. robing hood hashing, write naive variant with 1 memory port (represented as an array, 0.5MH)
  * Test python code (0.5MH)
  * Translate it to a single pipeline (automatically, with disastrous performance, 0MH)
  * Add pragma to merge loops to achieve II=1 (semi manually, 0.2MH)
  * Add pragma to use 64 AXI4 threads, duplicate it 32x, construct LSU (automatically, 1MH)
  * Use HWT UVM-like test environment to build sim enviroment, (30MH)
  * If everything was automatically translated, the functionality is already formaly verified
    but things like deadlock from external cause may still happen. 
  * Write a AXI4 cache (10MH, or use existing e.g. from hwtLib)
  * Tune up size of AXI out-of-order windows, LSU, write forward history length
    and cache for your app and synthesis in vendor tool and frequency (40MH, semi manually)


### Current state

* This library is in an alpha phase.
* You can try it online at [![Binder](https://mybinder.org/badge_logo.svg)](https://notebooks.gesis.org/binder/v2/gh/Nic30/hwtHls/HEAD) (From jupyterlab you can also run examples in tests.)

* Features
  * frontends:
    * Python bytecode
	    * Bytecode of any Python can be translated to hardware
	       * Bytecode is symbolically executed and the code which does not depend on HW evaluated value is executed immediately.
	         This means that the python runs as a preprocessors and it generates HW code.
	       * As this part translates bytecode to SSA, the input syntax does not matter.
	
	    * No exception handling in HW code, function calls must be explicitly marked to be translated to HW otherwise calls are evaluated compile time
	    * Only static typing for HW code
	    * (Meant to be used for simple things, for the rest you should construct AST or SSA directly.)
    * hwtHls AST (Python statement-like objects)

  * Kernel superoptimization framewors:
    * Hierarchical, backtracking list scheduler with operation chaining and retiming
    * FSM/dataflow fine-graded architecture extraction with different optimization strategies
     (extraction strategy specified as a sequence of transformations)
    * Polyhedral, affine, unroll and other LLVM asisted transformations
    * On demand speculations/out-of-order execution:
        * next iteration speculation before break
        * speculativele execution of multiple loop bodies
        * after loop code speculative execution before break
        * cascading of speculation
        * speculative IO access using LSU (for memory mapped IO) or buffers with confirmation (for IO streams)
        * memory access speculation and distributed locks
    * ArchElement framework for multithread optimizations.
	* Target architecture aware (any Xilinx, Intel and others after benchmark)

  * Support for any stream IO protocol 
    (= handshake and all its degenerated variants = any single channel interface)
    * arbitrary number of IO operations for any scheduling type
    * support for side channels, virtual channels, multiple packets per clock
      (e.g. xgmii)
    * explicit blocking, explicit dropping, explicit skipping
      (e.g. conditional read/write of data, read without consummer)
    * Packet FMS inference from read/write of ADT, SoF, EoF
	  * Program may contain arbitrary number of packet IO with arbitrary access.
      * Incremental packet parsing/deparsing, read/write chunk:
        * may not be alligned to word
        * may cause under/overflow
        * may be required to be end of stream or not
      * Optional check of input packet format
        (or synchronized by the input packet format which significantly reduce circuit complexity)

* Not done yet:
  * Complex operation reducing (DSP)
  * All platforms


## How it works?

* see doc in `hwtHls/__init__.py`
* for tutorial see examples and tests


### Installation

Linux (Ubuntu 24.04):
```
apt install build-essential python3-dev python3-pip llvm-18-dev
pip3 install -r https://raw.githubusercontent.com/Nic30/hwtHls/master/doc/requirements.txt # [optional]
# if you do not run previous command you will install dependencies from pip which may outdated
pip3 install git+https://github.com/Nic30/hwtHls.git # install this library from git
```
For python3.11+ it is recommended to use virtualenv to separate local python package installation from the system.
```
apt install python3-venv
python3 -m venv venv # create a venv directory where local instalation of python will be placed
source venv/bin/activate # modifies current shell to use previously generate python environment
```


## Related open-source
* :skull: [ahaHLS](https://github.com/dillonhuff/ahaHLS) - 2018-2019, A Basic High Level Synthesis System Using LLVM
* :skull: [augh](http://tima.imag.fr/sls/research-projects/augh/) - c->verilog, DSP support
* :skull: [balsa](https://apt.cs.manchester.ac.uk/projects/tools/balsa/) 2003-2010, Async circuit synthesis
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
* :skull: [Trident](https://sourceforge.net/projects/trident/) - 2006, java/C++/LLVM
* :skull: [FPGA C Compiler](https://sourceforge.net/projects/fpgac/) - 2005-2006, trivial 1:1 c->vhdl
* :skull: [hpiasg](https://github.com/hpiasg) - , set of tools for asynchronous and handshake circuit synthesis
* :skull: [LeFlow](https://github.com/danielholanda/LeFlow) - 2018-2018, TensorFlow -> XLA -> LegUp
* :skull: [orcc/Open RVC-CAL Compiler](https://github.com/orcc/orcc) - 2011-2015, dataflow compiler
* :skull: [xronos](https://github.com/endrix/xronos) [git2](hhttps://github.com/orcc/xronos) - 2012-2016, java, simple HLS for orcc
* [abc](https://people.eecs.berkeley.edu/~alanmi/abc/) <2008-?, A System for Sequential Synthesis and Verification
* [ahir](https://github.com/madhavPdesai/ahir) - LLVM, llvm bytecode->vhdl
* [AutoBridge](https://autosa.readthedocs.io/en/latest/tutorials/auto_bridge.html) - Python, floorplaning/pipelining tool for Vitis HLS
* [AutoSA](https://github.com/UCLA-VAST/AutoSA) - C++, Polyhedral-Based Systolic Array Compiler
* [binaryen](https://github.com/WebAssembly/binaryen) - , C++, WebAssembly compiler (implements some similar optimization passes)
* [blarney](https://github.com/blarney-lang/blarney)
* [calyx](https://github.com/cucapra/calyx) - , Rust - compiler infrastructure with custom lang focused on ML accelerators
* [CirC](https://github.com/circify/circ) - Rust - compiler infrastructure for HLS
* [circt-hls](https://github.com/circt-hls/circt-hls) - C++/LLVM/Python, set of hls libraries for circt
* [clash-compiler](https://github.com/clash-lang/clash-compiler)
* [CBMC-GC-2](https://gitlab.com/securityengineering/CBMC-GC-2) - MPC from ANSI-C
* [coreir](https://github.com/rdaly525/coreir) - 2016-?, LLVM HW compiler
* [DASS](https://github.com/JianyiCheng/DSS) - combination of dynamic and static scheduling
* [domino-compiler](https://github.com/packet-transactions/domino-compiler) 2016 -> C++, c like packet processing language and compiler
* [dynamatic](https://github.com/EPFL-LAP/dynamatic) - , C++/LLVM-MLIR, HLS with dynamic scheduling, MLIR handshake
* [DPC++](https://github.com/intel/llvm/tree/sycl) - C++/LLVM,
* [DuroHLS](https://github.com/corelab-src/DuroHLS-opt) [CorelabVerilog](https://github.com/corelab-src/CorelabVerilog) - C++/LLVM, set of hls passes
* [dynamatic](https://github.com/lana555/dynamatic) - , C++/LLVM - set of LLVM passes for dynamically scheduled HLS
* [FloPoCo](https://gitlab.com/flopoco/flopoco) - C++, arithmetic core generator
* [futil](https://github.com/cucapra/futil) - 2020-?, custom lang.
* [gemmini](https://github.com/ucb-bar/gemmini) - scala, systolic array generator
* [Hastlayer](https://github.com/Lombiq/Hastlayer-SDK) - 2012-2019, C# -> HW
* [heterocl](https://awesomeopensource.com/project/cornell-zhang/heterocl)
* [hls4ml](https://github.com/vloncar/hls4ml)
* [HyCC](https://github.com/stskeeps/HyCC) - 2018, hybrid MPC from ANSI-C
* [ICSC](https://github.com/intel/systemc-compiler) - C++/LLVM, systemC compiler
* [Light-HLS](https://github.com/zslwyuan/Light-HLS) -, C++/LLVM, experimental HLS framework
* [mockturtle](https://github.com/lsils/mockturtle) - C++, logic network lib. with project similar to HLS
* [mlir-aie](https://github.com/Xilinx/mlir-aie) - C++/LLVM/MLIR, compiler infrastructure for Xilinx Vesal AIE
* [mlir-air](https://github.com/Xilinx/mlir-air) - C++/LLVM/MLIR, compiler infrastructure for Xilinx AIR
* [orcc](https://github.com/orcc/orcc) - C++/LLVM, Open RVC-CAL Compiler hw/sw dataflow and img processing focused
* [PandA-bambu](http://panda.dei.polimi.it/?page_id=31) - 2003-?, GCC based c->verilog
* [phism](https://github.com/kumasento/phism) - Python/C++/LLVM, Polyhedral High-Level Synthesis in MLIR
* [PipelineC](https://github.com/JulianKemmerer/PipelineC) - 2018, Python, c -> hdl for a limited subset of c
* [pluto](https://github.com/bondhugula/pluto) -  An automatic polyhedral parallelizer and locality optimizer
* [ROCCC](https://github.com/nxt4hll/roccc-2.0), http://roccc.cs.ucr.edu/ - 2009-2013, C++/LLVM/suif c -> vhdl
* [ScaleHLS](https://github.com/hanchenye/scalehls), [ScaleHLS-HIDA](https://github.com/UIUC-ChenLab/ScaleHLS-HIDA) - C++/LLVM, MLIR based HLS compiler, ML focused
* [Slice](https://github.com/sylefeb/Silice)
* [spatial](https://github.com/stanford-ppl/spatial)  - , scala
* [TCE](https://github.com/cpc/tce)- C++/LLVM, environment for development of application specific processors
* [tiramisu](https://github.com/Tiramisu-Compiler/tiramisu) - 2016-?, C++, A polyhedral compiler
* [Tydi](https://github.com/abs-tudelft/tydi) - Rust, specification for complex data structures over hardware streams
* [UCLA-VAST/TAPA](https://github.com/UCLA-VAST/tapa) - C++, HLS tool build on the top of VivadoHLS with explicit parallelism
* [utwente-fmt](https://github.com/utwente-fmt) - abstract hls, verification libraries
* [Xilinx/Vitis HLS](https://github.com/Xilinx/HLS) - C++/LLVM, partially opensource
* [xls](https://github.com/google/xls) - 2020-?, C++ HLS compiler with JIT
* [slothy](https://github.com/slothy-optimizer/slothy) - Python, Assembly optimizer
* [souper](https://github.com/google/souper) - C++/LLVM, superoptimizer for LLVM IR based on SMT solver
* [llvm-superasm](https://github.com/sjoerdmeijer/llvm-superasm/tree/main/llvm/tools/llvm-superasm) - C++/LLVM, assembly superoptimizer based on SMT solver
* [noelle](https://github.com/arcana-lab/noelle) - C++/LLVM, library of LLVM analyses and transformations


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
* https://jianyicheng.github.io/

## Timing database generator scripts

* [Light-HLS](https://github.com/zslwyuan/Light-HLS/blob/master/HLS_Lib_Generator/LibGen.py)
