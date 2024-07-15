#pragma once
#include <unordered_map>
#include <llvm/IR/BasicBlock.h>

// :note: taken from boost
template<class T>
inline void hash_combine(std::size_t &seed, const T &v) {
	std::hash<T> hasher;
	seed ^= hasher(v) + 0x9e3779b9 + (seed << 6) + (seed >> 2);
}

// http://stackoverflow.com/a/1646913/126995
template<>
struct std::hash<std::pair<llvm::BasicBlock*, llvm::BasicBlock*>> {
	std::size_t operator()(const std::pair<llvm::BasicBlock*, llvm::BasicBlock*> &k) const {
		std::size_t res = 0;
		hash_combine(res, hash<llvm::BasicBlock*>()(k.first));
		hash_combine(res, hash<llvm::BasicBlock*>()(k.second));
		return res;
	}
};
