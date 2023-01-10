
# get all modules in whole library
hwtHls_modules = run_command(py3, '../utils/rec_glob.py', '.', 'module', check:true)\
    .stdout().strip().split('\n')

# install all python sources
foreach submodule_path: hwtHls_modules
    submodule_sources = run_command(py3, '../utils/rec_glob.py', submodule_path, '*.py', check:true)\
        .stdout().strip().split('\n')

    # mark sources of a single module for an installation
    py3.install_sources(
        submodule_sources,
        pure: false, # Will be installed next to binaries
        subdir: 'hwtHls' / submodule_path,  # Folder relative to site-packages to install to
    )
endforeach

subdir('llvm')
subdir('netlist/abc')
