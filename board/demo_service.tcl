set root [file dirname [file dirname [info script]]]
source [file join $root board demo_addresses.tcl]
set command [lindex $argv 0]
connect -url tcp:127.0.0.1:3121
set cpu {name == "ARM Cortex-A9 MPCore #0" && jtag_cable_serial == "210512180081"}
set fpga_filter {name == "xc7z020" && jtag_cable_serial == "210512180081"}
set apu {name == "APU" && jtag_cable_serial == "210512180081"}
set discovery_deadline [expr {[clock milliseconds]+8000}]
while {[llength [targets -target-properties -filter $apu]]!=1} {
    if {[clock milliseconds]>$discovery_deadline} {error "Verified XC7Z020 board is not connected"}
    after 200
}
if {$command eq "init"} {
    if {[llength [targets -target-properties -filter $cpu]]!=1 || [llength [targets -target-properties -filter $fpga_filter]]!=1} {error "Unexpected JTAG target"}
    targets -set -filter $cpu
    rst -system
    after 1000
    targets -set -filter $cpu
    source [file join $root board ps7_init.tcl]
    ps7_init
    targets -set -filter $fpga_filter
    fpga -file [file join $root board efficientad_full.bit]
    targets -set -filter $cpu
    ps7_post_config
    dow [file join $root board efficientad_demo.elf]
    con
    after 300
}
targets -set -filter $apu
set c [mrd -force -value $DemoControl 16]
if {$command eq "init"} {
    set ready_deadline [expr {[clock milliseconds]+15000}]
    while {[lindex $c 0]!=0x45414432 || [lindex $c 13]!=1 || [lindex $c 14]!=0x4F563135} {
        if {[clock milliseconds]>$ready_deadline} {error "Demo firmware startup timed out: $c"}
        after 150
        set c [mrd -force -value $DemoControl 16]
    }
}
if {[lindex $c 0]!=0x45414432 || [lindex $c 13]!=1 || [lindex $c 14]!=0x4F563135} {error "Demo firmware is not ready; initialize the board first"}
if {$command eq "infer"} {
    if {[lindex $c 1]==1} {error "Board is busy"}
    set work [lindex $argv 1]
    set input [file join $work input.bin]
    if {[file size $input]!=524288} {error "Expected 256x256x8 input bytes"}
    # This installed XSDB requires an explicit word count for binary writes.
    mwr -force -bin -file $input $DemoInput 131072
    set seq [expr {([lindex $c 3]+1)&0xffffffff}]
    mwr -force [expr {$DemoControl+8}] $seq
    set deadline [expr {[clock milliseconds]+45000}]
    set previous -1
    while {1} {
        after 70
        set c [mrd -force -value $DemoControl 16]
        set step [lindex $c 4]
        if {$step!=$previous} {puts "EA_PROGRESS $step";flush stdout;set previous $step}
        if {[lindex $c 3]==$seq} {
            if {[lindex $c 1]!=2 || [lindex $c 5]!=0} {error "PL inference failed: $c"}
            break
        }
        if {[clock milliseconds]>$deadline} {error "Board inference timed out; reconnect before retry"}
    }
    mrd -force -bin -file [file join $work fused.bin] $DemoFused 3136
    mrd -force -bin -file [file join $work times.bin] $DemoTimes 29
}
puts "EA_CONTROL $c"
puts "EA_CLOCK [mrd -force -value 0xF8000108 1] [mrd -force -value 0xF8000170 1]"
disconnect
exit
