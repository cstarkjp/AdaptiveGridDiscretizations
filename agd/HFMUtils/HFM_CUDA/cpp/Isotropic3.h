#include "TypeTraits.h"

const Int ndim = 3;
const Int nsym = 3; // Number of symmetric offsets
const Int nfwd = 0; // Number of forward offsets

const Int ntot = 6; // 2*nsym + nfwd
const Int nact = 3; // nsym + nfwd

#ifndef shape_i_macro
const Int shape_i[ndim] = {4,4,4}; // Shape of a single block
const Int size_i = 64; // Product of shape_i
const Int log2_size_i = 6; // Upper bound on log_2(size_i)
#endif

#ifndef niter_macro
const Int niter = 8;
#endif

#include "Isotropic_.h"
