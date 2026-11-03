set root [file normalize [file join [file dirname [info script]] ..]]
set dir [file join $root baseline_hls]
file mkdir $dir
foreach f {efficientad_engine.cpp efficientad_engine.h} {
    set original [file join $root .. efficientad_full_pl hls $f]
    if {[file exists $original]} {file copy -force $original [file join $dir $f]}
    if {![file exists [file join $dir $f]]} {error "Missing preserved baseline source: $f"}
}
file copy -force [file join $root hls tb_engine.cpp] [file join $dir tb_engine.cpp]
if {![file exists [file join $dir vendor]]} {file copy [file join $root hls vendor] [file join $dir vendor]}
cd $dir
open_project engine_project
set_top efficientad_engine
add_files efficientad_engine.cpp
add_files -tb tb_engine.cpp
open_solution sol -flow_target vivado
set_part xc7z020clg484-2
create_clock -period 20 -name default
set fixture [file join $root generated cache_tests.bin]
csim_design -argv [list $fixture 1000 18]
csynth_design
cosim_design -rtl verilog -tool xsim -argv [list $fixture 1000 18]
exit
