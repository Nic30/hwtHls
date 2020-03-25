#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

from os import path
from setuptools import setup, find_packages


this_directory = path.abspath(path.dirname(__file__))
with open(path.join(this_directory, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setup(name='hwtHls',
      version='0.1',
      description='High level synthesizer for HWToolkit (hwt)',
      long_description=long_description,
      long_description_content_type="text/markdown",
      url='https://github.com/Nic30/hwtHls',
      author='Michal Orsak',
      author_email='michal.o.socials@gmail.com',
      classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Topic :: Scientific/Engineering :: Electronic Design Automation (EDA)",
        "Topic :: System :: Hardware",
        "Topic :: System :: Emulators",
        "Topic :: Utilities"
      ],
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
