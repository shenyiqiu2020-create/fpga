if {[catch {connect -url tcp:127.0.0.1:3121} reason]} {
    puts "EA_TARGET_UNAVAILABLE: $reason"
    exit 2
}
puts "EA_TARGETS_BEGIN"
puts [targets]
puts [targets -target-properties]
puts "EA_TARGETS_END"
disconnect
exit
