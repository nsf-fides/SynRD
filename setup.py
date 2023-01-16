#!/usr/bin/env python

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

with open("README.md", "r") as f:
    long_description = f.read()

setup(
    name="SynRD",
    version="0.1",
    description="Benchmark for differentially private synthetic data.",
    long_description=long_description,
    author="Lucas Rosenblatt",
    author_email="lr2872@nyu.edu",
    url="https://github.com/DataResponsibly/SynRD",
    packages=["SynRD", 
              "SynRD.synthesizers",
              "SynRD.benchmark",
              "SynRD.papers"],
    # setup_requires=['wheel'],
    install_requires=["DataSynthesizer",
                     "smartnoise-synth", 
                      "pandas", 
                      "numpy", 
                      "scikit-learn", 
                      "diffprivlib", 
                      "rpy2", 
                      "pathlib"],
)

# NOTE: Independent installation of mbi required with:
# `pip install git+https://github.com/ryan112358/private-pgm.git` 
