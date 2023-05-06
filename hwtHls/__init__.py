"""
hwtHls
======

hwtHls is a library which provides a High Level Synthesis (HLS) compiler egine for hwt Hardware Construction Language (HCL).

* :mod:`hwtHls.frontend`: Converts the input code into SSA objects defined in `hwtHls.ssa`.
  (The code is loaded using `HlsScope` object in hwt component (`Unit` class),
   the constraints and interface types are specified as hwt objects.)

* There are several optimization SSA passes. Full list of optimizations is specified in HlsPlatform.
  On demand several some instructions in SSA must be lowered before conversion to LLVM SSA.

* LLVM SSA is then optimized (Full list of optimizations is specified in hwtHls/llvm/llvmCompilationBundle.cpp)

* Optimized LLVM SSA is then translated to LLVM Machine-level IR MIR. (Full list of transformations can be seen in hwtHls/llvm/targets/hwtFpgaTargetPassConfig.cpp)
  This is required to perform register allocation and resoruce sharing type of optimizations.

* LLVM MIR is then converted to a `hwtHls.netlist` and control and data channel optimizations are performed.
  This process ends with netlists nodes scheduled to a specif times.

* Nodes in scheduled netlist are then divided into architectural elements (ArchElement instances) and :mod:`hwtHls.architecture`.
  On this level exact realization of every node is resolved as well as each buffer placement or IO.

* Final graph of ArchElement instances is then directly translated to is then translated to hwt netlist which handles all SystemVerilog/VHDL/simulator/verification related things.
"""
