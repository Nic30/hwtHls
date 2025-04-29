#pragma once

#include <map>
#include <set>
#include <memory>
#include <llvm/IR/IRBuilder.h>
#include <llvm/IR/Instructions.h>

namespace hwtHls {

template<typename T>
std::shared_ptr<std::set<T>> mergeGroups(
		std::map<T, std::shared_ptr<std::set<T>>> &phiGroups,
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

using CreateBitRangeGetFn = std::function<llvm::Value* (llvm::IRBuilderBase *Builder, llvm::Value *bitVec,
		size_t lowBitNo, size_t bitWidth)>;

struct InstructionPtrNameGetter {
	llvm::StringRef operator()(llvm::Instruction *I) {
		return I->getName();
	}
};

template<typename nameGetterTy, typename InstrSequenceTy>
std::string resolveNameForMergedInstructions(
		const InstrSequenceTy &instructions) {
	auto getCommonPrefix = [](llvm::StringRef str0,
			llvm::StringRef str1) -> std::string {
		auto strlen0 = str0.size();
		auto strlen1 = str1.size();

		for (unsigned i = 0;; ++i) {
			auto c0 = i < strlen0 ? str0[i] : '\0';
			auto c1 = i < strlen1 ? str1[i] : '\n';
			if (c0 != c1) {
				bool diffIsIdSuffix = true;
				for (char c : { c0, c1 }) {
					switch (c) {
					case '\0':
					case '_':
					case '.':
					case ',':
					case ';':
					case ' ':
					case '0':
					case '1':
					case '2':
					case '3':
					case '4':
					case '5':
					case '6':
					case '7':
					case '8':
					case '9':
						break;
					default:
						diffIsIdSuffix = false;
						break;
					}
					if (diffIsIdSuffix)
						break;
				}
				if (diffIsIdSuffix)
					return str0.substr(0, i).str();
				else
					return "";
			} else if (c0 == '\0') {
				return str0.str();
			} else if (c1 == '\0') {
				return str1.str();
			}
		}
		return "";
	};
	std::string name;
	for (auto &I : instructions) {
		auto partName = nameGetterTy()(I);
		if (!partName.empty()) {
			if (name.empty()) {
				name = partName;
			} else {
				name = getCommonPrefix(name, partName);
				if (name.empty())
					return name; // we just resolved that it is not possible to infer any name
			}
		}
	}
	return name;
}

}

