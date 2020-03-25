import numpy as np
import os
import time
import copy

from . import kernel_traits
from . import solvers
from . import misc
from .cupy_module_helper import GetModule,SetModuleConstant,getmtime_max,traits_header
from .. import Grid
from ... import FiniteDifferences as fd
from ... import AutomaticDifferentiation as ad
from ... import Metrics

class Interface(object):
	"""
	This class carries out the RunGPU function work. 
	It should not be used directly.
	"""
	def __init__(self,hfmIn):

		self.hfmIn = hfmIn
		if hfmIn['arrayOrdering'] != 'RowMajor':
			raise ValueError("Only RowMajor indexing supported")

		# Needed for GetValue
		self.help = hfmIn.get('help',[])
		self.hfmOut = {
		'key used':['exportValues','origin','arrayOrdering'],
		'key defaulted':[],
		'key visited':[],
		'help content':{},
		}
		self.help_content = self.hfmOut['help content']

		self.verbosity = 1
		self.verbosity = self.GetValue('verbosity',default=1,
			help="Choose the amount of detail displayed on the run")
		
		self.model = self.GetValue('model',help='Minimal path model to be solved.')
		# Unified treatment of standard and extended curvature models
		if self.model.endswith("Ext2"): self.model=self.model[:-4]+"2"

		self.ndim = len(hfmIn['dims'])
		
		self.returns=None
		self.xp = ad.cupy_generic.get_array_module(**hfmIn)
		
	def HasValue(self,key):
		self.hfmOut['key visited'].append(key)
		return key in self.hfmIn

	def GetValue(self,key,default="_None",verbosity=2,help=None):
		"""
		Get a value from a dictionnary, printing some help if requested.
		"""
		if key in self.help and key not in self.help_content:
			self.help_content[key]=help
			if self.verbosity>=1:
				if help is None: 
					print(f"Sorry : no help for key {key}")
				else:
					print(f"---- Help for key {key} ----")
					print(help)
					print("-----------------------------")

		if key in self.hfmIn:
			self.hfmOut['key used'].append(key)
			return self.hfmIn[key]
		elif isinstance(default,str) and default == "_None":
			raise ValueError(f"Missing value for key {key}")
		else:
			self.hfmOut['key defaulted'].append((key,default))
			if verbosity<=self.verbosity:
				print(f"key {key} defaults to {default}")
			return default


	def Run(self,returns='out'):
		assert returns in ('in_raw','out_raw','out')
		self.returns=returns
		self.block={}
		self.in_raw = {'block':self.block}
		self.out_raw = {}

		self.SetKernelTraits()
		self.SetGeometry()
		self.SetValuesArray()
		self.SetKernel()
		self.SetSolver()
		self.PostProcess()

		return self.hfmOut

	@property
	def isCurvature(self):
		if any(self.model.startswith(e) for e in ('Isotropic','Riemann','Rander')):
			return False
		if self.model in ['ReedsShepp2','ReedsSheppForward2','Elastica2','Dubins2']:
			return True
		raise ValueError("Unreconized model")

	def SetKernelTraits(self):
		if self.verbosity>=1: print("Setting the kernel traits.")
		if self.verbosity>=2: print("(Scalar,Int,shape_i,niter_i,...)")	
		traits = kernel_traits.default_traits(self)
		traits.update(self.GetValue('traits',default=tuple(),
			help="Optional trait parameters passed to kernel"))

		self.multiprecision = (self.GetValue('multiprecision',default=False,
			help="Use multiprecision arithmetic, to tmprove accuracy") or 
			self.GetValue('values_float64',default=False) )
		if self.multiprecision: 
			traits['multiprecision_macro']=1
			traits['strict_iter_o_macro']=1
			traits['strict_iter_i_macro']=1

		self.factoringRadius = self.GetValue('factoringRadius',default=0,
			help="Use source factorization, to improve accuracy")
		if self.factoringRadius: traits['factor_macro']=1

		order = self.GetValue('order',default=1,
			help="Use second order scheme to improve accuracy")
		if order not in {1,2}: raise ValueError(f"Unsupported scheme order {order}")
		if order==2: traits['order2_macro']=1
		self.order=order

		if not self.isCurvature: # Dimension generic models
			traits['ndim_macro'] = int(self.model[-1])

		self.strict_iter_o = traits.get('strict_iter_o_macro',0)

		self.traits = traits
		self.in_raw['traits']=traits

		self.float_t = np.dtype(traits['Scalar']).type
		self.int_t   = np.dtype(traits['Int']   ).type
		self.shape_i = traits['shape_i']

	def SetGeometry(self):
		if self.verbosity>=1: print("Prepating the domain data (shape,metric,...)")

		# Domain shape and grid scale
		self.shape = tuple(self.GetValue('dims',
			help="dimensions (shape) of the computational domain").astype(int))
		self.periodic = self.GetValue('periodic',default=(False,)*self.ndim,
			help="Apply periodic boundary conditions on some axes")
		self.shape_o = tuple(misc.round_up(self.shape,self.shape_i))

		if self.HasValue('gridScale'):
			self.h = self.GetValue('gridScale', default=None,
				help="Scale of the computational grid")
		else:
			self.h = self.GetValue('gridScales', default=None,
				help="Axis independent scales of the computational grid")
		if self.isCurvature: self.h_per = 2.*np.pi / self.shape[2] # Gridscale for periodic dimension

		self.drift = self.GetValue('drift', default=None, verbosity=3,
			help="Drift introduced in the eikonal equation, becoming F(grad u - drift)=1")

		# Get the metric or cost function
		if self.model.startswith('Isotropic') or self.isCurvature:
			self.metric = self.GetValue('cost',None,verbosity=3,
				help="Cost function for the minimal paths")
			self.dualMetric = self.GetValue('speed',None,verbosity=3,
				help="Speed function for the minimal paths")
		else:
			self.metric = self.GetValue('metric',default=None,verbosity=3,
				help="Metric of the minimal path model")
			self.dualMetric = self.GetValue('dualMetric',default=None,verbosity=3,
				help="Dual metric of the minimal path model")

		# Import from HFM format, and make copy, if needed
		if self.model.startswith('Isotropic') or self.isCurvature: 
			metricClass = Metrics.Isotropic
		elif self.model.startswith('Riemann'): metricClass = Metrics.Riemann
		elif self.model.startswith('Rander') : metricClass = Metrics.Rander

		overwriteMetric = self.GetValue("overwriteMetric",default=False,
				help="Allow overwriting the metric or dualMetric")

		if ad.cupy_generic.isndarray(self.metric) or np.isscalar(self.metric): 
			self.metric = metricClass.from_HFM(self.metric)
		elif not overwriteMetric:
			self.metric = copy.deepcopy(self.metric)
		if ad.cupy_generic.isndarray(self.dualMetric) or np.isscalar(self.dualMetric): 
			self.dualMetric = metricClass.from_HFM(self.dualMetric)
		elif not overwriteMetric:
			self.dualMetric = copy.deepcopy(self.dualMetric)

		# Rescale 
		if self.metric is not None: 	self.metric =     self.metric.rescale(1/self.h)
		if self.dualMetric is not None: self.dualMetric = self.dualMetric.rescale(self.h)
		if self.drift is not None:
			if np.isscalar(self.h): 
				self.drift *= self.h
			else: 
				h = self.xp.array((self.h,self.h,self.h_per) if self.isCurvature else self.h)
				self.drift *= h.reshape((self.ndim,)+(1,)*self.ndim)

		if self.isCurvature:
			if self.metric is None: self.metric = self.dualMetric.dual()
			self.xi = self.GetValue('xi',
				help="Cost of rotation for the curvature penalized models")
			self.kappa = self.GetValue('kappa',default=0.,
				help="Rotation bias for the curvature penalized models")
			self.theta = self.GetValue('theta',default=0.,verbosity=3,
				help="Deviation from horizontality, for the curvature penalized models")

			self.xi *= self.h_per
			self.kappa /= self.h_per

			self.geom = ad.array([e for e in (self.metric,self.xi,self.kappa,self.theta)
				if not np.isscalar(e)])
			self.periodic = (False,False,True)

		else: # not self.isCurvature
			if self.model.startswith('Isotropic'):
				if self.metric is None: self.metric = self.dualMetric.dual()
				self.geom = self.metric.cost
			elif self.model.startswith('Riemann'):
				if self.dualMetric is None: self.dualMetric = self.metric.dual()
				self.geom = self.dualMetric.flatten()
			elif self.model.startswith('Rander'):
				if self.metric is None: self.metric = self.dualMetric.dual()
				self.geom = Metrics.Riemann(self.metric.m).dual().flatten()
				if self.drift is None: self.drift = self.metric.w
				else: self.drift += self.metric.w

			# TODO : remove. No need to create this grid for our interpolation
			grid = ad.array(np.meshgrid(*(self.xp.arange(s,dtype=self.float_t) 
				for s in self.shape), indexing='ij')) # Adimensionized coordinates
			self.metric.set_interpolation(grid,periodic=self.periodic) # First order interpolation


		self.block['geom'] = misc.block_expand(fd.as_field(self.geom,self.shape),
			self.shape_i,mode='constant',constant_values=self.xp.inf)
		if self.drift is not None:
			self.block['drift'] = misc.block_expand(fd.as_field(self.drift,self.shape),
				self.shape_i,mode='constant',constant_values=self.xp.nan)

	def SetValuesArray(self):
		if self.verbosity>=1: print("Preparing the values array (setting seeds,...)")
		xp = self.xp
		values = xp.full(self.shape,xp.inf,dtype=self.float_t)
		self.seeds = xp.array(self.GetValue('seeds', 
			help="Points from where the front propagation starts") )
		self.seeds = Grid.PointFromIndex(self.hfmIn,self.seeds,to=True) # Adimensionize seed position
		if len(self.seeds)==1: self.seed=self.seeds[0]
		seedValues = xp.zeros(len(self.seeds),dtype=self.float_t)
		seedValues = xp.array(self.GetValue('seedValues',default=seedValues,
			help="Initial value for the front propagation"))
		seedRadius = self.GetValue('seedRadius',default=0.,
			help="Spread the seeds over a radius given in pixels, so as to improve accuracy.")

		if seedRadius==0.:
			seedIndices = np.round(self.seeds).astype(int)
			values[tuple(seedIndices.T)] = seedValues
		else:
			neigh = Grid.GridNeighbors(self.hfmIn,self.seed,seedRadius) # Geometry last
			r = seedRadius 
			aX = [xp.arange(int(np.floor(ci-r)),int(np.ceil(ci+r)+1)) for ci in self.seed]
			neigh =  ad.stack(xp.meshgrid( *aX, indexing='ij'),axis=-1)
			neigh = neigh.reshape(-1,neigh.shape[-1])

			# Select neighbors which are close enough
			neigh = neigh[ad.Optimization.norm(neigh-self.seed,axis=-1) < r]

			# Periodize, and select neighbors which are in the domain
			nper = np.logical_not(self.periodic)
			test = np.logical_and(-0.5<=neigh[:,nper],
				neigh[:,nper]<xp.array(self.shape)[nper]-0.5)
			inRange = np.all(np.logical_and(-0.5<=neigh[:,nper],
				neigh[:,nper]<xp.array(self.shape)[nper]-0.5),axis=-1)
			neigh = neigh[inRange,:]
			
			diff = (neigh - self.seed).T # Geometry first
#			neigh[:,self.periodic] = neigh[:,self.periodic] % self.shape[self.periodic]
			metric0 = self.Metric(self.seed)
			metric1 = self.Metric(neigh.T)
			values[tuple(neigh.T)] = 0.5*(metric0.norm(diff) + metric1.norm(diff))

		block_values = misc.block_expand(values,self.shape_i,mode='constant',constant_values=xp.nan)

		# Tag the seeds
		if np.prod(self.shape_i)%8!=0:
			raise ValueError('Product of shape_i must be a multiple of 8')
		block_seedTags = xp.isfinite(block_values)
		block_seedTags = misc.packbits(block_seedTags,bitorder='little')
		block_seedTags = block_seedTags.reshape( self.shape_o + (-1,) )
		block_values[xp.isnan(block_values)] = xp.inf

		self.block.update({'values':block_values,'seedTags':block_seedTags})

		# Handle multiprecision
		if self.multiprecision:
			block_valuesq = xp.zeros(block_values.shape,dtype=self.int_t)
			self.block.update({'valuesq':block_valuesq})

		if self.strict_iter_o:
			self.block['valuesNext']=block_values.copy()
			if self.multiprecision:
				self.block['valuesqNext']=block_valuesq.copy()

		for key,value in self.block.items():
			if value.dtype.type not in (self.float_t,self.int_t,np.uint8):
				raise ValueError(f"Inconsistent type {value.dtype.type} for key {key}")

	def SetKernel(self):
		if self.verbosity>=1: print("Preparing the GPU kernel")
		if self.GetValue('dummy_kernel',default=False): return
		in_raw = self.in_raw

		# Set a few last traits
		traits = self.traits
		if self.isCurvature:
			traits['xi_var_macro'] = int(not np.isscalar(self.xi))
			traits['kappa_var_macro'] = int(not np.isscalar(self.kappa))
			traits['theta_var_macro'] = int(not np.isscalar(self.theta))
		if self.periodic != (False,)*self.ndim:
			traits['periodic_macro']=1
			traits['periodic']=periodic

		self.source = traits_header(self.traits)
		if self.isCurvature: self.source += f'#include "{self.model}.h"\n'
		else: self.source += f'#include "{self.model[:-1]}_.h"\n' # Dimension generic

		cuda_path = os.path.join(os.path.dirname(os.path.realpath(__file__)),"cuda")
		date_modified = getmtime_max(cuda_path)
		self.source += f"// Date cuda code last modified : {date_modified}\n"
		cuoptions = ("-default-device", f"-I {cuda_path}"
			) + self.GetValue('cuoptions',default=tuple(),
			help="Options passed via cupy.RawKernel to the cuda compiler")

		self.module = GetModule(self.source,cuoptions)
		mod = self.module

		float_t,int_t = self.float_t,self.int_t
		tol = self.float_t(self.GetValue('tol',default=1e-8,
			help="Convergence tolerance for the fixed point solver"))
		SetModuleConstant(mod,'tol',tol,float_t)

		self.size_o = np.prod(self.shape_o)
		SetModuleConstant(mod,'shape_o',self.shape_o,int_t)
		SetModuleConstant(mod,'size_o', self.size_o, int_t)

		size_tot = self.size_o * np.prod(self.shape_i)
		SetModuleConstant(mod,'shape_tot',self.shape,int_t) # Used for periodicity
		SetModuleConstant(mod,'size_tot', size_tot, int_t) # Used for geom indexing

		if self.multiprecision:
			# Choose power of two, significantly less than h
			multip_step = 2.**np.floor(np.log2(self.h/10)) 
			SetModuleConstant(mod,'multip_step',multip_step, float_t)
			multip_max = np.iinfo(self.int_t).max*multip_step/2
			SetModuleConstant(mod,'multip_max',multip_max, float_t)

			self.multip_step=multip_step
			in_raw.update({'multip_step':multip_step,'multip_max':multip_max})

		if self.factoringRadius:
			SetModuleConstant(mod,'factor_radius2',self.factoringRadius**2,float_t)
			SetModuleConstant(mod,'factor_origin',self.seed,float_t) # Single seed only
			SetModuleConstant(mod,'factor_metric',self.Metric(self.seed).to_HFM(),float_t)

		if self.order==2:
			order2_threshold = self.GetValue('order2_threshold',0.2,
				help="Relative threshold on second order differences / first order difference,"
				"beyond which the second order scheme deactivates")
			SetModuleConstant(mod,'order2_threshold',order2_threshold,float_t)
		
		if self.isCurvature:
			if np.isscalar(self.xi): SetModuleConstant(mod,'xi',self.xi,float_t)
			if np.isscalar(self.kappa): SetModuleConstant(mod,'kappa',self.kappa,float_t)

		in_raw.update({
			'tol':tol,
			'shape_o':self.shape_o,
			'shape_tot':self.shape,
			'source':self.source,
			})

	def Metric(self,x):
		if self.isCurvature: 
			raise ValueError("No metric available for curvature penalized models")
		if hasattr(self,'metric'): return self.metric.at(x)
		else: return self.dualMetric.at(x).dual()

	def KernelArgs(self):
		kernel_args = tuple(self.block[key] for key in self.kernel_argnames)

		if self.strict_iter_o:
			self.block['values'],self.block['valuesNext'] \
				=self.block['valuesNext'],self.block['values']
			if self.multiprecision:
				self.block['valuesq'],self.block['valuesqNext'] \
					=self.block['valuesqNext'],self.block['valuesq']

		return kernel_args

	def SetSolver(self):
		if self.verbosity>=1: print("Setup and run the eikonal solver")
		solver = self.GetValue('solver',default='AGSI',help="Choice of fixed point solver")
		self.nitermax_o = self.GetValue('nitermax_o',default=2000,
			help="Maximum number of iterations of the solver")

		if self.returns=='in_raw': return {'in_raw':in_raw,'hfmOut':hfmOut}

		kernel_argnames = ['values'] #,'geom','seedTags']
		if self.multiprecision: kernel_argnames.append('valuesq')
		if self.strict_iter_o: 
			kernel_argnames.append('valuesNext')
			if self.multiprecision: kernel_argnames.append('valuesqNext')
		kernel_argnames.append('geom')
		kernel_argnames.append('seedTags')
		if self.drift is not None: kernel_argnames.append('drift')
		self.kernel_argnames = kernel_argnames

		solver_start_time = time.time()

		if solver=='global_iteration':
			niter_o = solvers.global_iteration(self)
		elif solver in ('AGSI','adaptive_gauss_siedel_iteration'):
			niter_o = solvers.adaptive_gauss_siedel_iteration(self)
		else:
			raise ValueError(f"Unrecognized solver : {solver}")

		solverGPUTime = time.time() - solver_start_time
		self.hfmOut.update({
			'niter_o':niter_o,
			'solverGPUTime':solverGPUTime,
		})

		if niter_o>=self.nitermax_o:
			nonconv_msg = (f"Solver {solver} did not reach convergence after "
				f"maximum allowed number {niter_o} of iterations")
			if self.GetValue('raiseOnNonConvergence',default=True):
				raise ValueError(nonconv_msg)
			else:
				print("---- Warning ----\n",nonconv_msg,"\n-----------------\n")

		if self.verbosity>=1: print(f"GPU solve took {solverGPUTime} seconds,"
			f" in {niter_o} iterations.")

	def PostProcess(self):
		if self.verbosity>=1: print("Post-Processing")
		if self.returns=='out_raw': return {'out_raw':out_raw,'in_raw':in_raw,'hfmOut':hfmOut}
		values = misc.block_squeeze(self.block['values'],self.shape)
		if self.multiprecision:
			valuesq = misc.block_squeeze(self.block['valuesq'],self.shape)
			if self.GetValue('values_float64',default=False,
				help="Export values using the float64 data type"):
				float64_t = np.dtype('float64').type
				self.hfmOut['values'] = (self.xp.array(values,dtype=float64_t) 
					+ float64_t(self.multip_step) * valuesq)
			else:
				self.hfmOut['values'] = (values 
					+ self.xp.array(valuesq,dtype=self.float_t)*self.multip_step)
		else:
			self.hfmOut['values'] = values

		self.hfmOut['key unused'] = list(set(self.hfmIn.keys())-set(self.hfmOut['key used']))
		if self.verbosity>=1 and self.hfmOut['key unused']:
			print(f"Warning : unused keys from user : {self.hfmOut['key unused']}")
		return self.hfmOut



