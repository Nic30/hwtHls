#pragma once

#include <map>
#include <set>
#include <memory>
#include <llvm/IR/IRBuilder.h>
#include <llvm/IR/Instructions.h>

namespace hwtHls {

template<typename T>
std::shared_ptr<std::set<T>> mergeGroups(std::map<T, std::shared_ptr<std::set<T>>> &phiGroups,
		std::shared_ptr<std::set<T>> g0, std::shared_ptr<std::set<T>> g1) {
	if (g0->size() > g1->size()) {
		// swap to merge smaller to larger group from performance reasons
		std::swap(g0, g1);
	}
	for (auto &obj : *g0) {
		phiGroups[obj] = g1;
		g1->insert(obj);
	}
	return g1;
}


using CreateBitRangeGetFn = std::function<llvm::Value* (llvm::IRBuilder<> *Builder, llvm::Value *bitVec,
		size_t lowBitNo, size_t bitWidth)>;

}
