set root [file normalize [file join [file dirname [info script]] ..]]
source [file join $root generated mailbox.tcl]
connect -url tcp:127.0.0.1:3121
targets -set -filter {name == "APU" && jtag_cable_serial == "210512180081"}
puts "EA_STATUS [mrd -force -value $ea_status_address 16]"
disconnect
exit
