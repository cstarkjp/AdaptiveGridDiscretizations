# Copyright 2020 Jean-Marie Mirebeau, University Paris-Sud, CNRS, University Paris-Saclay
# Distributed WITHOUT ANY WARRANTY. Licensed under the Apache License, Version 2.0, see http://www.apache.org/licenses/LICENSE-2.0

from . import _Interface

def RunGPU(hfmIn,*args,**kwargs):
	return _Interface.Interface(hfmIn).Run(*args,**kwargs)