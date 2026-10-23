#pragma once

#include <llvm/IR/Value.h>
#include <llvm/ADT/SetVector.h>
#include <llvm/IR/BasicBlock.h>

// ABC includes (as provided)
#include <aig/aig/aig.h>
#include <base/abc/abc.h>
#include <base/main/abcapis.h>

namespace hwtHls {

/**
 * Translate fragment (DAG) of LLVM IR (1-bit logic only) to an
 * ABC AIG network.
 *
 * :see: ``RtlNetlistToAbcAig``
 * 
 * Supported instructions ``i1`` result and operands:
 * - ``BinaryOperator``: ``and``, ``or``, ``xor``
 * - ``SelectInst``
 * - ``ICmpInst`` ``eq``, ``ne``
 */
class LlvmIrToAbcAig {
public:
	Abc_Frame_t *abcFrame = nullptr; // Global ABC frame.
	Abc_Ntk_t *net = nullptr;		 // ABC network.
	Abc_Aig_t *aig = nullptr;		 // AIG manager (net->pManFunc).
	std::unordered_map<llvm::Value *, Abc_Obj_t *> translationCache;
	std::unordered_map<std::string, llvm::Value *>
		ioMap;

public:
	LlvmIrToAbcAig();
	Abc_Obj_t *translateInstructionImpl(llvm::Instruction *I);

	/**
	 * :note: This function assumes that ``I`` all
	 * operands have already been translated or registered as inputs.
	 */
	void translateInstruction(llvm::Instruction *I);

	/**
	 * Translate a DAG of LLVM IR instructions to an ABC AIG.
	 * 
	 * :note: inputs are not part of DAG, outputs are 
	 */
	void
	translate(const llvm::SetVector<llvm::Value *> &inputs,
			  const llvm::SetVector<llvm::Instruction *> &outputs);

	/**
	 * Utility to translate or return cached value
	 */
	Abc_Obj_t *getOrTranslateValue(llvm::Value *v);
	~LlvmIrToAbcAig();
};

}