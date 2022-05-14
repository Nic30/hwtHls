Readme for developers of this library
=====================================

.. README-dev:

List of useful tips for debug and explanation of related internal structures.

Setup of C/C++ source code indexer for LLVM
-------------------------------------------

* LLVM is large project and out-of-the box setting of indexers in IDEs do not work
  (Every line related to LLVM shows unresolved error)

* For eclipse you must:
  * Increase memory for Java VM in eclipse.ini `-Xms2048m -Xmx8192m`
  * In Window/ Preferences/ C/C++/ Indexer you must set
    * Skip files largetr than: 128
    * Skip included files largetr than: 256
    * Limit realtive to the maximum heap size: 75 %
    * Absolute limit: 6000 MB
 
 

Debug build
===========

* Default build and install (from locally downloaded repo)

.. code-block:: bash

	pip3 install .
	meson build .
	ninja -C build
	cd hwtHls/ssa/llvm/ && ln -s ../../build/hwtHls/ssa/llvm/*.so
	# you must link the c++ library file in order to find it from python using "import"
	# this is required becase we are not installing the library but using repo directly as a python package 

* use `LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libSegFault.so` to get better segfault reports
  libSegFault is a part of glibc but it may have a different location on your machine
* https://stackoverflow.com/questions/54273632/llvm-linking-commandline-error-option-help-list-registered-more-than-once-l

Doc generator
-------------

* https://devblogs.microsoft.com/cppblog/clear-functional-c-documentation-with-sphinx-breathe-doxygen-cmake/

How to debug C++ in Python module?
----------------------------------

Use GDB on Python binary (/usr/bin/python3 or your venv/bin/python), append local dependencies to PYTHONPATH if not installed, specify script to execute (e.g.  `-m tests.all`)
In eclipse you can append ${workspace_project_locations} in environment tab in Debug Configurations properties to add everything at once.

Using local llvm build
----------------------

* https://www.linuxfromscratch.org/blfs/view/cvs/general/llvm.html
.. code-block:: bash

    apt install cmake ninja-build
	git clone https://github.com/llvm/llvm-project.git
	mkdir llvm_install
	cd llvm-project/llvm
	git checkout llvmorg-14.0.0
	mkdir build
	cd build
	cmake -G Ninja  .. -DCMAKE_BUILD_TYPE=Debug\
		-DLLVM_ENABLE_ASSERTIONS=ON\
		-DLLVM_OPTIMIZED_TABLEGEN=ON\
		-DLLVM_LINK_LLVM_DYLIB=ON\
		-DLLVM_ENABLE_RTTI=ON\
		-DCMAKE_INSTALL_PREFIX=$PWD/../../../llvm_install

	ninja # Note that the llvm build is memory hungry you may require to limit number of threads using -j1 where 1 represents number of threads.
	ninja install # (installs only to a directory previously specified using -DCMAKE_INSTALL_PREFIX)

* `LLVM_OPTIMIZED_TABLEGEN` to speedup the build
* `LLVM_LINK_LLVM_DYLIB` to generate libLLVM.so because meson depnedency is using it
* `LLVM_ENABLE_RTTI` to provide typeinfo

.. code-block:: bash

	cd hwtHls
	meson build/ --native-file utils/custom-llvm.ini

* When executing you need to use `LD_PRELOAD=$PWD/../llvm_install/lib/libLLVM.so` in order to actually use the custom build otherwise a system wide installed library will be used.
* Note that once executed it takes >4m for gdb-11.1 and requires >16G of RAM to start because of the LLVM debug meta size.
* It is highly recommended to index llvm libraries in order to lower gdb start time `gdb-add-index llvm_install/lib/libLLVM-14.so`

Using -dbg package of llvm
--------------------------
* This is more simple and faster than build local llvm
* https://wiki.ubuntu.com/Debug%20Symbol%20Packages

LLVM/clang
==========


LLVM environment setup
----------------------

docker

.. code-block:: bash
	
	docker pull silkeh/clang
	mkdir clang_test
	docker run -it -v $PWD/clang_test:/clang_test --name clang_i silkeh/clang /bin/bash


Translation to LLVM IR
----------------------

.. code-block:: bash

	clang -S -emit-llvm main.c # produces  LLVM IR main.ll
	clang -cc1 main.c -emit-llvm # produces  LLVM IR main.ll
	llc main.ll # produces assembly main.s
	llc -mtriple=mips-linux-gnu -stop-after=finalize-isel < sum.ll


https://releases.llvm.org/14.0.0/docs/LangRef.html

* Dump all used passes `clang -mllvm -debug-pass=Arguments main.c`

.. code-block:: bash

	opt -dot-cfg test.s
	# and now by using xdot for instance we can see the control flow graph of the program
	xdot cfg.main.dot

TargetMachine
-------------

* https://llvm.org/docs/WritingAnLLVMBackend.html
* https://wiki.aalto.fi/display/t1065450/LLVM+TableGen
`llvm-tblgen insns.td -print-records`
* https://blog.llvm.org/2012/11/life-of-instruction-in-llvm.html
* llvm codegen types llvm/include/llvm/CodeGen/ValueTypes.td
* example LLVM backends
  * https://github.com/frasercrmck/llvm-leg/tree/master/lib/Target/LEG
* Other projects with FPGA/Verilog/FPGA LLVM backend
  * https://github.com/cpc/tce/tree/master/tce/src/applibs/LLVMBackend/plugin

Interpret
-------------


.. code-block:: bash

	clang -emit-llvm -c main.c -o main.bc
	lli -stats main.bc

Transformation passes
---------------------

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

LLVM tutorials
--------------
* https://lowlevelbits.org/how-to-learn-compilers-llvm-edition/
