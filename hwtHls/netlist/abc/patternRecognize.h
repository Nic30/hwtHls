#pragma once
#include <base/abc/abc.h>
#include <optional>

namespace hwtHls {

struct AbcPatternMux2 {
	bool isNegated;

	Abc_Obj_t *v0;
	bool v0n;
	Abc_Obj_t *c0;
	bool c0n;
	Abc_Obj_t *v1;
	bool v1n;
};

struct AbcPatternMux3: AbcPatternMux2 {
	Abc_Obj_t *c1;
	bool c1n;
	Abc_Obj_t *v2;
	bool v2n;
};

std::optional<AbcPatternMux2> recognizeMux2(bool negated, Abc_Obj_t *top)  noexcept(true);
std::optional<AbcPatternMux3> recognizeMux3(bool negated, Abc_Obj_t *top)  noexcept(true);
}
