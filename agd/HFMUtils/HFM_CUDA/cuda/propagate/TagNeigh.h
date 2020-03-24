
typedef float Scalar;
typedef int Int;

/* // The followind constants must be defined.
const Int ndim = 2;
const Int shape[ndim] = {10,10};
*/

__constant__ Int index_size;

#include "../Grid.h"

extern "C" {
void TagNeigh(const Scalar * minChg, const Int * index, Int * tags){
	const Int tid = blockIdx.x*blockDim.x+threadIdx.x;
	if(tid>=index_size) return;
	
	const Int n = index[tid];
	tags[n]=n;

	// Diamond connectivity
	const Int x = Grid::Position(n);
	for(Int k=0; k<ndim; ++k){
		for(Int eps=-1; eps<=1; eps+=2){
			x[k]+=eps;
			if(Grid::InRange(x)){tags[Grid::Index[x]]=n;}
			x[k]-=eps;
		}
	} 
}
} // extern "C"