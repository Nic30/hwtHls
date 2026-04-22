
py3.extension_module(
    'techmap',
    ['pybind/techmapPybind11.cpp',
     'hlsNetlist.cpp',
	 'hlsNetNodeScheduling.cpp',
     'flowmap_yosys.cpp',
     'flowmap_yosys_areaOpt.cpp',
     'schedulingAlap.cpp',
     'schedulingLutAlap.cpp',
     ],
    dependencies : [py3_dep, pybind11_dep],
    install: true,
    cpp_args: [],
    subdir: 'hwtHls/netlist/techmap/',
    include_directories : hwtHls_inc,
)