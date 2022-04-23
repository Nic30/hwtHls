
generated_llvm_backend_files = [
	#['GenericFpgaGenCallingConv.inc', '-gen-callingconv'],
	['GenericFpgaGenDAGISel.inc', '-gen-dag-isel'],
	#['GenericFpgaGenFastISel.inc', '-gen-fast-isel'],
	['GenericFpgaGenInstrInfo.inc', '-gen-instr-info'],
	['GenericFpgaGenRegisterInfo.inc', '-gen-register-info'],
	['GenericFpgaGenSubtargetInfo.inc', '-gen-subtarget'],
]

all_llvm_backend_gen_files = []
foreach f : generated_llvm_backend_files
	gen_src = custom_target(f[0],
	                        input : ['GenericFpgaInstrInfo.td', 'GenericFpgaRegisterInfo.td', 'GenericFpga.td'],
	                        output : [f[0], ],
	                        command : [llvm_tblgen,
	                        	'-I', llvm_dep.get_variable('includedir', default_value: '/usr/lib/llvm-13/include'),
	                            '-I', meson.current_source_dir(),
	                        	meson.current_source_dir()+'/GenericFpga.td', f[1], '-o=@OUTPUT0@'])
    all_llvm_backend_gen_files += gen_src 
endforeach