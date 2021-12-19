# Normal build and install (from locally downloaded repo)

`pip3 install .`


# Debug build

`meson build .`
`ninja -C build`
`cd hwtHls/ssa/llvm/ && ln -s ../../build/hwtHls/ssa/llvm/*.so`

# LLVM/clang

## LLVM environment setup
docker
`docker pull silkeh/clang`
`mkdir clang_test`
`docker run -it -v $PWD/clang_test:/clang_test --name clang_i silkeh/clang /bin/bash`

## Translation to LLVM IR
`clang -S -emit-llvm main.c` produces  LLVM IR `main.ll`
`clang -cc1 main.c -emit-llvm` produces  LLVM IR `main.ll`
`llc main.ll` produces assembly `main.s`

https://releases.llvm.org/11.0.0/docs/LangRef.html

Dump all used passes
`clang -mllvm -debug-pass=Arguments main.c`
```
opt -dot-cfg test.s
#and now by using xdot for instance we can see the control flow graph of the program
xdot cfg.main.dot
```

## TargetMachine
https://llvm.org/docs/WritingAnLLVMBackend.html
https://wiki.aalto.fi/display/t1065450/LLVM+TableGen
`llvm-tblgen insns.td -print-records`

## Interpret
`clang -emit-llvm -c main.c -o main.bc`
`lli -stats main.bc`

## Transformation passes
```
Pass Arguments:  -tti -targetlibinfo -ee-instrument
Pass Arguments:  -tti -targetlibinfo -assumption-cache-tracker -profile-summary-info -annotation2metadata -forceattrs -basiccg -always-inline -barrier -annotation-remarks
Pass Arguments:  -tti -targetlibinfo -targetpassconfig -machinemoduleinfo -collector-metadata -assumption-cache-tracker -profile-summary-info -machine-branch-prob -pre-isel-intrinsic-lowering -atomic-expand -lower-amx-type -gc-lowering -shadow-stack-gc-lowering -lower-constant-intrinsics -unreachableblockelim -post-inline-ee-instrument -scalarize-masked-mem-intrin -expand-reductions -indirectbr-expand -rewrite-symbols -dwarfehprepare -safe-stack -stack-protector -amdgpu-isel -finalize-isel -localstackalloc -x86-slh -machinedomtree -x86-flags-copy-lowering -phi-node-elimination -twoaddressinstruction -regallocfast -edge-bundles -x86-codegen -fixup-statepoint-caller-saved -lazy-machine-block-freq -machine-opt-remark-emitter -prologepilog -postrapseudos -x86-pseudo -gc-analysis -fentry-insert -xray-instrumentation -patchable-function -x86-evex-to-vex-compress -funclet-layout -stackmap-liveness -livedebugvalues -x86-seses -cfi-instr-inserter -x86-lvi-ret -lazy-machine-block-freq -machine-opt-remark-emitter
```

https://www.llvm.org/docs/Passes.html#introduction
https://www.llvm.org/docs/LoopTerminology.html
Llvm pass execution (`-disable-llvm-passes` is required otherwise `optnone` attribute is added and nothing happens during `opt`)
`clang -cc1 -Os -disable-llvm-passes -emit-llvm main.c -o - | opt -S -mem2reg`


## In IR debugging metainformations

* https://wiki.aalto.fi/display/t1065450/LLVM+DebugInfo


## Other LLVM bindings

* https://github.com/numba/llvmlite