#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os

from coverage.cmdline import main as coverage_main
"""
Skipt which generates HTML covertage report in $REPO/htmlcov folder.
"""

if __name__ == "__main__":
    os.chdir(os.path.join(os.path.dirname(__file__), ".."))
    coverage_main(["run", "--source", "hwtHls", "-m", "tests.all", "--singlethread"])
    coverage_main(["report", "-m"])
    coverage_main(["html"])
    
