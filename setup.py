#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

print("This project uses PEP517 use `pip install .` etc insead of executing setup.py")

#from setuptools import setup, find_packages
#from Cython.Build import cythonize
##import distutils.command.build_ext
#from distutils.core import Extension
#from os import path
##import sys
##import os
##import shutil
##from glob import glob
## import re
##from subprocess import check_call
##from pathlib import Path
##from distutils.extension import Extension
#
#this_directory = path.abspath(path.dirname(__file__))
#with open(path.join(this_directory, 'README.md'), encoding='utf-8') as f:
#    long_description = f.read()
#
#ext = Extension(name="hwtHls.llvm.hello", sources=["hwtHls/llvm/hello.pyx"]),
#
#
##class build_ext(distutils.command.build_ext.build_ext):
##
##    def run(self):
##        #super(build_ext, self).run()
##        # from mesonbuild.mesonmain import main as mesonbuild_main
##        # orig_argv = sys.argv
##        # sys.argv = [re.sub(r'(-script\.pyw|\.exe)?$', '', sys.executable), "build", "."]
##        # call exit(0) if directory already configured
##        check_call([sys.executable, "-m", "mesonbuild.mesonmain", "build", "."])
##        check_call(["ninja", "-C", "build"])
##        # if err != 0:
##        #    sys.exit(err)
##        # sys.argv = orig_argv
##
##        # copy build files
##        if self.extensions is None:
##            self.extensions = []
##        for f_src in glob("build/hwtHls/llvm/*.so"):
##            e = Extension("hello", sources=["placeholder-resolved-by-meson"])
##            self.extensions.append(e)
##            f_dst = path.relpath(path.abspath(f_src), path.abspath("./build"))
##            if self.inplace:
##                print("cp", f_src, f_dst)
##                shutil.copy(
##                    f_src,
##                    f_dst,
##                )
##
#
#setup(name='hwtHls',
#      version='0.1',
#      description='High level synthesizer for HWToolkit (hwt)',
#      long_description=long_description,
#      long_description_content_type="text/markdown",
#      url='https://github.com/Nic30/hwtHls',
#      author='Michal Orsak',
#      author_email='Nic30original@gmail.com',
#      classifiers=[
#        "Development Status :: 4 - Beta",
#        "Intended Audience :: Developers",
#        "License :: OSI Approved :: MIT License",
#        "Operating System :: OS Independent",
#        "Programming Language :: Python :: 3 :: Only",
#        "Programming Language :: Python :: 3",
#        "Programming Language :: Python :: 3.5",
#        "Programming Language :: Python :: 3.6",
#        "Programming Language :: Python :: 3.7",
#        "Topic :: Scientific/Engineering :: Electronic Design Automation (EDA)",
#        "Topic :: System :: Hardware",
#        "Topic :: System :: Emulators",
#        "Topic :: Utilities"
#      ],
#      install_requires=[
#        'hwtLib>=2.9',
#        'scipy>=1.5.2',
#      ],
#      ext_modules=cythonize(ext),
#      license='MIT',
#      packages=find_packages(),
#      include_package_data=True,
#      zip_safe=False,
#      #tests_require=['pytest'],
#      test_suite='hwtHls.tests.all.suite',
#      #cmdclass={"build_ext": build_ext},
#)
#