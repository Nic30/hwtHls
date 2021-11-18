# Normal build and install (from locally downloaded repo)

`pip3 install .`


# Debug build

`meson build .`
`ninja -C build`
`cd hwtHls/llvm/ && ln -s ../../build/hwtHls/llvm/*.so`

