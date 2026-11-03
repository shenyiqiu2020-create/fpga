# Placed-design hook: split the one-hot FSM controls that fan out to the
# partitioned bias/multiplier registers. RTL and arithmetic stay unchanged.
set ea_root [file normalize [file join [file dirname [info script]] ..]]
report_high_fanout_nets -max_nets 30 -file [file join $ea_root generated fanout_before.rpt]
set ea_controls {}
foreach ea_net [get_nets -hier -filter {NAME =~ *conv_layer_Outline*/ap_CS_fsm_state*}] {
    set ea_loads [llength [get_pins -leaf -of_objects $ea_net -filter {DIRECTION == IN}]]
    if {$ea_loads>=128} {
        lappend ea_controls $ea_net
        puts "EA_FORCE_CONTROL_REPLICATION: $ea_net, loads=$ea_loads"
    }
}
if {[llength $ea_controls]} {
    phys_opt_design -force_replication_on_nets $ea_controls
} else {
    puts "EA_CONTROL_REPLICATION: no registered loader control exceeds 128 loads in the new schedule"
}
report_high_fanout_nets -max_nets 30 -file [file join $ea_root generated fanout_after_replication.rpt]
