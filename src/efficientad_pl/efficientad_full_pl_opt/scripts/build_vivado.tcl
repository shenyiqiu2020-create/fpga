# Creates ONLY this package's new project. Does not open/edit the old project.
set root [file normalize [file join [file dirname [info script]] ..]]
set ipdir [file join $root hls engine_project sol impl ip]
if {![file exists [file join $ipdir component.xml]]} {error "Package HLS IP first: missing $ipdir/component.xml"}
set work [file join $root _build vivado]
file mkdir $work
set xpr [file join $work ea_full.xpr]
if {[file exists $xpr]} {
    open_project $xpr
    open_bd_design [get_files */design_full.bd]
    set aux [get_bd_pins rst/aux_reset_in]
    if {[get_bd_nets -of_objects $aux] ne [get_bd_nets -of_objects [get_bd_pins one/dout]]} {
        delete_bd_objs [get_bd_nets -of_objects $aux]
        connect_bd_net [get_bd_pins zero/dout] [get_bd_pins rst/mb_debug_sys_rst]
        connect_bd_net [get_bd_pins one/dout] $aux
        validate_bd_design
        save_bd_design
        generate_target all [get_files */design_full.bd]
        reset_run synth_1
    }
} else {
    create_project ea_full $work -part xc7z020clg484-2
    set_property ip_repo_paths [list $ipdir] [current_project]
    update_ip_catalog
    create_bd_design design_full
    create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:5.5 ps
    source [file join $root generated ps_config.tcl]
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
}
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
file copy -force $bit [file join $root generated efficientad_full.bit]
write_hw_platform -fixed -include_bit -force [file join $root generated ax7021_efficientad_full.xsa]
puts "EA_FULL_BUILD_SUCCESS: [file join $root generated ax7021_efficientad_full.xsa], WNS=$slack"
close_project
exit
