LLVM profiling:
* https://clang.llvm.org/docs/analyzer/developer-docs/PerformanceInvestigation.html

To collect:
.. code-block:: python
	import cProfile
    pr = cProfile.Profile()
    pr.enable()
    # ...
    pr.disable()
    pr.dump_stats('profile.prof')

To display:
.. code-block:: bash
	pyprof2calltree -i profile.prof -k