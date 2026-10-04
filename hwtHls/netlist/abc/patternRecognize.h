#pragma once
#include <base/abc/abc.h>
#include <memory>
#include <optional>
#include <stdexcept>
#include <vector>

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

struct AbcPatternMux3 : AbcPatternMux2 {
	Abc_Obj_t *c1;
	bool c1n;
	Abc_Obj_t *v2;
	bool v2n;
};

std::optional<AbcPatternMux2> recognizeMux2(bool negated,
											Abc_Obj_t *top) noexcept(true);
std::optional<AbcPatternMux3> recognizeMux3(bool negated,
											Abc_Obj_t *top) noexcept(true);

/**
 * Recursively collect all inputs which connected using "and" and are not and
 * itself. :attention: it must be checked before that the top o is not just AND
 * to avoid rewriting AND using NOT ORs
 *
 * :note: in AIG "a | b" is "~(~a & ~b)"
 *     "a | (b | c)" is ~(~a & (~b & ~c))
 */
void collectOrMembers(
	Abc_Obj_t *o,
	std::vector<std::pair<Abc_Obj_t *, bool>> &result) noexcept(true);

template <typename ValueT> class AbcPatternRecognizer {
public:
	enum RecognizedOps {
		NOT,
		AND,
		OR,
		XOR,
		TERNARY,
		NOP, // placeholder, do noting eperator
	};
	// this represents node of expression DAG
	class RecognizedOpResult;
	class RecognizedOpResult {
	public:
		// used only if this is a term
		ValueT val;
		// used only if this is a operator node
		RecognizedOps op;
		std::vector<std::shared_ptr<RecognizedOpResult>> operands;

		RecognizedOpResult(ValueT val) :
			val(val), op(RecognizedOps::NOP) {}
		RecognizedOpResult(
			RecognizedOps op,
			std::vector<std::shared_ptr<RecognizedOpResult>> &&operands) :
			val(), op(op), operands(std::move(operands)) {}

		static inline std::shared_ptr<RecognizedOpResult> fromInitializerList(
			RecognizedOps op,
			std::initializer_list<std::shared_ptr<RecognizedOpResult>>
				opsList) {
			std::vector<std::shared_ptr<RecognizedOpResult>> operands;
			operands.reserve(opsList.size());
			for (auto &op_ : opsList) {
				operands.push_back(std::move(op_));
			}
			return std::make_shared<RecognizedOpResult>(op,
														std::move(operands));
		}
	};
	AbcPatternRecognizer() {}

	// this method should be implemented to construct translated object
	virtual ValueT _translate(Abc_Obj_t *o, bool negated) {
		throw std::runtime_error(
			"AbcPatternRecognizer::_translate should be overriden");
	};

	/*
	def _recognizeNonAigOperator(self, o: Abc_Obj_t, negated: bool):
		assert not o.IsComplement(), o
		m = recognizeMux3(negated, o)
		tr = self._translate
		if m is not None:
			res = (HwtOps.TERNARY, (tr(m.v0, m.v0n), tr(m.c0, m.c0n),
									tr(m.v1, m.v1n), tr(m.c1, m.c1n),
									tr(m.v2, m.v2n)))
			if m.isNegated:
				return (HwtOps.NOT, res)
			else:
				return res

		m = recognizeMux2(negated, o)
		if m is not None:
			res = (HwtOps.TERNARY, (tr(m.v0, m.v0n), tr(m.c0, m.c0n),
									tr(m.v1, m.v1n)))
			if m.isNegated:
				return (HwtOps.NOT, res)
			else:
				return res

		o0n = o.FaninC0()
		o1n = o.FaninC1()
		topIsOr = negated and o0n and o1n
		topP0, topP1 = o.IterFanin()

		if not topIsOr:
			# not: ~(p0 & p0)
			# not: (~p0 & ~p0)
			if topP0 == topP1 and ((negated and not o0n and not o1n) or
								   (not negated and o0n and o1n)):
				return HwtOps.NOT, (tr(topP0, False),)
			# or not o1n is there because the OR tree in AIG is made of ANDs and
	only leafs have not if ((topP0.IsPi() or not o0n) and (topP1.IsPi() or not
	o1n)): # if both operands are negated or PI try to search OR

				# or: ~(~p0 & ~p1 & ~p2 ...)
				orMembers = tuple(self._collectOrMembers(o))
				if orMembers:
					allArePis = all(op.IsPi() for op, _ in orMembers)
					if len(orMembers) > 2 or allArePis:
						if negated:
							if all(n for _, n in orMembers):
								# (~p0 | ~p1) -> ~(p0 & p1)
								return HwtOps.NOT, (HwtOps.AND, tuple(tr(p,
	int(not n)) for p, n in orMembers)) else: return HwtOps.OR, tuple(tr(p, n)
														for p, n in orMembers)
						elif sum(int(not n) for _, n in orMembers) >
	len(orMembers) // 2: # (~p0 & ~p1) -> ~(p0 | p1) return HwtOps.NOT,
	(HwtOps.OR, tuple(tr(p, n) for p, n in orMembers))

			return None

		# :note: top may be "or"
		if o0n and o1n and not topP0.IsPi() and not topP1.IsPi():
			P0o0n = topP0.FaninC0()
			P0o1n = topP0.FaninC1()
			P1o0n = topP1.FaninC0()
			P1o1n = topP1.FaninC1()
			P1o0, P1o1 = topP1.IterFanin()

			if (P0o0n + P0o1n) == 1 and (P1o0n + P1o1n) == 1:
				p0, p1 = topP0.IterFanin()
				if P0o0n:
					p0, p1 = p1, p0

				P1o0, P1o1 = topP1.IterFanin()
				if P1o0n:
					P1o0, P1o1 = P1o1, P1o0

				if p0 == P1o1 and p1 == P1o0:
					# xor: (p0 & ~p1) | (p1 & ~p0)
					return HwtOps.XOR, (tr(p0, False), tr(p1, False))

			elif not P0o0n and not P0o1n and (P1o0n + P1o1n) == 1:
				pc, p1 = topP0.IterFanin()  # both not negated
				P1o0, P1o1 = topP1.IterFanin()
				if not P1o0n:
					# swap to have negated input on left side of second operand
					P1o0, P1o1 = P1o1, P1o0
					P1o0n, P1o1n = P1o1n, P1o0n

				if pc == P1o0:  # is in format ((~)pC & P0o1) | ((~)pC & P1o1)
	(there is just 1 ~pC in expression) if pc == P1o1: # or: (pC & p1) | (~pC &
	pC) -> (pC & p1) res = HwtOps.AND, (tr(pc, False), tr(p1, False)) if
	negated: return res else: # ~(pC & p1) return HwtOps.NOT, res

		if o0n and o1n:
			# or:  ~(~p0 & ~p1)
			res = HwtOps.OR, (tr(topP0, False), tr(topP1, False))
			if negated:
				return res
			else:
				# or:  ~~(~p0 & ~p1) = ~(p0 | p1)
				return HwtOps.NOT, res
	*/

	/*
	 * Check if object is in format:
     * 
	 * xor: (p0 & ~p1) | (p1 & ~p0)
	 * mux: (pC & p1) | (~pC & p0)
	 * 	 (~pC | pT) & (pC | pF)
	 * 	 ...
	 * or:  ~(~p0 & ~p1), ~(~p0 & ~p1 & ~p2 ...)
	 * not: ~(p0 & p0)
	 * not: (~p0 & ~p0)
     * 
	 * * prioritize not and before or of negated
	 * * (~p0 | ~p1) -> ~(p0 & p1)
	 * * (~p0 & ~p1) -> ~(p0 | p1)
	*/
	virtual std::shared_ptr<RecognizedOpResult>
	_recognizeNonAigOperator(Abc_Obj_t *o, bool negated) {
		assert(!Abc_ObjIsComplement(o) && "o must not be complemented");

		auto tr = [&](Abc_Obj_t *obj, bool n) -> ValueT {
			return _translate(obj, n);
		};

		// Try 3-input MUX pattern
		if (auto m = recognizeMux3(negated, o)) {
			auto tern = RecognizedOpResult::fromInitializerList(
				TERNARY,
				{
					std::make_shared<RecognizedOpResult>(tr(m->v0, m->v0n)),
					std::make_shared<RecognizedOpResult>(tr(m->c0, m->c0n)),
					std::make_shared<RecognizedOpResult>(tr(m->v1, m->v1n)),
					std::make_shared<RecognizedOpResult>(tr(m->c1, m->c1n)),
					std::make_shared<RecognizedOpResult>(tr(m->v2, m->v2n)),
				});
			if (m->isNegated) {
				return RecognizedOpResult::fromInitializerList(
					NOT, {std::move(tern)});
			} else {
				return tern;
			}
		}

		// Try 2-input MUX pattern
		if (auto m = recognizeMux2(negated, o)) {
			auto tern = RecognizedOpResult::fromInitializerList(
				TERNARY,
				{
					std::make_shared<RecognizedOpResult>(tr(m->v0, m->v0n)),
					std::make_shared<RecognizedOpResult>(tr(m->c0, m->c0n)),
					std::make_shared<RecognizedOpResult>(tr(m->v1, m->v1n)),
				});
			if (m->isNegated) {
				return RecognizedOpResult::fromInitializerList(
					NOT, {std::move(tern)});
			} else {
				return tern;
			}
		}

		bool o0n = Abc_ObjFaninC0(o);
		bool o1n = Abc_ObjFaninC1(o);

		Abc_Obj_t *topP0 = Abc_ObjFanin0(o);
		Abc_Obj_t *topP1 = Abc_ObjFanin1(o);

		bool topIsOr = negated && o0n && o1n;

		if (!topIsOr) {
			// not: ~(p0 & p0)
			// not: (~p0 & ~p0)
			if (topP0 == topP1 &&
				((negated && !o0n && !o1n) || (!negated && o0n && o1n))) {
				return RecognizedOpResult::fromInitializerList(
					NOT,
					{std::make_shared<RecognizedOpResult>(tr(topP0, false))});
			}

			// Check if both operands are suitable for OR-tree search:
			// (topP0.IsPi() or not o0n) and (topP1.IsPi() or not o1n)
			if ((Abc_ObjIsPi(topP0) || !o0n) && (Abc_ObjIsPi(topP1) || !o1n)) {

				// Collect OR members
				std::vector<std::pair<Abc_Obj_t *, bool>> orMembers;
				collectOrMembers(o, orMembers);

				if (!orMembers.empty()) {
					bool allArePis = true;
					for (auto &[op, n] : orMembers) {
						if (!Abc_ObjIsPi(op)) {
							allArePis = false;
							break;
						}
					}

					if (orMembers.size() > 2 || allArePis) {
						if (negated) {
							// Check if all are negated: all(n for _, n in
							// orMembers)
							bool allNegated = true;
							for (auto &[op, n] : orMembers) {
								if (!n) {
									allNegated = false;
									break;
								}
							}
							if (allNegated) {
								// (~p0 | ~p1) -> ~(p0 & p1)
								std::vector<std::shared_ptr<RecognizedOpResult>>
									andOps;
								andOps.reserve(orMembers.size());
								for (auto &[p, n] : orMembers) {
									andOps.push_back(
										std::make_shared<RecognizedOpResult>(
											tr(p, !n)));
								}
								auto andNode =
									std::make_shared<RecognizedOpResult>(
										AND, std::move(andOps));
								return RecognizedOpResult::fromInitializerList(
									NOT, {std::move(andNode)});
							} else {
								// OR of members
								std::vector<std::shared_ptr<RecognizedOpResult>>
									orOps;
								orOps.reserve(orMembers.size());
								for (auto &[p, n] : orMembers) {
									orOps.push_back(
										std::make_shared<RecognizedOpResult>(
											tr(p, n)));
								}
								auto orNode =
									std::make_shared<RecognizedOpResult>(
										OR, std::move(orOps));
								return std::move(orNode);
							}
						} else {
							// Count how many are non-negated: sum(int(not n)
							// ...)
							std::size_t nonNegatedCount = 0;
							for (auto &[p, n] : orMembers) {
								if (!n)
									++nonNegatedCount;
							}
							if (nonNegatedCount > orMembers.size() / 2) {
								// (~p0 & ~p1) -> ~(p0 | p1)
								std::vector<std::shared_ptr<RecognizedOpResult>>
									orOps;
								orOps.reserve(orMembers.size());
								for (auto &[p, n] : orMembers) {
									orOps.push_back(
										std::make_shared<RecognizedOpResult>(
											tr(p, n)));
								}
								auto orNode =
									std::make_shared<RecognizedOpResult>(
										OR, std::move(orOps));
								return RecognizedOpResult::fromInitializerList(
									NOT, {std::move(orNode)});
							}
						}
					}
				}
			}

			// No pattern recognized
			return nullptr;
		}

		// From here: topIsOr == true (negated && o0n && o1n)
		// :note: top may be "or"
		if (o0n && o1n && !Abc_ObjIsPi(topP0) && !Abc_ObjIsPi(topP1)) {
			bool P0o0n = Abc_ObjFaninC0(topP0);
			bool P0o1n = Abc_ObjFaninC1(topP0);
			bool P1o0n = Abc_ObjFaninC0(topP1);
			bool P1o1n = Abc_ObjFaninC1(topP1);

			Abc_Obj_t *P1o0 = Abc_ObjFanin0(topP1);
			Abc_Obj_t *P1o1 = Abc_ObjFanin1(topP1);

			if ((P0o0n + P0o1n) == 1 && (P1o0n + P1o1n) == 1) {
				Abc_Obj_t *p0 = Abc_ObjFanin0(topP0);
				Abc_Obj_t *p1 = Abc_ObjFanin1(topP0);
				if (P0o0n) {
					std::swap(p0, p1);
				}

				P1o0 = Abc_ObjFanin0(topP1);
				P1o1 = Abc_ObjFanin1(topP1);
				if (P1o0n) {
					std::swap(P1o0, P1o1);
				}

				if (p0 == P1o1 && p1 == P1o0) {
					// xor: (p0 & ~p1) | (p1 & ~p0)
					return RecognizedOpResult::fromInitializerList(
						XOR,
						{
							std::make_shared<RecognizedOpResult>(tr(p0, false)),
							std::make_shared<RecognizedOpResult>(tr(p1, false)),
						});
				}
			} else if (!P0o0n && !P0o1n && (P1o0n + P1o1n) == 1) {
				// pc, p1 = topP0.IterFanin()  (both not negated)
				Abc_Obj_t *pc = Abc_ObjFanin0(topP0);
				Abc_Obj_t *p1 = Abc_ObjFanin1(topP0);

				P1o0 = Abc_ObjFanin0(topP1);
				P1o1 = Abc_ObjFanin1(topP1);

				if (!P1o0n) {
					// swap to have negated input on left side of second operand
					std::swap(P1o0, P1o1);
					std::swap(P1o0n, P1o1n);
				}

				if (pc == P1o0) {
					// is in format ((~)pC & P0o1) | ((~)pC & P1o1)
					if (pc == P1o1) {
						// or: (pC & p1) | (~pC & pC) -> (pC & p1)
						auto andNode = RecognizedOpResult::fromInitializerList(
							AND, {
									 std::make_shared<RecognizedOpResult>(
										 tr(pc, false)),
									 std::make_shared<RecognizedOpResult>(
										 tr(p1, false)),
								 });
						if (negated) {
							return andNode;
						} else {
							// ~(pC & p1)
							return RecognizedOpResult::fromInitializerList(
								NOT, {std::move(andNode)});
						}
					}
				}
			}
		}

		if (o0n && o1n) {
			// or:  ~(~p0 & ~p1)
			auto orNode = RecognizedOpResult::fromInitializerList(
				OR, {
						std::make_shared<RecognizedOpResult>(tr(topP0, false)),
						std::make_shared<RecognizedOpResult>(tr(topP1, false)),
					});
			if (negated) {
				return orNode;
			} else {
				// or:  ~~(~p0 & ~p1) = ~(p0 | p1)
				return RecognizedOpResult::fromInitializerList(
					NOT, {std::move(orNode)});
			}
		}

		// No pattern matched
		return nullptr;
	}
};

}
