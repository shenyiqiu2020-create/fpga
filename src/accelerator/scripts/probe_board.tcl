connect -url tcp:127.0.0.1:3121
puts [targets]
set filter {name == "APU" && jtag_cable_serial == "210512180081"}
if {[llength [targets -target-properties -filter $filter]]==1} {
    targets -set -filter $filter
    puts "EA_PREVIOUS_CLOCK [mrd -force -value 0xF8000108 1] [mrd -force -value 0xF8000170 1]"
    puts "EA_PREVIOUS_STATUS [mrd -force -value 0x009D0080 17]"
}
disconnect
exit
