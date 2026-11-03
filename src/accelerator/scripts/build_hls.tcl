set root [file normalize [file join [file dirname [info script]] ..]]
set stage "csim"
if {[info exists ::env(EA_STAGE)]} {set stage $::env(EA_STAGE)}
# Start every synthesis in a fresh solution. Existing HLS implementation
# caches can otherwise preserve old RTL even after syn/verilog is refreshed.
if {$stage eq "prepare" || $stage eq "synth" || $stage eq "all"} {
    set solution [file normalize [file join $root hls engine_project sol]]
    set archive [file normalize [file join $root _build solution_before_synth_[clock seconds]]]
    if {[string first "${root}/" $solution]!=0 || [string first "${root}/" $archive]!=0} {error "Solution paths escaped this project"}
    if {[file exists $solution]} {file mkdir [file dirname $archive];file rename $solution $archive}
}
cd [file join $root hls]
open_project engine_project
set_top efficientad_engine
add_files efficientad_engine.cpp
add_files -tb tb_engine.cpp
add_files -tb [file join $root generated engine_tests.bin]
open_solution sol -flow_target vivado
set_part xc7z020clg484-2
create_clock -period 8 -name default
config_interface -m_axi_addr64=false
set fixture [file join $root generated engine_tests.bin]
if {[info exists ::env(EA_FIXTURE)]} {set fixture $::env(EA_FIXTURE)}
if {$stage eq "csim" || $stage eq "all" || $stage eq "verify_cache" || $stage eq "verify_packed" || $stage eq "prepare"} {csim_design -argv [list $fixture]}
if {$stage eq "tail_csim"} {csim_design -argv [list $fixture 1000 27]}
if {$stage eq "synth" || $stage eq "all" || $stage eq "prepare"} {csynth_design}
if {$stage eq "cosim" || $stage eq "all"} {cosim_design -rtl verilog -tool xsim -argv [list $fixture]}
if {$stage eq "verify_cache"} {cosim_design -rtl verilog -tool xsim -argv [list $fixture 1000 18]}
if {$stage eq "verify_packed"} {cosim_design -rtl verilog -tool xsim -argv [list $fixture 1000 24]}
if {$stage eq "verify_compute"} {cosim_design -rtl verilog -tool xsim -argv [list $fixture 1000 0 conv]}
if {$stage eq "package" || $stage eq "all" || $stage eq "prepare"} {
    set impl [file normalize [file join $root hls engine_project sol impl]]
    export_design -format ip_catalog -rtl verilog -display_name "EfficientAD Overlapped PE40 125MHz INT8 Engine"
    exec C:/Users/sheny/anaconda3/python.exe [file join $root scripts sync_export_rtl.py]
}
exit
