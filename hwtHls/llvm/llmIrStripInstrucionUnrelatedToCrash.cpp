#include <hwtHls/llvm/llmIrStripInstrucionUnrelatedToCrash.h>
#include <unistd.h>
#include <sys/wait.h>

#include <llvm/Transforms/Utils/Local.h>

using namespace llvm;

namespace hwtHls {

class InstructionStripWorkItem {
public:
	// use to replace with value
	std::pair<Use *, Value*> opToReplaceWith;
	// instruction to remove
	Instruction *IToRm;
	// instruction known to have just one non constant operand,
	// attempt to replace with trunc/zext
	std::pair<Instruction*, size_t> IWithSingleNonConstOperand;

	InstructionStripWorkItem(Use &op, Value&replacement) :
			opToReplaceWith({&op, &replacement}), IToRm(nullptr), IWithSingleNonConstOperand( {
					nullptr, 0 }) {
	}
	InstructionStripWorkItem(Instruction &I) :
			opToReplaceWith({nullptr, nullptr}), IToRm(&I), IWithSingleNonConstOperand( {
					nullptr, 0 }) {
	}
	InstructionStripWorkItem(Instruction &I, size_t onlyNonConstOperand) :
			opToReplaceWith({nullptr, nullptr}), IToRm(nullptr), IWithSingleNonConstOperand(
					{ &I, onlyNonConstOperand }) {
	}

	void run(IRBuilderBase &Builder) {
		if (opToReplaceWith.first) {
			auto &I = *opToReplaceWith.first->getUser();
			auto ty = opToReplaceWith.first->get()->getType();
			assert(ty->isIntegerTy());
			I.setOperand(opToReplaceWith.first->getOperandNo(),
					opToReplaceWith.second);
		} else if (IToRm) {
			IToRm->eraseFromParent();
		} else if (IWithSingleNonConstOperand.first) {
			auto I = IWithSingleNonConstOperand.first;
			assert(!isa<TruncInst>(I) && !isa<ZExtInst>(I));
			auto src = I->getOperand(IWithSingleNonConstOperand.second);
			Builder.SetInsertPoint(I);
			auto replacement = Builder.CreateZExtOrTrunc(src, I->getType());
			I->replaceAllUsesWith(replacement);
			I->eraseFromParent();
		} else {
			llvm_unreachable(
					"InstructionStripWork: All cases should be already checked");
		}
	}
};

void segfault_handler(int signal) {
	exit(1);
}

/*
 * This function applies update and checks testFn in child process.
 * Child process is required because this function check primarily for segfaults and alike
 * which destroy process memory.
 *
 * :note: This function speculatively tries multiple updates in multiple threads to overcome
 * process spin up delay.
 * Each process applies n updates where n is its index.
 * */
static size_t tryIfPreservesCrash(LlvmCompilationBundle &ctx, size_t nProcs,
		const std::function<void(LlvmCompilationBundle&)> &testFn,
		std::vector<InstructionStripWorkItem> work) {
	nProcs = std::min(nProcs, work.size());
	std::vector<pid_t> children;
	for (size_t i = 0; i < nProcs; ++i) {
		pid_t pid = fork();
		if (pid < 0) {
			throw std::runtime_error("Unable to fork process");
		} else if (pid == 0) {
			// child process
			for (size_t _i = 0; _i < i + 1; _i++) {
				// apply all updates from start to index of this process in work list
				work[_i].run(ctx.builder);
			}
			signal(SIGSEGV, segfault_handler);
			testFn(ctx);
			exit(EXIT_SUCCESS);
		} else {
			// parent process
			children.push_back(pid);
		}
	}
	bool foundChildrenWhichDoesNotCrash = false;
	size_t crashedChildren = 0;
	for (auto c_pid : children) {
		int status;
		waitpid(c_pid, &status, 0);
		// :note: WIFEXITED returns true if process exited normally
		if (WIFEXITED(status)) {
			foundChildrenWhichDoesNotCrash = true;
		} else {
			if (!foundChildrenWhichDoesNotCrash)
				crashedChildren++;
		}
	}
	return crashedChildren;
}

static size_t runApplyRemoveUpdates(LlvmCompilationBundle &ctx, size_t nProcs,
		std::function<void(LlvmCompilationBundle&)> testFn,
		std::vector<InstructionStripWorkItem> &updates) {
	// test if update are preserving crash in child processes
	size_t removableOps = tryIfPreservesCrash(ctx, nProcs, testFn, updates);
	// apply updates which are preserving the crash
	for (size_t i = 0; i < removableOps; ++i) {
		updates[i].run(ctx.builder);
	}
	// remove processed updates
	if (removableOps < updates.size()) {
		auto notAppliableUpdate = updates[removableOps];
		bool notAppliableUpdateChanged = false;
		if (notAppliableUpdate.opToReplaceWith.first) {
			if (auto C = dyn_cast<ConstantInt>(notAppliableUpdate.opToReplaceWith.first)) {
				if (C->isZero()) {
					auto newC = ConstantInt::getAllOnesValue(notAppliableUpdate.opToReplaceWith.second->getType());
					notAppliableUpdate.opToReplaceWith.second = newC;
					notAppliableUpdateChanged = true;
				}
			}
		}
		if (notAppliableUpdateChanged) {
			updates.erase(updates.begin(), updates.begin() + removableOps);
		} else {
			// skip also the first non appliable update
			updates.erase(updates.begin(), updates.begin() + removableOps + 1);
		}
	} else {
		// all updates were applied
		updates.clear();
	}
	return removableOps;
}

void llmIrStripInstrucionUnrelatedToCrash(LlvmCompilationBundle &ctx,
		size_t nProcs, std::function<void(LlvmCompilationBundle&)> testFn) {
	size_t removedCnt = 0;
	std::vector<InstructionStripWorkItem> removes;
	removes.reserve(nProcs);
	const TargetLibraryInfo *TLI = nullptr;
	for (;;) {
		bool change = false;

		for (BasicBlock &BB : reverse(*ctx.main)) {
			for (Instruction &I : make_early_inc_range(reverse(BB))) {
				for (Use &op : reverse(I.operands())) {
					auto ty = op.get()->getType();
					if (ty->isIntegerTy() && !isa<Constant>(op.get())) {
						// stag update for later
						removes.push_back(InstructionStripWorkItem(op, *ConstantInt::get(ty, 0)));
						if (removes.size() >= nProcs) {
							auto removableCnt = runApplyRemoveUpdates(ctx,
									nProcs, testFn, removes);
							change |= bool(removableCnt);
							removedCnt += removableCnt;
							if (removableCnt)
								errs() << "removedCnt: " << removedCnt << "\n";
						}
					}
				}
				// [todo] if this is the concatenation try remove bits entirely
				//        sometimes it is important that operand values are next to each other and just replacing one with constant
				//        is not sufficient
				// [todo] if this is SwitchInst/conditional BranchInst try remove successors
				// [todo] if this is the terminator try replacing it with ret (and rm successor PHINode operands)
				if (isInstructionTriviallyDead(&I, TLI)) {
					// stag update for later
					removes.push_back(InstructionStripWorkItem(I));
				} else if (!isa<TruncInst>(&I) && !isa<ZExtInst>(&I)
						&& I.getType()->isIntegerTy()) {
					// try to replace this instruction with just zext of only non const arg
					std::optional<size_t> nonConstOpIndex;
					for (auto &O : I.operands()) {
						if (!isa<Constant>(O.get())) {
							if (!O.get()->getType()->isIntegerTy()) {
								nonConstOpIndex = { };
								break; // operand is not int, can not convert to zext/sext
							}
							if (nonConstOpIndex.has_value()) {
								nonConstOpIndex = { };
								break; // this instruction has multiple non constant operands
							}
							nonConstOpIndex = O.getOperandNo();
						}
					}
					if (nonConstOpIndex.has_value()) {
						removes.push_back(
								InstructionStripWorkItem(I,
										nonConstOpIndex.value()));
					}
				}
				if (removes.size() >= nProcs) {
					auto removableCnt = runApplyRemoveUpdates(ctx, nProcs,
							testFn, removes);
					change |= bool(removableCnt);
					errs() << "removedCnt (instr): " << removedCnt << "\n";
					removedCnt += removableCnt;
				}
			}
		}
		// [todo] if block is not reachable try remove it
		// [todo] if block has only a single successor which has only a single predecessor try merging src and dst block if src!=dst
		while (!removes.empty()) {
			auto removableCnt = runApplyRemoveUpdates(ctx, nProcs, testFn,
					removes);
			change |= bool(removableCnt);
			errs() << "removedCnt (leftover): " << removedCnt << "\n";
			removedCnt += removableCnt;
		}

		if (!change)
			break;
	}
}

}
