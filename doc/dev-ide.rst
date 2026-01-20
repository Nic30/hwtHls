Eclipse
-------
* LLVM code indexing is likely to take 0.5 hour. And indexer will need more memory than default settings allows.

.. code-block::
  Skip files larger than: 128 MB
  Skip included files larger than: 256 MB
  
  Limit relative to maximum heap size: 75%
  Absolute limit: 6000 MB

In eclipse.ini allow more memory for JVM by appending

.. code-block::

  -Xms4G
  -Xmx16G

* After update of LLVM, pybind11, Eclipse CDT C++ code indexer usually breaks and Index "Rebuild" or "Freshen All Files"
  will end up successfully but the index is still out of date.
  This can be solved by manual delete of CDT analysis cache

  .. code-block::
    rm workspace/.metadata/.plugins/org.eclipse.cdt.core/llvm.*.pdom\
       workspace/.metadata/.plugins/org.eclipse.cdt.core/pybind11.*.pdom\
       workspace/.metadata/.plugins/org.eclipse.cdt.core/hwtHls.*.pdom
       

* Eclipse CDT can not find pybind11 files
  To fix that add include paths
  Project Properties --> C/C++ General --> Paths and Symbols --> Includes
  /usr/local/lib/python3.13
  /usr/local/lib/python3.13/dist-packages/pybind11/include
  (update name of your python)

* Eclipse CDT does not recognize some STL containers like unordered_set and unordered_map.
  --Deprecated:
  To fix that it is necessary to define __cplusplus at least to 202002L (and for std::generator you need at least 202302L)
  Project Properties --> C/C++ General --> Paths and Symbols --> Symbols --> GNU C++ 
  Make sure that the value corresponds to language version defined in meson.build
  --
  https://stackoverflow.com/questions/17131744/eclipse-cdt-indexer-does-not-know-c11-containers
  https://gcc.gnu.org/onlinedocs/cpp/Standard-Predefined-Macros.html
  https://github.com/eclipse-cdt/cdt/issues/438
  --Deprecated:
  Alternatively you can add -std=c++23 flag to builtin compiler settings
  Window -> Preferences -> C/C++ -> Build -> Settings -> CDT GCC Built-in Compiler settings
  --
  You also need to switch to LSP based editor in eclipse 2025-12 called "New C/C++ editing experience"
  Window -> Preferences -> C/C++ -> Editor (LSP) -> Set C/C++ Editor (LSP) as default
  And for that you need to install clang and clangd.


* Worst problems for CDT usually happen in x86 backend generated files, which are not required for hwtHls at all.
  So after analysis nearly all types should be inferred correctly and code advisor should work as expected.
* Expected debugger spin-up time until first breakpoint:
  Debug build of LLVM + Debug build of hwtHls = 70s
  Release build of LLVM + Debug build of hwtHls = 2s

