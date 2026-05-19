#include <hwtHls/llvm/llvmIrStripInstrucionUnrelatedToCrash.h>

#include <optional>
#include <unistd.h>
#include <sys/wait.h>
#include <sys/time.h>
#include <sys/resource.h>
#include <sys/prctl.h>

#include <llvm/ADT/STLExtras.h>
#include <llvm/IR/Constants.h>
#include <llvm/IR/Instructions.h>
#include <llvm/IR/Verifier.h>
#include <llvm/IR/InstrTypes.h>
#include <llvm/Transforms/Utils/Local.h>

using namespace llvm;

// #define DEBUG_LOGS 1

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
	bool convertToFollowup() {
		if (opToReplaceWith.first) {
			if (auto C = dyn_cast<ConstantInt>(opToReplaceWith.first)) {
				if (C->isZero()) {
					// previously we were trying to replace with 0, now we try
					// with all-ones
					auto newC = ConstantInt::getAllOnesValue(
						opToReplaceWith.second->getType());
					opToReplaceWith.second = newC;
					return true;
				}
			}
		}
		return false;
	}

	void run(IRBuilderBase &Builder) {
		if (opToReplaceWith.first) {
			auto &I = *opToReplaceWith.first->getUser();
#ifndef NDEBUG
			auto ty = opToReplaceWith.first->get()->getType();
			assert(ty->isIntegerTy());
#endif
			I.setOperand(opToReplaceWith.first->getOperandNo(),
					opToReplaceWith.second);
		} else if (IToRm) {
			IToRm->eraseFromParent();
		} else if (IWithSingleNonConstOperand.first) {
			auto I = IWithSingleNonConstOperand.first;
			Value*src;
			if (isa<CastInst>(I)) {
				if (!isa<CastInst>(I->getOperand(0)))
					return; // operand was already replaced and it is no longer possible to apply this
				src = dyn_cast<CastInst>(I->getOperand(0))->getOperand(0);
			} else {
				src = I->getOperand(IWithSingleNonConstOperand.second);
			}
			
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
	#ifdef DEBUG_LOGS
		errs() << "child SIGSEGV\n";
	#endif
	// :note: _exit does not flushes buffers etc., it is used from performance reasons
	_exit(1);
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
		std::deque<InstructionStripWorkItem>& work) {
	nProcs = std::min(nProcs, work.size());
	std::vector<pid_t> children;
	for (size_t i = 0; i < nProcs; ++i) {
		pid_t pid = fork();
		if (pid < 0) {
			throw std::runtime_error("Unable to fork process");
		} else if (pid == 0) {
			// child process
			
			// disable core dumps to prevent slow termination on SIGSEGV
			struct rlimit rl = {0, 0};// current soft limit,  hard limit
			setrlimit(RLIMIT_CORE, &rl);
			prctl(PR_SET_DUMPABLE, 0);
			
			for (size_t _i = 0; _i < i + 1; _i++) {
				// apply all updates from start to index of this process in work list
				work[_i].run(ctx.builder);
			}
			signal(SIGSEGV, segfault_handler);
			testFn(ctx);
			#ifdef DEBUG_LOGS
				errs() << "child SUCCESS\n";
			#endif
			
			if (verifyModule(*ctx.module, &errs())) {
				_exit(2);
			}
			_exit(EXIT_SUCCESS);
		} else {
			// parent process
			children.push_back(pid);
		}
	}

	#ifdef DEBUG_LOGS
		errs() << "tryIfPreservesCrash forked \n";
	#endif
	bool foundChildrenWhichDoesNotCrash = false;
	size_t crashedChildren = 0;
	for (auto c_pid : children) {
		int status;
		waitpid(c_pid, &status, 0);
		// :note: WIFEXITED returns true if process exited normally
		if (WIFEXITED(status) && WEXITSTATUS(status) == EXIT_SUCCESS) {
			foundChildrenWhichDoesNotCrash = true;
		} else {
			if (!foundChildrenWhichDoesNotCrash)
				crashedChildren++;
		}
	}
	#ifdef DEBUG_LOGS
		errs() << "tryIfPreservesCrash child waited \n";
	#endif

	return crashedChildren; // = number of updates from "work" which we can apply and the compilation is still crashing
}

// :note: this function always removes some items from "udpates" or replaces them by followup
static size_t runApplyRemoveUpdates(LlvmCompilationBundle &ctx, size_t nProcs,
		std::function<void(LlvmCompilationBundle&)> testFn,
		std::deque<InstructionStripWorkItem> &updates) {
	#ifdef DEBUG_LOGS
		errs() << "runApplyRemoveUpdates " << updates.size() << "\n";
	#endif
	// test if update are preserving crash in child processes
	size_t removableOps = tryIfPreservesCrash(ctx, nProcs, testFn, updates);
	// apply updates which are preserving the crash
	for (size_t i = 0; i < removableOps; ++i) {
		updates[i].run(ctx.builder);
	}
	auto toRemoveCnt = removableOps;
	// remove processed updates
	if (removableOps < updates.size()) {
		auto notAppliableUpdate = updates[removableOps];
		// check if non appliable update has some followup
		if (!notAppliableUpdate.convertToFollowup()) {
			// remove also the notAppliableUpdate because it has no followup
			toRemoveCnt += 1;
		}
		updates.erase(updates.begin(), updates.begin() + toRemoveCnt);
	} else {
		// all updates were applied
		assert(removableOps == updates.size());
		updates.clear();
	}
	#ifdef DEBUG_LOGS
		errs() << "runApplyRemoveUpdates end" << removableOps << "\n";
	#endif
	return removableOps;
}

void llvmIrStripInstrucionUnrelatedToCrash(LlvmCompilationBundle &ctx,
		size_t nProcs, std::function<void(LlvmCompilationBundle&)> testFn, bool logAfterChange) {
	size_t removedCnt = 0;
	std::deque<InstructionStripWorkItem> removes;
	//removes.reserve(nProcs);
	const TargetLibraryInfo *TLI = nullptr;
	size_t iterationCount = 0;
	for (;;) {
		bool change = false;

		for (BasicBlock &BB : reverse(*ctx.main)) {
			for (Instruction &I : make_early_inc_range(reverse(BB))) {
				for (Use &op : reverse(I.operands())) {
					auto ty = op.get()->getType();
					if (ty->isIntegerTy() && !isa<Constant>(op.get())) {
						// try replacing with 0
						removes.push_back(InstructionStripWorkItem(op, *ConstantInt::get(ty, 0)));
						
						// if there are enough updates to run updates in child workers
						if (removes.size() >= nProcs) {
							auto removableCnt = runApplyRemoveUpdates(ctx,
									nProcs, testFn, removes);
							change |= bool(removableCnt);
							removedCnt += removableCnt;
							if (removableCnt)
								errs() << "removedCnt: " << removedCnt << "\n";
							if (removableCnt && logAfterChange) {
								errs() << "iteration:" << iterationCount << "\n" << *ctx.main << "\n";
								iterationCount++; 
							}
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
				} else if (I.getType()->isIntegerTy() && (!isa<CastInst>(&I) || isa<CastInst>(I.getOperand(0))) && !isa<PHINode>(&I)) {
					// try to replace this instruction with just zext of only
					// non const arg
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
				} else if (!I.isTerminator() && I.hasNUses(0)) {
					// case for instructions with sideeffect which are not dead but potentially removable
					removes.push_back(InstructionStripWorkItem(I));
				}
				if (removes.size() >= nProcs) {
					auto removableCnt = runApplyRemoveUpdates(ctx, nProcs,
							testFn, removes);
					change |= bool(removableCnt);
					errs() << "removedCnt (instr): " << removedCnt << "\n";
					removedCnt += removableCnt;
					if (removableCnt && logAfterChange) {
						errs() << "iteration:" << iterationCount << "\n" << *ctx.main << "\n";
						iterationCount++; 
					}
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
			if (removableCnt && logAfterChange) {
				errs() << "iteration:" << iterationCount << "\n" << *ctx.main << "\n";
				iterationCount++; 
			}
		}

		if (!change)
			break;
	}
}

}
