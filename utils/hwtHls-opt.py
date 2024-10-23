#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import importlib
import importlib.util
import sys
from pathlib import Path

workspace = Path(__file__).parent.parent / "workspace"


sys.path.extend(workspace + p for p in [
    'hwtHls',
    'hwtHlsGdb',
    'hwtGraph',
    'ipCorePackager',
    'hwtSimApi',
    'sphinx-hwt',
    'hwt',
    'pyMathBitPrecise',
    'pyDigitalWaveTools',
    'hwtBuildsystem',
    'hwtLib',
    'hdlConvertorAst'])

__doc__ = """
This script is similar thing to llvm opt program. It runs the optimization pipeline on input code.
This script was made as a compatibility layer for llvm based tools (in this case code-explorer https://github.com/compiler-explorer/compiler-explorer) 

This script takes python code as an input and tries to search function "main" then it executes it and expect that the output is HwModule instance.
This instance is then compiled using to_rtl_str and the intermediate during pipeline may be made visible using print-before-all and by other common llvm options. 
"""

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--version', action='store_true')
parser.add_argument('-o', type=str, help="Specify the output filename.",)
parser.add_argument('-S', action='store_true', help="Write output in LLVM intermediate language (instead of bitcode).")
parser.add_argument('filename', nargs='?', help='If filename is omitted from the command line or is "-", opt reads its input from standard input.'
                        '  Inputs can be in either the LLVM assembly language format (.ll) or the LLVM bitcode format (.bc).')
parser.add_argument('-print-after-all', action='store_true')
parser.add_argument('-print-before-all', action='store_true')
parser.add_argument('-print-module-scope', action='store_true')
parser.add_argument('-fsave-optimization-record', action='store_true')


def runCompilation(args):
    from hwt.hwModule import HwModule
    from hwt.synth import to_rtl_str
    from hwtHls.platform.xilinx.artix7 import Artix7Medium
    from hwtHls.platform.platform import HlsDebugBundle

    moduleName = "test"
    spec = importlib.util.spec_from_file_location(moduleName, args.filename)
    if spec is None:
        raise AssertionError("Input file is not a valid python file", [c for c in args.filename])
    pyModule = importlib.util.module_from_spec(spec)
    sys.modules[moduleName] = pyModule
    spec.loader.exec_module(pyModule)
    hwModule = pyModule.main()

    assert isinstance(hwModule, HwModule), ("main() must return instance of HwModule", hwModule)
    targetPlatform = Artix7Medium(debugFilter=HlsDebugBundle.ALL_RELIABLE)
    if args.print_before_all:
        targetPlatform._llvmCliArgs.append(("print-before-all", 0, "", "true"))

    if args.print_after_all:
        targetPlatform._llvmCliArgs.append(("print-after-all", 0, "", "true"))

    if args.fsave_optimization_record:
        p = Path(args.o)
        targetPlatform._llvmCliArgs.append(("pass-remarks-output", 0, "", (p.parent / (p.stem +".opt.yaml")).as_posix()))
        

    res = to_rtl_str(hwModule, target_platform=targetPlatform)
    if args.o:
        with open(args.o, "w") as outFile:
            outFile.write(res)
    else:
        print(res) 

args = parser.parse_args()

if args.version:
    print("""\
Ubuntu LLVM version 18.1.3
  Optimized build.
  Default target: x86_64-pc-linux-gnu
  Host CPU: skylake
    """)
else:
    if not args.S:
        raise NotImplementedError("-S required")
    runCompilation(args)
