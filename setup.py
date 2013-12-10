#!/usr/bin/env python
from setuptools import setup, find_packages

setup (
    name = "katscripts",
    version = "trunk",
    description = "KAT observation scripting framework",
    author = "MeerKAT SDP, CAM and Commissioning Teams",
    author_email = "spt@ska.ac.za",
    packages = find_packages(),
    include_package_data = True,
#    scripts = [],
    url = 'http://ska.ac.za/',
    classifiers = [
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: Other/Proprietary License",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Scientific/Engineering :: Astronomy",
    ],
    platforms = [ "OS Independent" ],
    install_requires = ['numpy', 'katpoint'],
    keywords = "meerkat kat ska",
    zip_safe = False,
)