#include <hwtHls/netlist/abc/patternRecognize.h>
#include <aig/aig/aig.h>
#include <algorithm>

namespace hwtHls {

void * __attribute__ ((unused)) ___v2 = (void*) &Vec_MemHashProfile; // to suppress warning that Vec_MemHashProfile is unused

/*
def _recognizeCommonTermNegatedInOne(self, o0: Abc_Obj_t, o1: Abc_Obj_t):
    # recognize (v0 & c), (v1 & ~c) with any permutation
    if o0.IsPi() or o1.IsPi():
        return None
    o0_0, o0_1 = o0.IterFanin()
    o0_0n = o0.FaninC0()
    o0_1n = o0.FaninC1()

    o1_0, o1_1 = o1.IterFanin()
    o1_0n = o1.FaninC0()
    o1_1n = o1.FaninC1()

    if o0_0 == o1_0 and o0_0n != o1_0n:
        indexOfC_in_o0 = 0
        indexOfC_in_o1 = 0
    elif o0_0 == o1_1 and o0_0n != o1_1n:
        indexOfC_in_o0 = 0
        indexOfC_in_o1 = 1
    elif o0_1 == o1_0 and o0_1n != o1_0n:
        indexOfC_in_o0 = 1
        indexOfC_in_o1 = 0
    elif o0_1 == o1_1 and o0_1n != o1_1n:
        indexOfC_in_o0 = 1
        indexOfC_in_o1 = 1
    else:
        return None

    # inputs for v1,v2 are negated by default
    if indexOfC_in_o0 == 0:
        c0 = o0_0
        c0n = o0_0n
        v0 = o0_1
        v0n = o0_1n
    else:
        assert indexOfC_in_o0 == 1
        c0 = o0_1
        c0n = o0_1n
        v0 = o0_0
        v0n = o0_0n

    if indexOfC_in_o1 == 0:
        v1 = o1_1
        v1n = o1_1n
    else:
        v1 = o1_0
        v1n = o1_0n

    return ((v0, v0n), (c0, c0n), (v1, v1n))
*/
std::optional<AbcPatternMux2> _recognizeCommonTermNegatedInOne(Abc_Obj_t* o0, Abc_Obj_t* o1) {
    // recognize (v0 & c), (v1 & ~c) with any permutation
    if (Abc_ObjIsPi(o0) || Abc_ObjIsPi(o1)) {
        return {};
    }
    Abc_Obj_t* o0_0 = Abc_ObjFanin0(o0);
    Abc_Obj_t* o0_1 = Abc_ObjFanin1(o0);
    bool o0_0n = Abc_ObjFaninC0(o0);
    bool o0_1n = Abc_ObjFaninC1(o0);

    Abc_Obj_t* o1_0 = Abc_ObjFanin0(o1);
    Abc_Obj_t* o1_1 = Abc_ObjFanin1(o1);
    bool o1_0n = Abc_ObjFaninC0(o1);
    bool o1_1n = Abc_ObjFaninC1(o1);

    int indexOfC_in_o0;
    int indexOfC_in_o1;
    if (o0_0 == o1_0 && o0_0n != o1_0n) {
        indexOfC_in_o0 = 0;
        indexOfC_in_o1 = 0;
    } else if (o0_0 == o1_1 && o0_0n != o1_1n) {
        indexOfC_in_o0 = 0;
        indexOfC_in_o1 = 1;
    } else if  (o0_1 == o1_0 && o0_1n != o1_0n) {
        indexOfC_in_o0 = 1;
        indexOfC_in_o1 = 0;
    } else if  (o0_1 == o1_1 && o0_1n != o1_1n) {
        indexOfC_in_o0 = 1;
        indexOfC_in_o1 = 1;
    } else {
        return {};
    }
    Abc_Obj_t* c0;
    bool c0n;
	Abc_Obj_t* v0;
	bool v0n;
    // inputs for v1,v2 are negated by default
    if (indexOfC_in_o0 == 0) {
        c0 = o0_0;
        c0n = o0_0n;
        v0 = o0_1;
        v0n = o0_1n;
    } else {
        assert(indexOfC_in_o0 == 1);
        c0 = o0_1;
        c0n = o0_1n;
        v0 = o0_0;
        v0n = o0_0n;
    }
	Abc_Obj_t* v1;
	bool v1n;
    if (indexOfC_in_o1 == 0) {
        v1 = o1_1;
        v1n = o1_1n;
    } else {
        v1 = o1_0;
        v1n = o1_0n;
    }
    return AbcPatternMux2{false, v0, v0n, c0, c0n, v1, v1n};
}

/*
def _recognize3ValMuxRightSide(self, o: Abc_Obj_t, negated: bool):
    """
    .. figure:: _static/abc_aig_patterns_mux3val.png
    """
    if not negated or o.IsPi():
        return None
    c0, v0 = o.IterFanin()
    c0n = o.FaninC0()
    v0n = o.FaninC1()
    return (c0, c0n, v0, v0n)
*/
struct AbcPatternMux3RightSide {
	Abc_Obj_t* v0;
	bool v0n;
	Abc_Obj_t* c0;
	bool c0n;
};

/*
.. figure:: _static/abc_aig_patterns_mux3val.png
*/
std::optional<AbcPatternMux3RightSide> _recognize3ValMuxRightSide(Abc_Obj_t* o, bool negated) {
    if (!negated || Abc_ObjIsPi(o))
        return {};

    Abc_Obj_t* c0 = Abc_ObjFanin0(o);
    Abc_Obj_t* v0 = Abc_ObjFanin1(o);
    bool c0n = Abc_ObjFaninC0(o);
    bool v0n = Abc_ObjFaninC1(o);

    return AbcPatternMux3RightSide{c0, c0n, v0, v0n};
}

/*
def _recognize3ValMuxLeftSide(self, o: Abc_Obj_t, negated: bool, c0: Abc_Obj_t, c0n: bool, v0: Abc_Obj_t, v0n:bool):
    """
    .. figure:: _static/abc_aig_patterns_mux3val.png
    """
    # :note: o represents 13 in the figure
    if not negated or o.IsPi():
        return None

    o0, o1 = o.IterFanin()
    if o0.IsPi() or o1.IsPi():
        return None
    o0n = o.FaninC0()
    o1n = o.FaninC1()
    if o0n + o1n != 1:
        return None
    # swap to have negated on left
    if o1n:
        o0, o1 = o1, o0
        o0n, o1n = o1n, o0n
    # o0 now corresponds to 11 in the figure
    # o1 now corresponds to 12 in the figure

    # one of the o1 inputs must be ~c0, but v0 and c0 may be swapped
    o1_0, o1_1 = o1.IterFanin()
    o1_0n = o1.FaninC0()
    o1_1n = o1.FaninC1()
    c0v0Swap = False
    o1_1_0Swap = False

    # :note: negation flag should be the opposite, thats why there is !=
    if c0 == o1_1 and c0n != o1_1n:
        pass
    elif v0 == o1_1 and v0n != o1_1n:
        # v0 is actually c0
        c0v0Swap = True
    elif c0 == o1_0 and c0n != o1_0n:
        # c0 or left side
        o1_1_0Swap = True
    elif v0 == o1_0 and v0n != o1_0n:
        c0v0Swap = True
        o1_1_0Swap = True
    else:
        return None

    if c0v0Swap:
        c0, v0 = v0, c0
        c0n, v0n = v0n, c0n

    if o1_1_0Swap:
        o1_0, o1_1 = o1_1, o1_0
        o1_0n, o1_1n = o1_1n, o1_0n

    # :note: c0, v0 now has final value
    assert c0 == o1_1, ("It was just swapped to be of this value", c0, o1_1)

    # :note: now resolving node 11 and 10 in the figure
    #      o0 - 11
    #      o1_0 - 10
    assert o0n, "This should be already checked by o0n + o1n == 1"
    if not o1_0n:
        return None
    if o1_0.IsPi():
        return None
    # search for c1 which is common input of o0, o1_0 and is negated in some

    matchMuxLowerOrs = self._recognizeCommonTermNegatedInOne(o0, o1_0)
    if matchMuxLowerOrs is None:
        return None
    ((v1, v1n), (c1, c1n), (v2, v2n)) = matchMuxLowerOrs
    # inputs for v1,v2 are negated by default in this pattern
    v1n = int(not v1n)
    v2n = int(not v2n)

    tr = self._translate
    return (tr(v0, v0n), tr(c0, c0n), tr(v1, v1n), tr(c1, c1n), tr(v2, v2n))
}
*/



/*
.. figure:: _static/abc_aig_patterns_mux3val.png
*/
std::optional<AbcPatternMux3> _recognize3ValMuxLeftSide(Abc_Obj_t *o,
		bool negated, Abc_Obj_t *c0, bool c0n, Abc_Obj_t *v0, bool v0n) {
    // :note: o represents 13 in the figure
    if (!negated || Abc_ObjIsPi(o))
        return {};

    Abc_Obj_t* o0 = Abc_ObjFanin0(o);
	Abc_Obj_t* o1 = Abc_ObjFanin1(o);
    if (Abc_ObjIsPi(o0) || Abc_ObjIsPi(o1))
        return {};
    bool o0n = Abc_ObjFaninC0(o);
    bool o1n = Abc_ObjFaninC1(o);
    if (o0n + o1n != 1)
        return {};
    // swap to have negated on left
    if (o1n) {
        std::swap(o0, o1);
        std::swap(o0n, o1n);
    }
    // o0 now corresponds to 11 in the figure
    // o1 now corresponds to 12 in the figure

		// one of the o1 inputs must be ~c0, but v0 and c0 may be swapped
    Abc_Obj_t* o1_0 = Abc_ObjFanin0(o1);
	Abc_Obj_t* o1_1 = Abc_ObjFanin1(o1);
    bool o1_0n  = Abc_ObjFaninC0(o1);
    bool o1_1n  = Abc_ObjFaninC1(o1);
    bool c0v0Swap = false;
    bool o1_1_0Swap = false;

	// :note: negation flag should be the opposite, thats why there is !=
    if (c0 == o1_1 && c0n != o1_1n) {

    } else if (v0 == o1_1 && v0n != o1_1n) {
        // v0 is actually c0
        c0v0Swap = true;
    } else if ( c0 == o1_0 && c0n != o1_0n) {
        // c0 or left side
        o1_1_0Swap = true;
    } else if ( v0 == o1_0 && v0n != o1_0n) {
        c0v0Swap = true;
        o1_1_0Swap = true;
    } else {
        return {};
    }
    if (c0v0Swap) {
        std::swap(c0, v0);
        std::swap(c0n, v0n);
    }
    if (o1_1_0Swap) {
    	std::swap(o1_0, o1_1);
    	std::swap(o1_0n, o1_1n);
    }
	// :note: c0, v0 now has final value
    assert((c0 == o1_1) && "It was just swapped to be of this value");

    // :note: now resolving node 11 and 10 in the figure
    //      o0 - 11
    //      o1_0 - 10
    assert(o0n && "This should be already checked by o0n + o1n == 1");
    if (!o1_0n)
        return {};
    if (Abc_ObjIsPi(o1_0))
        return {};
    // search for c1 which is common input of o0, o1_0 and is negated in some

    auto _matchMuxLowerOrs = _recognizeCommonTermNegatedInOne(o0, o1_0);
    if (!_matchMuxLowerOrs.has_value())
        return {};
    AbcPatternMux2& m = _matchMuxLowerOrs.value();
    auto v1  = m.v0;
	auto v1n = m.v0n;
	auto c1  = m.c0;
	auto c1n = m.c0n;
	auto v2  = m.v1;
	auto v2n = m.v1n;
	// inputs for v1,v2 are negated by default in this pattern
    v1n = !v1n;
    v2n = !v2n;

    return AbcPatternMux3{false, v0, v0n, c0, c0n, v1, v1n, c1, c1n, v2, v2n};
}

/*
mux3v = None
mux3v_right = self._recognize3ValMuxRightSide(topP1, o1n)
if mux3v_right is not None:
    mux3v = self._recognize3ValMuxLeftSide(topP0, o0n, *mux3v_right)
if mux3v is None:
    mux3v_right = self._recognize3ValMuxRightSide(topP0, o0n)
    if mux3v_right is not None:
        mux3v = self._recognize3ValMuxLeftSide(topP1, o1n, *mux3v_right)
if mux3v is not None:
    if negated:
        return (HwtOps.TERNARY, mux3v)
    else:
        return (HwtOps.NOT, (HwtOps.TERNARY, mux3v))
*/
std::optional<AbcPatternMux3> recognizeMux3(bool negated, Abc_Obj_t *top)  noexcept(true) {
	if (Abc_ObjIsPi(top)) {
		return {};
	}
    bool o0n = Abc_ObjFaninC0(top);
    bool o1n = Abc_ObjFaninC1(top);
    Abc_Obj_t* topP0 = Abc_ObjFanin0(top);
    Abc_Obj_t* topP1 = Abc_ObjFanin1(top);


	std::optional<AbcPatternMux3> mux3v;
	auto mux3v_right = _recognize3ValMuxRightSide(topP1, o1n);
	if (mux3v_right.has_value()) {
	    auto& m = mux3v_right.value();
		mux3v = _recognize3ValMuxLeftSide(topP0, o0n, m.v0, m.v0n, m.c0, m.c0n);
	}
	if (!mux3v.has_value()) {
	    mux3v_right = _recognize3ValMuxRightSide(topP0, o0n);
	    if (mux3v_right.has_value()) {
	    	auto& m = mux3v_right.value();
	        mux3v = _recognize3ValMuxLeftSide(topP1, o1n, m.v0, m.v0n, m.c0, m.c0n);
	    }
	}
	if (mux3v.has_value()) {
	    if (!negated)
	    	mux3v.value().isNegated = !mux3v.value().isNegated ;
	    return mux3v;
	}
	return {};
}

/*
mux2v = self._recognizeCommonTermNegatedInOne(topP0, topP1)
if mux2v is not None:
    ((v0, v0n), (c0, c0n), (v1, v1n)) = mux2v
    if c0n and c0.IsPi():
        v0, v0n, v1, v1n = v1, v1n, v0, v0n
        c0n = False

    if (v0.IsPi() and v0n and
        v1.IsPi() and v1n) or \
            (not negated and (v0.IsPi() and v0n or
                              v1.IsPi() and v1n)):
        # remove not from value inputs and output
        negated = int(not negated)
        v0n = int(not v0n)
        v1n = int(not v1n)

    res = HwtOps.TERNARY, (
            tr(v0, v0n),
            tr(c0, c0n),
            tr(v1, v1n))
    if negated:
        return res
    else:
        # ~(pC ? p1 : p0)
         return HwtOps.NOT, res
*/
std::optional<AbcPatternMux2> recognizeMux2(bool negated, Abc_Obj_t *top)  noexcept(true) {
	if (Abc_ObjIsPi(top)) {
		return {};
	}
    bool o0n = Abc_ObjFaninC0(top);
    bool o1n = Abc_ObjFaninC1(top);
    if (!o0n || !o1n)
    	return {};
    Abc_Obj_t* topP0 = Abc_ObjFanin0(top);
    Abc_Obj_t* topP1 = Abc_ObjFanin1(top);

	auto _mux2v = _recognizeCommonTermNegatedInOne(topP0, topP1);
	if (_mux2v.has_value()) {
		AbcPatternMux2& m = _mux2v.value();
		auto v0 = m.v0;
		auto v0n = m.v0n;
		auto c0 = m.c0;
		auto c0n = m.c0n;
		auto v1 = m.v1;
		auto v1n = m.v1n;

		if (c0n && Abc_ObjIsPi(c0)) {
			std::swap(v0, v1);
			std::swap(v0n, v1n);
			c0n = false;
		}

		if ((Abc_ObjIsPi(v0) && v0n && Abc_ObjIsPi(v1) && v1n) || //
				(!negated
						&& ((Abc_ObjIsPi(v0) && v0n) || (Abc_ObjIsPi(v1) && v1n)))) {
			// remove not from value inputs and output
			negated = !negated;
			v0n = !v0n;
			v1n = !v1n;
		}
		// (pC ? p1 : p0)
		// ~(pC ? p1 : p0)
		return AbcPatternMux2{!negated, v0, v0n, c0, c0n, v1, v1n};
	}
	return {};
}

}
