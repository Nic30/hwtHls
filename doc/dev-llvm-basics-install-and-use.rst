LLVM basics, install and use
============================

LLVM/clang is useful when debugging something LLVM related which does not necessary dependent on this library.
There is also https://llvm.godbolt.org/ which has nice WEB UI. There is a discord server and https://discourse.llvm.org.
https://www.cs.cmu.edu/afs/cs/academic/class/15745-s13/public/lectures/L6-LLVM-Detail-1up.pdf

Installation linux
------------------
.. code-block:: bash
   apt install llvm-18-dev

Using local llvm build
----------------------

This is useful when debugging issues which are happening in LLVM code.

* https://www.linuxfromscratch.org/blfs/view/cvs/general/llvm.html
.. code-block:: bash

    apt install cmake ninja-build
	git clone https://github.com/llvm/llvm-project.git
	mkdir llvm_install
	cd llvm-project/llvm
	git checkout llvmorg-18.1.3 
	cmake -B build -DCMAKE_BUILD_TYPE=Debug -G Ninja\
	    -DLLVM_TARGETS_TO_BUILD=X86\
		-DLLVM_ENABLE_ASSERTIONS=ON\
		-DLLVM_OPTIMIZED_TABLEGEN=ON\
		-DLLVM_LINK_LLVM_DYLIB=ON\
		-DLLVM_ENABLE_RTTI=ON\
		-DLLVM_USE_SPLIT_DWARF=ON\
		-DCMAKE_INSTALL_PREFIX=$PWD/../../llvm_install
	ninja -C build # Note that the llvm build is memory hungry you may require to limit number of threads using -j1 where 1 represents number of threads.
	ninja -C build install # (installs only to a directory previously specified using -DCMAKE_INSTALL_PREFIX)

* `LLVM_TARGETS_TO_BUILD` note that we do not need any target as this library provides custom targets but we
  specify some because if left unspecified, all are build by default which takes space and time to build
* `LLVM_OPTIMIZED_TABLEGEN` to speedup the build
* `LLVM_LINK_LLVM_DYLIB` to generate libLLVM.so because meson depnedency is using it
* `LLVM_ENABLE_RTTI` to provide typeinfo to enable debugging with GDB
* `LLVM_USE_SPLIT_DWARF` to speedup GDB startup
* `CMAKE_INSTALL_PREFIX` is an absolute path to a directory of your choice

.. code-block:: bash

	cd hwtHls # cd to this project root directory
	meson setup build/ --native-file utils/custom-llvm.ini

* When executing you need to use `LD_PRELOAD=$PWD/../llvm_install/lib/libLLVM.so` in order to actually use the custom build otherwise a system wide installed library will be used.
* Note that once executed it takes >4m for gdb-11.1 and requires >16G of RAM to start because of the LLVM debug meta size.
  If you do not use debug build of LLVM you still will be able to debug c++ code in this project and gdb will start in <1s.
  But you wont be able to debug inside LLVM functions.
* It is highly recommended to index LLVM libraries in order to lower gdb start time `gdb-add-index llvm_install/lib/libLLVM-16.so`

Using -dbg package of llvm
--------------------------
* This is more simple and faster than build local llvm
* https://wiki.ubuntu.com/Debug%20Symbol%20Packages



LLVM environment setup
----------------------

You can use installed llvm as it is or you can use docker to separate all llvm related things from your os.

.. code-block:: bash

	docker pull silkeh/clang
	mkdir clang_test
	docker run -it -v $PWD/clang_test:/clang_test --name clang_i silkeh/clang /bin/bash


TargetMachine/MIR
-----------------

* https://llvm.org/devmtg/2017-10/slides/Braun-Welcome%20to%20the%20Back%20End.pdf
* https://llvm.org/docs/WritingAnLLVMBackend.html
* https://wiki.aalto.fi/display/t1065450/LLVM+TableGen
`llvm-tblgen insns.td -print-records`
* https://blog.llvm.org/2012/11/life-of-instruction-in-llvm.html
* llvm codegen types llvm/include/llvm/CodeGen/ValueTypes.td
* example LLVM backends
  * https://github.com/frasercrmck/llvm-leg/tree/master/lib/Target/LEG
* Other projects with FPGA/Verilog/FPGA LLVM backend
  * https://github.com/cpc/tce/tree/master/tce/src/applibs/LLVMBackend/plugin
* to get original MDNode for MachineInst see  NVPTXAsmPrinter::isLoopHeaderOfNoUnroll
* MIR registers does not need to have definition by any MachineOperand for example ProcessImplicitDefsPass
  removes all defining instructions for undef values. However each use MachineOperand must have IsUndef flag set.


Translation to LLVM IR
----------------------

.. code-block:: bash

	clang -S -emit-llvm -O0 -g -fno-discard-value-names main.c # produces  LLVM IR main.ll
	clang -cc1 main.c -emit-llvm # produces  LLVM IR main.ll
	llc main.ll # produces assembly main.s
	llc -mtriple=mips-linux-gnu -stop-after=finalize-isel < sum.ll


https://releases.llvm.org/15.0.0/docs/LangRef.html

* Dump all used passes `clang -mllvm -debug-pass=Arguments main.c`

.. code-block:: bash

	opt -dot-cfg test.s # there is also -view-cfg, -view-cfg-only
	# and now by using xdot for instance we can see the control flow graph of the program
	xdot cfg.main.dot

Interpret
---------

.. code-block:: bash

	clang -emit-llvm -c main.c -o main.bc
	lli -stats main.bc

Transformation passes
---------------------


.. code-block:: text
    opt --help-hidden # displays all options for every pass

.. code-block:: text
	opt --debug-pass=Structure < main.bc

	Pass Arguments:  -tti -targetlibinfo -ee-instrument
	Pass Arguments:  -tti -targetlibinfo -assumption-cache-tracker -profile-summary-info -annotation2metadata -forceattrs -basiccg -always-inline
	                      -barrier -annotation-remarks
	Pass Arguments:  -tti -targetlibinfo -targetpassconfig -machinemoduleinfo -collector-metadata -assumption-cache-tracker -profile-summary-info
	                      -machine-branch-prob -pre-isel-intrinsic-lowering -atomic-expand -lower-amx-type -gc-lowering -shadow-stack-gc-lowering
	                      -lower-constant-intrinsics -unreachableblockelim -post-inline-ee-instrument -scalarize-masked-mem-intrin -expand-reductions
	                      -indirectbr-expand -rewrite-symbols -dwarfehprepare -safe-stack -stack-protector -amdgpu-isel -finalize-isel -localstackalloc
	                      -x86-slh -machinedomtree -x86-flags-copy-lowering -phi-node-elimination -twoaddressinstruction -regallocfast -edge-bundles
	                      -x86-codegen -fixup-statepoint-caller-saved -lazy-machine-block-freq -machine-opt-remark-emitter -prologepilog -postrapseudos
	                      -x86-pseudo -gc-analysis -fentry-insert -xray-instrumentation -patchable-function -x86-evex-to-vex-compress -funclet-layout
	                      -stackmap-liveness -livedebugvalues -x86-seses -cfi-instr-inserter -x86-lvi-ret -lazy-machine-block-freq -machine-opt-remark-emitter


* https://www.llvm.org/docs/Passes.html#introduction
* https://www.llvm.org/docs/LoopTerminology.html
* https://blog.regehr.org/archives/1603
* https://compilergym.com/llvm/index.html
* Llvm pass execution (`-disable-llvm-passes` is required otherwise `optnone` attribute is added and nothing happens during `opt`)
`clang -cc1 -Os -disable-llvm-passes -emit-llvm main.c -o - | opt -S -mem2reg`

* exec multiple branches but store only on some selected: "if conversion". This transformation predicates instructions. See e.g. ARM as an example
* https://juejin.cn/column/6963554563173384200
* https://github.com/zslwyuan/LLVM-9.0-Learner-Tutorial
* https://llvm.org/docs/GlobalISel/GenericOpcode.html
* https://llvm.org/docs/CodeGenerator.html
* https://blog.regehr.org/archives/1603
* GlobalISel Combine rules https://groups.google.com/g/llvm-dev/c/kVwGJ2xs76w
* https://github.com/nael8r/How-To-Write-An-LLVM-Register-Allocator/blob/master/HowToWriteAnLLVMRegisterAllocator.rst
* https://www.cs.cornell.edu/courses/cs6120/2020fa/blog/pipeline-ii-analysis/

Dictionary
----------
* nuw no unsigned wrap
* nsw no signed wrap
* invoke - call with exception handling, InvokeInstr is a terminator CallBase is not


In IR debugging meta-information
--------------------------------

* https://wiki.aalto.fi/display/t1065450/LLVM+DebugInfo


Other LLVM bindings
-------------------

* https://github.com/numba/llvmlite

LLVM attributes and metadata
----------------------------

* https://blog.yossarian.net/2021/11/29/LLVM-internals-part-4-attributes-and-attribute-groups

LLVM alias analysis
-------------------

* https://sites.google.com/site/parallelizationforllvm/building-the-dependence-graph
* https://blog.tartanllama.xyz/llvm-alias-analysis/

LLVM tutorials
--------------
* https://lowlevelbits.org/how-to-learn-compilers-llvm-edition/

