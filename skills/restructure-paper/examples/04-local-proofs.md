# Examples for 04-local-proofs

## Abstract examples

“Correct the map on the exceptional set” is insufficient when repair is the difficult step. Define the correction, show that it stays inside that set and preserves the needed invariant, and account for its cost if the theorem is quantitative. Counting the exceptional set alone does not establish repairability.

“Apply Cauchy–Schwarz repeatedly” can be adequate for an ordinary two-line estimate. With weights and replicated variables, display one legal weighted step and identify the terminal expression to which the moment hypothesis applies. Expand that bookkeeping rather than surrounding routine simplifications.

A construction has a right adjoint because of a compactness or duality condition. Explain why this particular adjoint represents the object needed next and how its unit/counit controls the claimed operation. Listing the existence of several adjoints does not explain their role.

## A citation may establish less than the sentence claims

Suppose a cited theorem gives uniform integrability, but the manuscript says “the theorem therefore gives convergence in L1.” Check and state the other ingredient, such as convergence in probability, and explain how it combines with uniform integrability. Do not reproduce the imported theorem's proof; supply the missing application step. A reviewer who knows the relevant convergence criterion must still ask whether those inputs and their connection appear in the manuscript.

A source identifies two vector spaces by an invertible linear map S, but equips the source with the transported product u star v = S^{-1}(S(u) S(v)). Its underlying-space identification does not say that star is the original product. If a later calculation needs the original product, identify which product the imported theorem preserves and give the required multiplicativity relation; saying that the convention is already incorporated does not do this. The source's explicit limitation is part of the input, not optional surrounding prose.

## A transfer needs its preserved data

An integral matrix may be invertible over the rationals and singular modulo a prime. To conclude invertibility after reduction, identify a condition that survives, such as determinant equal to 1 or -1; “reduce the same matrix” alone is insufficient. This illustrates the difference between retaining a construction and retaining the property the next step needs.

Under a change of variables y=2x, a probability density transforms as q(y)=p(y/2)/2. A statement that “normalization is already included” does not expose the correction. Show the general transformation that proves the needed identity, rather than check only one special density. The aim is to reveal the mathematical adjustment, not to expand every routine calculation in the paper.

A coordinate change can also depend on a parameter. If y=x+t and v(y,t)=u(y-t,t), then the time derivative is v_t=u_t-u_x at (y-t,t). Checking only v_y=u_x at a fixed time misses the correction required by a time-evolution equation. Inspect the full transformation and the operation the argument actually uses, not just a correct formula for one component. The needed explanation can still be a single displayed identity.
