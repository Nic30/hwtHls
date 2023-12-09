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
    * Skip files larger than: 128 MB
    * Skip included files larger than: 256 MB
    * Limit realtive to the maximum heap size: 75 %
    * Absolute limit: 6000 MB


Meson
-----
References which may be useful when writing meson.build:
* https://mesonbuild.com
* https://github.com/ev-br/mc_lib/blob/master/mc_lib/meson.build
* https://mesonbuild.com/Python-module.html


Debug build
===========

* Default build and install (from locally downloaded repo)

.. code-block:: bash

	# make sure that you installed dependencies from pyproject.toml using pip3 install
	meson setup build
	# meson setup build -Db_profile=true # to build with profiling
	ninja -C build

	# you must link the c++ library file in order to find it from python using "import"
	# this is required becase we are not installing the library but using repo directly as a python package
	ln -s "../../$(ls build/hwtHls/llvm/*.so)" hwtHls/llvm/
	ln -s "../../../$(ls build/hwtHls/netlist/abc/abc*.so)" hwtHls/netlist/abc/
	ln -s "../../../../$(ls build/hwtHls/netlist/analysis/reachabilityCpp/*.so)"  hwtHls/netlist/analysis/reachabilityCpp/

* You can use `LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libSegFault.so` to get better segfault reports.
  libSegFault is a part of glibc but it may have a different location on your machine
* https://stackoverflow.com/questions/54273632/llvm-linking-commandline-error-option-help-list-registered-more-than-once-l

* You can enable debug messages for a specific pass programatically using

.. code-block:: cpp

	llvm::StringMap<llvm::cl::Option*> &Map = llvm::cl::getRegisteredOptions();
	Map["debug-only"]->addOccurrence(0, "", "early-ifcvt"); // early-ifcvt is a name of some pass to debug (attention, option available only in LLVM debug build)
	Map["print-before"]->addOccurrence(0, "", "early-ifcvt"); // you can use this to dump input to specified pass


Doc generator
-------------

* https://devblogs.microsoft.com/cppblog/clear-functional-c-documentation-with-sphinx-breathe-doxygen-cmake/

How to debug C++ in Python module?
----------------------------------

Use GDB on Python binary (/usr/bin/python3 or your venv/bin/python), append local dependencies to PYTHONPATH if not installed, specify script to execute (e.g.  `-m tests.all`)
In eclipse you can append ${workspace_project_locations} in environment tab in Debug Configurations properties to add everything at once.

Other
=====

gdbserver
---------
* https://github.com/bet4it/gdbserver

Python profiling
----------------
.. code-block:: bash
    apt install kcachegrind # install gui to show profiling data
    pip3 install pyprof2calltree # install utility script which converts from pyprof

.. code-block:: python
    import cProfile
    pr = cProfile.Profile()
    pr.enable()
    # somethig to profile
    pr.disable()
    pr.dump_stats('profile.prof')

.. code-block:: bash
    pyprof2calltree -i profile.prof -k


Profiling C++ with perf
-----------------------
* Note that you do not need this, you can use -Db_profile=true meson option as described before

.. code-block:: bash
   # install perf
   apt install linux-tools-common linux-tools-generic
   
