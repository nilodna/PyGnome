#!/bin/sh

# Script to build in develop mode under Anaconda -- requires some lib re-linking!

python setup.py develop --no-deps
python re_link_for_anaconda.py 



