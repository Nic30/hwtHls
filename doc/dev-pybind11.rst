
Binding stl
* https://pybind11.readthedocs.io/en/stable/advanced/cast/stl.html
  * :attention: the  PYBIND11_MAKE_OPAQUE(std::vector<int>) must be included or defined in every file which is using vector<int>
    but py::bind_vector<std::vector<int>>(m, "VectorInt"); must be only in a single file

* valgrind + python3
  * https://github.com/python/cpython/blob/main/Misc/README.valgrind 
  * https://github.com/python/cpython/blob/main/Misc/valgrind-python.supp