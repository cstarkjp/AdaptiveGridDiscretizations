import itertools
import math
import numpy as np
import copy
from . import Dense
from . import Sparse

def norm_infinity(arr):
	return np.max(np.abs(np.array(arr)))

class stop_default(object):
	"""
	Default stopping criterion for the newton method.
	Parameters : 
	* residue_tol : target tolerance on the residue infinity norm
	* niter_max : max iterations before aborting
	* raise_on_abort : wether to raise an exception if aborting
	* niter_print : generator for which iterations to print the state
	"""	
	def __init__(
		self,residue_tol=1e-8,niter_max=50,raise_on_abort=True,
		niter_print=itertools.chain(range(1,6),range(6,16,2),itertools.count(16,4))
		):
		self.residue_tol	=residue_tol
		self.niter_max 		=niter_max
		self.raise_on_abort	=raise_on_abort
		self.niter_print_iter =iter(copy.deepcopy(niter_print))
		self.niter_print_next = next(self.niter_print_iter) # Next iteration to print
		self.niter_print_last = None # Last iteration printed
		self.residue_norms = []

	def abort(self):
		if self.raise_on_abort:
			raise ValueError
		return True


	def __call__(self,residue,niter):
		residue_norm = norm_infinity(residue)
		self.residue_norms.append(residue_norm)

		def print_state():
			if niter!=self.niter_print_last:
				self.niter_print_last = niter
				print("Iteration:",niter," Residue norm:",residue_norm)


		if niter>=self.niter_print_next:
			print_state()
			self.niter_print_next = next(self.niter_print_iter)
		
		
		if residue_norm<self.residue_tol:
			print_state()
			print("Target residue reached. Terminating.")
			return True

		if np.isnan(residue_norm):
			print_state()
			print("Residue has NaNs. Aborting.")
			return self.abort()
		
		if niter>=self.niter_max:
			print_state()
			print("Max iterations exceeded. Aborting.")
			return self.abort()

		return False		

class damping_default(object):
	def __init__(self,criterion=None,refine_factor=2.,step_min=2.e-3,raise_on_abort=False):
		self.criterion=criterion
		self.refine_factor=refine_factor
		self.step_min=step_min
		self.raise_on_abort=raise_on_abort
		self.steps = []

	def __call__(self,x,direction,*params):
		step = 1.
		while self.criterion(x+step*direction,*params):
			step/=2.
			if step<self.step_min:
				print("Minimal damping undershot. Aborting.")
				if self.raise_on_abort:
					raise ValueError
				break	
		self.steps.append(step)
		return step


def newton_root(func,x0,params=None,stop="Default",
	relax=None,damping=None,ad="Sparse",solver=None,in_place=False):
	"""
	Newton's method, for finding a root of a given function.
	func : function to be solved
	x0 : initial guess for the root
	fprime : method for computin
	stop : stopping criterion
	relax : added to the jacobian before inversion
	damping : criterion for step reduction
	ad : is either 
	   - keyword "Sparse" for using Sparse AD (Default)
	   - keyword "Dense" for using Dense AD
	   - a shape_bound given as a tuple, for Dense AD with few independent variables
	"""

	if stop is "Default": 	stop = stop_default()
	if ad is "Dense":		ad = tuple()

	# Create a variable featuring AD information
	def ad_var(x0):
		if not in_place:
			x0=np.copy(x0)

		if ad is "Sparse":			
			return Sparse.identity(constant=x0)
		elif isinstance(ad,tuple):	
			return Dense.identity(constant=x0,shape_bound=ad)						
		assert False

	# Find Newton's descent direction
	def descent_direction(residue):
		if relax is not None:
#			residue=residue+relax
			residue+=relax

		if solver is not None:
			return solver(residue)
		elif ad is "Sparse":
			return residue.solve()
		elif isinstance(ad,tuple): # Dense ad
			return residue.solve(shape_bound=ad)

	x=ad_var(x0)
	for niter in itertools.count():
		residue = func(x,*params)
		if stop(residue,niter):
			return np.array(x)

		direction = descent_direction(residue)

		step = 1. if damping is None else damping(np.array(x),direction,*params)
		x += step*direction





#def newton_min():
#	pass