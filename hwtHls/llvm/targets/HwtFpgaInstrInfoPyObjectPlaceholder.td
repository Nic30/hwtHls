
// Placeholder instruction for netlist object which will be aded later in translation
// inputs are in format  // in format [objId, dstOperandWidth, *srcOperands, *srcOperandWidths]
def HWTFPGA_PYOBJECT_PLACEHOLDER: HwtFpgaInst<
    (outs anyregcls:$dst),
    (ins variable_ops),
    []> {
    	let hasSideEffects = false;
		let isNotDuplicable = false;
    }

def HWTFPGA_PYOBJECT_PLACEHOLDER_WITH_SIDEEFFECT: HwtFpgaInst<
    (outs anyregcls:$dst),
    (ins variable_ops),
    []> {
    	let hasSideEffects = true;
		let isNotDuplicable = false;
    }
def HWTFPGA_PYOBJECT_PLACEHOLDER_NOTDUPLICABLE: HwtFpgaInst<
    (outs anyregcls:$dst),
    (ins variable_ops),
    []> {
    	let hasSideEffects = false;
		let isNotDuplicable = true;
    }
    
def HWTFPGA_PYOBJECT_PLACEHOLDER_NOTDUPLICABLE_WITH_SIDEEFECT: HwtFpgaInst<
    (outs anyregcls:$dst),
    (ins variable_ops),
    []> {
    	let hasSideEffects = true;
		let isNotDuplicable = true;
    }
     
