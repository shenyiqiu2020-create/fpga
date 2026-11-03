# Creates ONLY this package's new project. Does not open/edit the old project.
set root [file normalize [file join [file dirname [info script]] ..]]
set ipdir [file join $root hls engine_project sol impl ip]
if {![file exists [file join $ipdir component.xml]]} {error "Package HLS IP first: missing $ipdir/component.xml"}
set work [file normalize [file join $root _build vivado]]
set xpr [file join $work ea_full.xpr]
# Always import this build's IP into a fresh project. Reopening a completed
# project can retain an earlier HLS IP and skip the implementation run.
if {[file exists $xpr]} {
    set archive [file normalize [file join $root _build vivado_before_build_[clock seconds]]]
    if {[string first "${root}/" $work]!=0 || [string first "${root}/" $archive]!=0} {error "Vivado paths escaped this project"}
    file rename $work $archive
}
file mkdir $work
create_project ea_full $work -part xc7z020clg484-2
set_property ip_repo_paths [list $ipdir] [current_project]
update_ip_catalog
create_bd_design design_full
create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:5.5 ps
source [file join $root generated ps_config.tcl]
set actual_mhz [get_property CONFIG.PCW_ACT_FPGA0_PERIPHERAL_FREQMHZ [get_bd_cells ps]]
if {abs($actual_mhz-125.0)>0.001} {error "PS clock is $actual_mhz MHz, not 125 MHz"}
create_bd_cell -type ip -vlnv xilinx.com:hls:efficientad_engine:1.0 engine
create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect:1.0 ctrl_smc
create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect:1.0 mem_smc
foreach block {ctrl_smc mem_smc} {
    set_property -dict [list CONFIG.NUM_SI {1} CONFIG.NUM_MI {1}] [get_bd_cells $block]
}
create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 rst
set_property CONFIG.C_EXT_RESET_HIGH {0} [get_bd_cells rst]
create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 one
set_property -dict [list CONFIG.CONST_WIDTH {1} CONFIG.CONST_VAL {1}] [get_bd_cells one]
create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 zero
set_property -dict [list CONFIG.CONST_WIDTH {1} CONFIG.CONST_VAL {0}] [get_bd_cells zero]
make_bd_intf_pins_external [get_bd_intf_pins ps/DDR]
make_bd_intf_pins_external [get_bd_intf_pins ps/FIXED_IO]
connect_bd_intf_net [get_bd_intf_pins ps/M_AXI_GP0] [get_bd_intf_pins ctrl_smc/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins ctrl_smc/M00_AXI] [get_bd_intf_pins engine/s_axi_control]
connect_bd_intf_net [get_bd_intf_pins engine/m_axi_ddr] [get_bd_intf_pins mem_smc/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins mem_smc/M00_AXI] [get_bd_intf_pins ps/S_AXI_HP0]
connect_bd_net [get_bd_pins ps/FCLK_CLK0] [get_bd_pins ps/M_AXI_GP0_ACLK] \
    [get_bd_pins ps/S_AXI_HP0_ACLK] [get_bd_pins engine/ap_clk] \
    [get_bd_pins ctrl_smc/aclk] [get_bd_pins mem_smc/aclk] [get_bd_pins rst/slowest_sync_clk]
connect_bd_net [get_bd_pins ps/FCLK_RESET0_N] [get_bd_pins rst/ext_reset_in]
connect_bd_net [get_bd_pins one/dout] [get_bd_pins rst/dcm_locked] [get_bd_pins rst/aux_reset_in]
connect_bd_net [get_bd_pins zero/dout] [get_bd_pins rst/mb_debug_sys_rst]
connect_bd_net [get_bd_pins rst/interconnect_aresetn] [get_bd_pins ctrl_smc/aresetn] [get_bd_pins mem_smc/aresetn]
connect_bd_net [get_bd_pins rst/peripheral_aresetn] [get_bd_pins engine/ap_rst_n]
assign_bd_address
set controls [get_bd_addr_segs -of_objects [get_bd_addr_spaces ps/Data]]
if {[llength $controls]!=1} {error "Unexpected PS control address map: $controls"}
set_property offset 0x43C00000 $controls
set_property range 64K $controls
validate_bd_design
save_bd_design
set bd [get_files */design_full.bd]
generate_target all $bd
set wrappers [make_wrapper -files $bd -top]
add_files -norecurse $wrappers
set_property top design_full_wrapper [current_fileset]
update_compile_order -fileset sources_1
set_property STEPS.PLACE_DESIGN.ARGS.DIRECTIVE Explore [get_runs impl_1]
set_property STEPS.PHYS_OPT_DESIGN.IS_ENABLED true [get_runs impl_1]
set_property STEPS.PHYS_OPT_DESIGN.ARGS.DIRECTIVE AggressiveFanoutOpt [get_runs impl_1]
set_property STEPS.PHYS_OPT_DESIGN.TCL.PRE [file join $root scripts replicate_control.tcl] [get_runs impl_1]
set_property STEPS.ROUTE_DESIGN.ARGS.DIRECTIVE Explore [get_runs impl_1]
set_property STEPS.POST_ROUTE_PHYS_OPT_DESIGN.IS_ENABLED true [get_runs impl_1]
set_property STEPS.POST_ROUTE_PHYS_OPT_DESIGN.ARGS.DIRECTIVE AggressiveExplore [get_runs impl_1]
if {![string match "*Complete*" [get_property STATUS [get_runs impl_1]]]} {
    launch_runs impl_1 -to_step write_bitstream -jobs 4
    wait_on_run impl_1
}
set bit [file join $work ea_full.runs impl_1 design_full_wrapper.bit]
if {![file exists $bit]} {error "No new bitstream. Inspect synthesis/implementation errors under $work"}
open_run impl_1
report_utilization -file [file join $root generated vivado_utilization.rpt]
report_timing_summary -file [file join $root generated vivado_timing.rpt]
set slack [get_property SLACK [get_timing_paths -delay_type max -max_paths 1]]
if {$slack<0} {error "Timing not met: WNS=$slack; XSA not exported"}
set hold [get_property SLACK [get_timing_paths -delay_type min -max_paths 1]]
if {$hold<0} {error "Hold timing not met: WHS=$hold; XSA not exported"}
set period [get_property PERIOD [get_clocks clk_fpga_0]]
if {abs($period-8.0)>0.002} {error "Unexpected implemented clock period: $period"}
file copy -force $bit [file join $root generated efficientad_full.bit]
write_hw_platform -fixed -include_bit -force [file join $root generated ax7021_efficientad_full.xsa]
puts "EA_FULL_BUILD_SUCCESS: [file join $root generated ax7021_efficientad_full.xsa], WNS=$slack"
close_project
exit
