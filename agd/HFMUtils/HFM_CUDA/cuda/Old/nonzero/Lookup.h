/**
This kernel is used to list the active nodes.
*/

#ifndef BoolAtom_macro
#define BoolAtom_macro
typedef unsigned char BoolAtom;
#endif

#ifndef Int_macro
#define Int_macro
typedef int Int;
#endif

#ifndef ndim_macro
#define ndim_macro
const Int ndim=2;
#endif

#ifndef shape_i_macro
#define shape_i_macro
const Int shape_i[ndim] = {32,32};
const Int size_i = 1024; // prod(shape_i)
const Int log2_size_i = 10; // Upper bound on log2(size_i) 1+fls(size_i-1); ?
#endif

__constant__ Int shape_tot[ndim];
__constant__ Int shape_o[ndim];
__constant__ Int size_o; // prod(shape_o)

// Definitions required to compile Grid.h, but otherwise unused.
#define PERIODIC(...) 
typedef unsigned char BoolPack;

#include "../Grid.h"
#include "Accumulate.h"

extern "C" {

__global__ void Lookup(const BoolAtom * active, Int * index, Int * nindex){
	__shared__ Int x_o[ndim];
	__shared__ Int n_o;
	Int x_i[ndim]; // = ThreadIdx
	x_i[0] = threadIdx.x; x_i[1] = threadIdx.y; if(ndim==3) x_i[ndim-1] = threadIdx.z;
	const Int n_i = Grid::Index(x_i,shape_i);

	if(n_i==0){
		x_o[0] = blockIdx.x; x_o[1] = blockIdx.y; if(ndim==3) x_o[ndim-1] = blockIdx.z;
		n_o = Grid::Index(x_o,shape_o);
	}

	__syncthreads();

	Int x[ndim]; // = x_i*shape_o + x_o
	for(Int k=0; k<ndim; ++k){
		x[k] = x_i[k]*shape_o[k] + x_o[k];}
	const Int n = Grid::Index(x,shape_tot); // Note : distinct from HFM two level 

	const bool isActive = Grid::InRange(x,shape_tot) ? bool(active[n]) : false;

	__shared__ Int active_acc_i[size_i];
	active_acc_i[n_i] = isActive;

	__syncthreads();

	Accumulate(active_acc_i,n_i,log2_size_i);

	if(n_i==size_i-1) {
		nindex[n_o] = active_acc_i[size_i-1];}

	if(isActive){
		const Int pos = (active_acc_i[n_i]-1)*size_o + n_o;
		index[pos] = n;}
}

}