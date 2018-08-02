#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

from setuptools import setup, find_packages
from setuptools.command.test import test as TestCommand
import sys
import textwrap


class PyTest(TestCommand):
    user_options = [('pytest-args=', 'a', "Arguments to pass to pytest")]

    def initialize_options(self):
        TestCommand.initialize_options(self)
        self.pytest_args = []

    def run_tests(self):
        import shlex
        # import here, cause outside the eggs aren't loaded
        import pytest
        errno = pytest.main(shlex.split(self.pytest_args))
        sys.exit(errno)


setup(name='hwtHls',
      version='0.1',
      description='High level synthesizer for HWToolkit (hwt)',
      url='https://github.com/Nic30/hwtHls',
      author='Michal Orsak',
      author_email='michal.o.socials@gmail.com',
      classifiers=textwrap.dedent("""
        Development Status :: 4 - Beta
        Intended Audience :: Developers
        License :: OSI Approved :: MIT License
        Operating System :: OS Independent
        Programming Language :: Python :: 3 :: Only
        Programming Language :: Python :: 3
        Programming Language :: Python :: 3.5
        Programming Language :: Python :: 3.6
        Programming Language :: Python :: 3.7
        Topic :: Scientific/Engineering :: Electronic Design Automation (EDA)
        Topic :: System :: Hardware
        Topic :: System :: Emulators
        Topic :: Utilities
        """).strip().splitlines(),
      install_requires=[
        'hwt>=1.9',
        'hwtLib>=1.9',
      ],
      license='MIT',
      packages=find_packages(),
      include_package_data=True,
      zip_safe=False,
      tests_require=['pytest'],
      test_suite='hwtHls.tests.all.suite',)
