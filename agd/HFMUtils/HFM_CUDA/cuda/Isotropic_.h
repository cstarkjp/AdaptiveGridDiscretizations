#pragma once 

const Int n_print = 100;
const Int n_print2=3;

#include "Constants.h"
#include "Grid.h"
#include "HFM.h"

extern "C" {

__global__ void Update(
	Scalar * u, MULTIP(Int * uq,)
	const Scalar * metric, const BoolPack * seeds, 
	const Int * updateList_o, BoolAtom * updateNext_o){ // Used as simple booleans

//	__shared__ Int shape_o[ndim];
	__shared__ Int x_o[ndim];
	__shared__ Int n_o;

	if(threadIdx.x==0 && threadIdx.y==0 && threadIdx.z==0){
		n_o = updateList_o[blockIdx.x];
		Grid::Position(n_o,shape_o,x_o);
	}

	__syncthreads(); // __shared__ x_o, n_o

	Int x_i[ndim], x[ndim];
	x_i[0] = threadIdx.x; x_i[1]=threadIdx.y; if(ndim==3) x_i[ndim-1]=threadIdx.z;
	for(int k=0; k<ndim; ++k){
		x[k] = x_o[k]*shape_i[k]+x_i[k];}

	const Int n_i = Grid::Index(x_i,shape_i);
	const Int n = n_o*size_i + n_i;

	const bool isSeed = Grid::GetBool(seeds,n);
	const Scalar cost = metric[n];
	const Scalar u_old = u[n];
	__shared__ Scalar u_i[size_i]; // Shared block values
	u_i[n_i] = u_old;

	MULTIP(const Int zz=0+0;
		const Int zzz=0+0+0;)


#if multiprecision_macro
	const Int uq_old = uq[n];
	__shared__ Int uq_i[size_i];
	uq_i[n_i] = uq_old;
#endif

	// Get the neighbor values, or their indices if interior to the block
	Int    v_i[ntot]; // Index of neighbor, if in the block
	Scalar v_o[ntot]; // Value of neighbor, if outside the block
#if multiprecision_macro
	Int vq_o[ntot];
#endif
	for(Int k=0,ks=0; k<nsym; ++k){
		for(Int s=0; s<2; ++s){
			Int y[ndim], y_i[ndim]; // Position of neighbor. Caution : aliasing
			for(int l=0; l<ndim; ++l){y[l]=x[l]; y_i[l]=x_i[l];}

			const Int eps=2*s-1;
			y[k]+=eps; y_i[k]+=eps;

			if(Grid::InRange(y_i,shape_i))  {
				v_i[ks] = Grid::Index(y_i,shape_i);
			} else {
				v_i[ks] = -1;
				if(Grid::InRange(y,shape_tot)) {
					const Int ny = Grid::Index(y,shape_i,shape_o);
					v_o[ks] = u[ny];
#if multiprecision_macro
					vq_o[ks] = uq[ny];
#endif
				} else {
					v_o[ks] = infinity();
#if multiprecision_macro
					vq_o[ks] = 0;
#endif
				}
			}
			++ks;
		}
	}
	__syncthreads(); // __shared__ u_i

	// Compute and save the values
	HFMIter(!isSeed,n_i,cost,v_o,v_i,u_i);
	u[n] = u_i[n_i];
	
	// Find the smallest value which was changed.
	const Scalar u_diff = abs(u_old - u_i[n_i]);
	if( !(u_diff>tol) ){// Equivalent to u_diff<=tol, but Ignores NaNs 
		u_i[n_i]=infinity();}
	__syncthreads(); // Get all values before reduction

	Reduce_i_macro( u_i[n_i] = min(u_i[n_i],u_i[m_i]); )
	__syncthreads();  // Make u_i[0] accessible to all 

	// Tag neighbor blocks, and this particular block, for update
	if(u_i[0]!=infinity() && n_i<=2*ndim){ 
		Int k = n_i/2;
		const Int s = n_i%2;
		Int eps = 2*s-1;
		if(n_i==2*ndim){k=0; eps=0;}

		Int neigh_o[ndim];
		for(Int l=0; l<ndim; ++l) {neigh_o[l]=x_o[l];}
		neigh_o[k]+=eps;
		if(Grid::InRange(neigh_o,shape_o)) {
			updateNext_o[Grid::Index(neigh_o,shape_o)]=1;}
	}

	if(debug_print && n==0){
		printf("shape %i,%i",shape_tot[0],shape_tot[1]);

	}
}

} // Extern "C"