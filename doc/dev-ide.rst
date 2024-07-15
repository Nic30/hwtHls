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

* After update of LLVM, Eclipse CDT C++ code indexer commonly breaks and Index "Rebuild" or "Freshen All Files"
  will end up successfully but the index is still out of date.
  This can be solved by manual delete of CDT analysis cache

.. code-block::
  rm workspace/.metadata/.plugins/org.eclipse.cdt.core/llvm.*.pdom\
     workspace/.metadata/.plugins/org.eclipse.cdt.core/hwtHls.*.pdom

* Eclipse CDT does not recognize some STL containers like unordered_set and unordered_map.
  To fix that it is necessary to define __cplusplus at least to 202002L
  Project Properties --> C/C++ General --> Paths and Symbols --> Symbols --> GNU C++
  Make sure that the value corresponds to language version defined in meson.build
  https://stackoverflow.com/questions/17131744/eclipse-cdt-indexer-does-not-know-c11-containers
  https://gcc.gnu.org/onlinedocs/cpp/Standard-Predefined-Macros.html

* Worst problems for CDT usually happen in x86 backend generated files, which are not required for hwtHls at all.
  So after analysis nearly all types should be inferred correctly and code advisor should work as expected.
* Expected debugger spin-up time until first breakpoint:
  Debug build of LLVM + Debug build of hwtHls = 70s
  Release build of LLVM + Debug build of hwtHls = 2s
