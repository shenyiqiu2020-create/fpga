set root [file normalize [file join [file dirname [info script]] ..]]
set dir [file join $root compare_hls]
file mkdir $dir
foreach f {efficientad_engine.cpp efficientad_engine.h} {
    file copy -force [file join $root .. efficientad_full_pl_opt hls $f] [file join $dir $f]
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
set fixture [file join $root generated packed_tests.bin]
csim_design -argv [list $fixture 1000 24]
csynth_design
cosim_design -rtl verilog -tool xsim -argv [list $fixture 1000 24]
exit
