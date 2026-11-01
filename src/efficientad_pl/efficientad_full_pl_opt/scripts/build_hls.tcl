set root [file normalize [file join [file dirname [info script]] ..]]
set stage "csim"
if {[info exists ::env(EA_STAGE)]} {set stage $::env(EA_STAGE)}
cd [file join $root hls]
open_project engine_project
set_top efficientad_engine
add_files efficientad_engine.cpp
add_files -tb tb_engine.cpp
add_files -tb [file join $root generated engine_tests.bin]
open_solution sol -flow_target vivado
set_part xc7z020clg484-2
create_clock -period 20 -name default
set fixture [file join $root generated engine_tests.bin]
if {[info exists ::env(EA_FIXTURE)]} {set fixture $::env(EA_FIXTURE)}
if {$stage eq "csim" || $stage eq "all" || $stage eq "verify_cache"} {csim_design -argv [list $fixture]}
if {$stage eq "synth" || $stage eq "all"} {csynth_design}
if {$stage eq "cosim" || $stage eq "all"} {cosim_design -rtl verilog -tool xsim -argv [list $fixture]}
if {$stage eq "verify_cache"} {cosim_design -rtl verilog -tool xsim -argv [list $fixture 1000 18]}
if {$stage eq "package" || $stage eq "all"} {export_design -format ip_catalog -rtl verilog -display_name "EfficientAD DDR INT8 Engine"}
exit
