set root [file normalize [file join [file dirname [info script]] ..]]
foreach name {efficientad_full.bit efficientad_full.elf ps7_init.tcl} {
    if {![file exists [file join $root generated $name]]} {error "Missing artifact: $name"}
}
connect -url tcp:127.0.0.1:3121
set cpu_filter {name == "ARM Cortex-A9 MPCore #0" && jtag_cable_serial == "210512180081"}
set fpga_filter {name == "xc7z020" && jtag_cable_serial == "210512180081"}
if {[llength [targets -target-properties -filter $cpu_filter]]!=1 ||
    [llength [targets -target-properties -filter $fpga_filter]]!=1} {
    error "Expected one XC7Z020 + ARM0 on verified Digilent cable 210512180081"
}
targets -set -filter $cpu_filter
rst -system
after 1000
targets -set -filter $cpu_filter
source [file join $root generated ps7_init.tcl]
ps7_init
targets -set -filter $fpga_filter
fpga -file [file join $root generated efficientad_full.bit]
targets -set -filter $cpu_filter
ps7_post_config
dow [file join $root generated efficientad_full.elf]
con
puts "EA_FULL_LAUNCHED: watch COM11 115200 8N1 or read the DDR status mailbox."
disconnect
exit
