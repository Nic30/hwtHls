"""
This module contains a LLVM binding and definition of a custom FPGA like LLVM target machine.
There are several custom transformations which are mainly focused on bit-width reduction and dependency removal. 

The GenFpga target is defined in hwtHls/llvm/targets/ and it tries to obey common LLVM target naming scheme and file hierarchy.

.. image:: _static/hwtHls_llvm_backend.png


The target is used for several things:

* It provides common informations about target (like memory layout, pointer size, instruction costs, ...) for all things in LLVM.

* It specifies instruction set (GenericFpgaInstrInfo.td) and how to generate it from LLVM SSA IR
  (genericFpgaTargetPassConfig.cpp, GenericFpgaCombine.td).
  The translation is an iterative process (described in mentioned file).
  The target itself does use LLVM GlobalISel framework for instruction selection.

The target definition is not fully integrated to LLVM target enum because it uses a non modified distribution of LLVM which can be
compiled in advance and most importantly, so this project can use LLVM pre-compiled libraries from Linux repositories.
This significantly reduces installation time and compilation RAM/storage requirements which is important for CI.
"""