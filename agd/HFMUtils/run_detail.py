import numpy as np
from .LibraryCall import RunDispatch,GetBinaryDir
from .. import Metrics
from .. import AutomaticDifferentiation as ad
from .Grid import PointFromIndex

class Cache(object):
	def __init__(self):
		self.contents = dict()
		self.verbosity = None
		self.requested = None
	def PreProcess(self,hfmIn_raw):
		self.verbosity = hfmIn_raw.get('verbosity',1)
		self.requested = []
		if hfmIn_raw.get('exportValues',False): 		self.requested.append('values')
		if hfmIn_raw.get('exportActiveNeighs',False):	self.requested.append('activeNeighs')
		if not self.contents:
			if self.verbosity>=1: print("Requesting cacheable data")
			hfmIn_raw['exportValues']=True
			hfmIn_raw['exportActiveNeighs']=True
		else:
			if self.verbosity>=1: print("Providing cached data")
			for key,value in self.contents.items():
				setkey_safe(hfmIn_raw,key,value)
			# Note : all points set as accepted in HFM algorithm
			hfmIn_raw['exportValues']=False
			hfmIn_raw['exportActiveNeighs']=False

	def PostProcess(self,hfmOut_raw):
		if not self.contents:
			if self.verbosity>=1 : print("Filling cache data")
			for key in ('values','activeNeighs'):
				self.contents[key] = hfmOut_raw[key]
		else:
			for key in self.requested:
				setkey_safe(hfmOut_raw,key,self.contents[key]) 

def RunRaw(hfmIn):
	"""Raw call to the HFM library"""
	return RunDispatch(hfmIn,GetBinaryDir("FileHFM","HFMpy"))

def RunSmart(hfmIn,returns="out",co_output=None,cache=None):
	"""
	Calls the HFM library, with pre-processing and post-processing of data.

	tupleIn and tupleOut are intended to make the inputs and outputs 
	visible to reverse automatic differentiation
	- returns : string in ('in_raw','out_raw','out')
		early aborts the run and returns specified data
	"""
	
	#TODO : 
	#	- geometryFirst (default : all but seeds)
	#   - cache argument for faster output

	assert(returns in ('in_raw','out_raw','out'))
	hfmIn_raw = {}

	# Pre-process usual arguments
	for key,value in hfmIn.items():
#		if key not in tupleInKeys:
		PreProcess(key,value,hfmIn,hfmIn_raw)

	# Reverse automatic differentiation
	if co_output is not None:
		assert hfmIn.get('extractValues',False) and co_output[0] is None
		co_value = co_output[1] 
		indices = np.nonzero(co_value)
		positions = PointFromIndex(hfmIn_raw,np.array(indices).T)
		weights = co_value[indices]
		setkey_safe(hfmIn_raw,'inspectSensitivity',positions)
		setkey_safe(hfmIn_raw,'inspectSensitivityWeights',weights)
		setkey_safe(hfmIn_raw,'inspectSensitivityLengths',[len(weights)])
	
	# Dealing with cached data
	if cache is not None:
		cache.PreProcess(hfmIn_raw)

	# Call to the HFM library
	if returns=='in_raw': return hfmIn_raw
	hfmOut_raw = RunDispatch(hfmIn_raw,GetBinaryDir("FileHFM","HFMpy"))
	if returns=='out_raw': return hfmOut_raw
	
	# Dealing with cached data
	if cache is not None:
		cache.PostProcess(hfmOut_raw)

	# Post process
	hfmOut = {}
	for key,val in hfmOut_raw.items():
		PostProcess(key,val,hfmOut_raw,hfmOut)

	# Reverse automatic differentiation
	if co_output is not None:
		result=[]
		for key,value in hfmIn.items():
			if key=='cost':
				if isinstance(value,Metrics.Isotropic):
					value = value.to_HFM()
				result.append((value,hfmOut['costSensitivity_0']))
			elif key=='seedValues':
				sens = hfmOut['seedSensitivity_0']
				# Match the seeds with their approx given in sensitivity
				corresp = np.argmin(ad.Optimization.norm(np.expand_dims(hfmIn_raw['seeds'],axis=2)
					-np.expand_dims(sens[:,:2].T,axis=1),ord=2,axis=0),axis=0)
				sens_ordered = np.zeros_like(value)
				sens_ordered[corresp]=sens[:,2]
				result.append((value,sens_ordered))
			# TODO : speed
		return result

	return (hfmOut,hfmOut.pop('values')) if hfmIn.get('extractValues',False) else hfmOut	

def setkey_safe(dico,key,value):
	if key in dico:
		if value is not dico[key]:
			raise ValueError("Multiple values for key ",key)
	else:
		dico[key]=value

# ----------------- Preprocessing ---------------
def PreProcess(key,value,refined_in,raw_out):
	"""
	copies key,val from refined to raw, with adequate treatment
	"""

	verbosity = refined_in.get('verbosity',1)

	if key in ('cost','speed'):
		if isinstance(value,Metrics.Isotropic):
			value = value.to_HFM()
		if isinstance(value,ad.Dense.denseAD):
			setkey_safe(raw_out,'costVariation',
				value.coef if key=='cost' else (1/value).coef)
			value = np.array(value)
		setkey_safe(raw_out,key,value)
	elif key in ('metric','dualMetric'):
		if isinstance(value,Metrics.Base): # AD not handled yet
			value = value.to_HFM()
		setkey_safe(raw_out,key,value)

	elif key=='seedValues':
		if ad.is_ad(value):
			setkey_safe(raw_out,'seedValueVariation',value.coef)
			value=np.array(value)
		setkey_safe(raw_out,key,value)

	elif key=='extractValues':
		setkey_safe(raw_out,'exportValues',value)
	else:
		setkey_safe(raw_out,key,value)

#	if isinstance(value,Metrics.Base): 
		# ---------- Set the metric ----------
#		assert(key in ['cost','speed','metric','dualMetric'])

#		# Set the model if unspecified
#		if 'model' not in refined_in:
#			modelName = value.name_HFM()
#				modelName=modelName[0]
#				if verbosity>=1:
#					print('model defaults to ',modelName[0])
#			setkey_safe(raw_out,'model',modelName)
		
		# Set the metric
#		metricValues = value.to_HFM()

#		if ad.is_ad(metricValues):
			# Interface for forward automatic differentiation
#			assert(key=='cost' and isinstance(metricValues,Metrics.Isotropic))
#			setkey_safe(raw_out,'costVariation',metricValues.gradient())
#			for i,dvalue in enumerate(metricValues.gradient()):
#				setkey_safe(raw_out,'costVariation_'+str(i),dvalue)
#		else:
#			setkey_safe(raw_out,key,metricValues)

#---------- Post processing ------------
def PostProcess(key,value,raw_in,refined_out):
	"""
	copies key,val from raw to refined, with adequate treatment
	"""
	if key.startswith('geodesicPoints'):
		from ..HFMUtils import GetGeodesics
		suffix = key[len('geodesicPoints'):]
		geodesics = GetGeodesics(raw_in,suffix=suffix)
		setkey_safe(refined_out,"geodesics"+suffix,
			[np.moveaxis(geo,-1,0) for geo in geodesics])
	elif key.startswith('geodesicLengths'):
		pass

	elif key=='values':
		if 'valueVariation' in raw_in:
			value = ad.Dense.denseAD(value,raw_in['valueVariation'])
		setkey_safe(refined_out,key,value)
	elif key=='valueVariation':
		pass
		
	else:
		setkey_safe(refined_out,key,value)

