set root [file normalize [file join [file dirname [info script]] ..]]
set name efficientad_full
if {[llength $argv]} {set name [lindex $argv 0]}
if {$name ne "efficientad_full" && $name ne "baseline_profile"} {error "Unknown application"}
source [file join $root generated ${name}_addresses.tcl]
connect -url tcp:127.0.0.1:3121
set filter {name == "APU" && jtag_cable_serial == "210512180081"}
if {[llength [targets -target-properties -filter $filter]]!=1} {error "Expected one verified APU"}
targets -set -filter $filter
puts "EA_STATUS [mrd -force -value $EaStatus 17]"
puts "EA_TOTALS [mrd -force -value $EaTotals 32]"
puts "EA_PROFILE [mrd -force -value $EaProfile 580]"
puts "EA_CLOCK [mrd -force -value 0xF8000108 1] [mrd -force -value 0xF8000170 1]"
puts "EA_ARM_CLOCK [mrd -force -value 0xF8000100 1] [mrd -force -value 0xF8000120 1]"
disconnect
exit
