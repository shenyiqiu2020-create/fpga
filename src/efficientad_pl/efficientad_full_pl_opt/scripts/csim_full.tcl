set root [file normalize [file join [file dirname [info script]] ..]]
cd [file join $root hls]
open_project full_model_csim
set_top efficientad_engine
add_files efficientad_engine.cpp
add_files -tb tb_full_model.cpp
open_solution sol -flow_target vivado
set_part xc7z020clg484-2
create_clock -period 20 -name default
csim_design -O
exit
