#pragma once

#include <llvm/CodeGen/MachineOperand.h>

namespace hwtHls {

/// MachineOperand::isIdenticalTo with dissabled compare of def and other flags except for isUndef
bool MachineOperand_isIdenticalTo_ignoringFlags(
		const llvm::MachineOperand &This, const llvm::MachineOperand &Other);
}
