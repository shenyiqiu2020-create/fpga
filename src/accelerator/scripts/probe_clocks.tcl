set root [file normalize [file join [file dirname [info script]] ..]]
create_project clock_probe [file join $root _build clock_probe] -part xc7z020clg484-2
create_bd_design ps_probe
create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:5.5 ps
source [file join $root generated ps_config.tcl]
foreach p {PCW_ACT_FPGA0_PERIPHERAL_FREQMHZ PCW_CPU_CPU_PLL_FREQMHZ PCW_IO_IO_PLL_FREQMHZ PCW_DDR_DDR_PLL_FREQMHZ PCW_ACT_UART_PERIPHERAL_FREQMHZ} {
    puts "EA_CLOCK_PROPERTY $p [get_property CONFIG.$p [get_bd_cells ps]]"
}
report_property -all [get_bd_cells ps] -file [file join $root generated ps125_properties.rpt]
close_project
exit
