#!/bin/bash

# =============================================================================
# Controller C2 Test Script
# Tests FSM functionality, command handling, and error scenarios
# =============================================================================

# MQTT Configuration (from autogen_config.h)
BROKER="BROKERHERE"
PORT="PORTHERE"
USERNAME="UNAMEHERE"
PASSWORD="PASSWORDHERE"

# MQTT Topics (from autogen_config.h)
HUMIDIFIER_WRITE="mush/humidity_driver_fruiting/commands/c2/humidifier/write"
HEATINGPAD_WRITE="mush/temperature_driver_fruiting/commands/c2/heatingpad/write"
LIGHT_WRITE="mush/light_driver_fruiting/commands/c2/light/write"
VENTFAN_WRITE="mush/vent_driver_fruiting/commands/c2/ventfan/write"

# Readback topics for monitoring
READBACK_PATTERN="mush/c2/actuators/+/readback"
ALL_C2_PATTERN="mush/c2/#"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_test() {
    echo -e "${BLUE}=== $1 ===${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

# Function to send MQTT command
send_command() {
    local topic=$1
    local value=$2
    local device_name=$3
    local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%S.%3NZ")
    local payload="{\"timestamp_utc\":\"$timestamp\",\"value\":\"$value\",\"uuid\":\"test-uuid\"}"
    
    echo "Sending '$value' to $device_name"
    mosquitto_pub -h $BROKER -p $PORT -u $USERNAME -P $PASSWORD -t "$topic" -m "$payload"
    
    if [ $? -eq 0 ]; then
        print_success "Command sent successfully"
    else
        print_error "Failed to send command"
    fi
}

# Function to start MQTT monitoring in background
start_monitor() {
    local pattern=$1
    local output_file=$2
    
    echo "Starting MQTT monitor for pattern: $pattern"
    mosquitto_sub -h $BROKER -p $PORT -u $USERNAME -P $PASSWORD -t "$pattern" -v > "$output_file" 2>&1 &
    echo $!
}

# Function to stop background process
stop_monitor() {
    local pid=$1
    if kill -0 $pid 2>/dev/null; then
        kill $pid
        wait $pid 2>/dev/null
    fi
}

# Test 1: Latest Command Wins
test_latest_command_wins() {
    print_test "Test 1: Latest Command Wins (Rapid Succession)"
    
    # Start monitoring
    monitor_file=$(mktemp)
    monitor_pid=$(start_monitor "$READBACK_PATTERN" "$monitor_file")
    
    echo "Sending SIMULTANEOUS commands to humidifier..."
    echo "Expected: Only the final 'on' command should execute"
    
    # Send all 3 commands simultaneously in background
    echo "Launching all 3 commands at once..."
    (
        local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%S.%3NZ")
        local payload1="{\"timestamp_utc\":\"$timestamp\",\"value\":\"on\",\"uuid\":\"test-uuid\"}"
        mosquitto_pub -h $BROKER -p $PORT -u $USERNAME -P $PASSWORD -t "$HUMIDIFIER_WRITE" -m "$payload1"
    ) &
    
    (
        local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%S.%3NZ")  
        local payload2="{\"timestamp_utc\":\"$timestamp\",\"value\":\"off\",\"uuid\":\"test-uuid\"}"
        mosquitto_pub -h $BROKER -p $PORT -u $USERNAME -P $PASSWORD -t "$HUMIDIFIER_WRITE" -m "$payload2"
    ) &
    
    (
        local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%S.%3NZ")
        local payload3="{\"timestamp_utc\":\"$timestamp\",\"value\":\"on\",\"uuid\":\"test-uuid\"}"
        mosquitto_pub -h $BROKER -p $PORT -u $USERNAME -P $PASSWORD -t "$HUMIDIFIER_WRITE" -m "$payload3"
    ) &
    
    # Wait for all background commands to complete
    wait
    print_success "All 3 commands sent simultaneously"
    
    echo "Waiting 10 seconds to observe readbacks..."
    sleep 10
    
    stop_monitor $monitor_pid
    
    echo -e "\n${YELLOW}Readback Messages Received:${NC}"
    cat "$monitor_file" | grep "humidifier/readback"
    
    readback_count=$(grep -c "humidifier/readback" "$monitor_file")
    echo -e "\nTotal humidifier readbacks: $readback_count"
    
    if [ "$readback_count" -eq 1 ]; then
        print_success "PASS: Only 1 readback received (latest command wins)"
    else
        print_error "FAIL: Expected 1 readback, got $readback_count"
        echo "This suggests commands are being processed individually rather than queued"
    fi
    
    rm "$monitor_file"
    echo
}

# Test 2: All Actuators Basic Functionality
test_all_actuators() {
    print_test "Test 2: All Actuators Basic Functionality"
    
    # Start monitoring
    monitor_file=$(mktemp)
    monitor_pid=$(start_monitor "$READBACK_PATTERN" "$monitor_file")
    
    echo "Testing all 4 actuators with on/off commands..."
    
    # Test each actuator
    send_command "$HUMIDIFIER_WRITE" "on" "humidifier"
    sleep 2
    send_command "$HEATINGPAD_WRITE" "on" "heating pad"
    sleep 2
    send_command "$LIGHT_WRITE" "on" "light"
    sleep 2
    send_command "$VENTFAN_WRITE" "on" "vent fan"
    sleep 2
    
    # Turn them all off
    send_command "$HUMIDIFIER_WRITE" "off" "humidifier"
    sleep 2
    send_command "$HEATINGPAD_WRITE" "off" "heating pad"
    sleep 2
    send_command "$LIGHT_WRITE" "off" "light"
    sleep 2
    send_command "$VENTFAN_WRITE" "off" "vent fan"
    
    echo "Waiting 5 seconds for readbacks..."
    sleep 5
    
    stop_monitor $monitor_pid
    
    echo -e "\n${YELLOW}All Readback Messages:${NC}"
    cat "$monitor_file"
    
    readback_count=$(grep -c "readback" "$monitor_file")
    echo -e "\nTotal readbacks: $readback_count"
    
    if [ "$readback_count" -eq 8 ]; then
        print_success "PASS: All 8 readbacks received (4 on + 4 off)"
    else
        print_warning "Expected 8 readbacks, got $readback_count (may be timing related)"
    fi
    
    rm "$monitor_file"
    echo
}

# Test 3: Invalid Commands
test_invalid_commands() {
    print_test "Test 3: Invalid Commands"
    
    # Start monitoring
    monitor_file=$(mktemp)
    monitor_pid=$(start_monitor "$READBACK_PATTERN" "$monitor_file")
    
    echo "Sending invalid commands (should be ignored)..."
    
    # Invalid JSON
    echo "Sending malformed JSON..."
    mosquitto_pub -h $BROKER -p $PORT -u $USERNAME -P $PASSWORD -t "$HUMIDIFIER_WRITE" -m "not_json"
    sleep 1
    
    # Invalid value field
    echo "Sending invalid value field..."
    local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%S.%3NZ")
    local bad_payload="{\"timestamp_utc\":\"$timestamp\",\"value\":\"invalid\",\"uuid\":\"test-uuid\"}"
    mosquitto_pub -h $BROKER -p $PORT -u $USERNAME -P $PASSWORD -t "$HUMIDIFIER_WRITE" -m "$bad_payload"
    sleep 1
    
    # Missing value field
    echo "Sending missing value field..."
    local missing_value="{\"timestamp_utc\":\"$timestamp\",\"uuid\":\"test-uuid\"}"
    mosquitto_pub -h $BROKER -p $PORT -u $USERNAME -P $PASSWORD -t "$HUMIDIFIER_WRITE" -m "$missing_value"
    sleep 1
    
    # Send a valid command to confirm system still works
    echo "Sending valid command to confirm system still works..."
    send_command "$HUMIDIFIER_WRITE" "on" "humidifier"
    
    echo "Waiting 5 seconds..."
    sleep 5
    
    stop_monitor $monitor_pid
    
    echo -e "\n${YELLOW}Readback Messages (should only be 1 from valid command):${NC}"
    cat "$monitor_file"
    
    readback_count=$(grep -c "readback" "$monitor_file")
    
    if [ "$readback_count" -eq 1 ]; then
        print_success "PASS: Only valid command produced readback"
    else
        print_error "FAIL: Expected 1 readback from valid command, got $readback_count"
    fi
    
    rm "$monitor_file"
    echo
}

# Test 4: Periodic Republish (requires waiting)
test_periodic_republish() {
    print_test "Test 4: Periodic Republish (60 second intervals)"
    
    print_warning "This test requires waiting 60+ seconds for OUTPUT_REPUBLISH_FREQUENCY_MS"
    echo "Press Enter to continue, or Ctrl+C to skip..."
    read
    
    # Start monitoring
    monitor_file=$(mktemp)
    monitor_pid=$(start_monitor "$READBACK_PATTERN" "$monitor_file")
    
    echo "Setting known state for humidifier..."
    send_command "$HUMIDIFIER_WRITE" "on" "humidifier"
    sleep 5
    
    echo "Now waiting 70 seconds to observe periodic republish..."
    echo "You should see additional readbacks without sending new commands"
    
    for i in {1..14}; do
        echo -n "."
        sleep 5
    done
    echo
    
    stop_monitor $monitor_pid
    
    echo -e "\n${YELLOW}All Messages (initial + any republishes):${NC}"
    cat "$monitor_file" | grep "humidifier/readback"
    
    readback_count=$(grep -c "humidifier/readback" "$monitor_file")
    
    if [ "$readback_count" -gt 1 ]; then
        print_success "PASS: Periodic republish working ($readback_count total readbacks)"
    else
        print_error "FAIL: No periodic republish detected"
    fi
    
    rm "$monitor_file"
    echo
}

# Test 5: Monitor Boot Status and System Info
test_system_status() {
    print_test "Test 5: System Status Monitoring"
    
    echo "Monitoring system status topics for 30 seconds..."
    echo "Look for boot status, restart reasons, wifi uptime, etc."
    
    monitor_file=$(mktemp)
    monitor_pid=$(start_monitor "$ALL_C2_PATTERN" "$monitor_file")
    
    sleep 30
    
    stop_monitor $monitor_pid
    
    echo -e "\n${YELLOW}System Status Messages:${NC}"
    cat "$monitor_file" | grep -E "(status|restart|uptime|boot)"
    
    status_count=$(grep -c -E "(status|restart|uptime|boot)" "$monitor_file")
    
    if [ "$status_count" -gt 0 ]; then
        print_success "System status messages detected"
    else
        print_warning "No system status messages detected in 30 seconds"
    fi
    
    rm "$monitor_file"
    echo
}

# Interactive menu
show_menu() {
    echo -e "\n${BLUE}Controller C2 Test Menu${NC}"
    echo "1. Latest Command Wins Test (rapid succession)"
    echo "2. All Actuators Basic Test"
    echo "3. Invalid Commands Test"
    echo "4. Periodic Republish Test (60+ sec wait)"
    echo "5. System Status Monitor"
    echo "6. Run All Tests"
    echo "7. Start Real-time Monitor"
    echo "q. Quit"
    echo
}

# Real-time monitor
real_time_monitor() {
    print_test "Real-time MQTT Monitor"
    echo "Monitoring all C2 traffic. Press Ctrl+C to stop."
    echo
    
    mosquitto_sub -h $BROKER -p $PORT -u $USERNAME -P $PASSWORD -t "$ALL_C2_PATTERN" -v
}

# Main script
main() {
    echo -e "${GREEN}Controller C2 Test Script${NC}"
    echo "Broker: $BROKER:$PORT"
    echo "User: $USERNAME"
    echo
    
    # Test MQTT connectivity
    echo "Testing MQTT connectivity..."
    if mosquitto_pub -h $BROKER -p $PORT -u $USERNAME -P $PASSWORD -t "test/connection" -m "test" >/dev/null 2>&1; then
        print_success "MQTT connection OK"
    else
        print_error "MQTT connection failed!"
        exit 1
    fi
    
    while true; do
        show_menu
        read -p "Select option: " choice
        
        case $choice in
            1) test_latest_command_wins ;;
            2) test_all_actuators ;;
            3) test_invalid_commands ;;
            4) test_periodic_republish ;;
            5) test_system_status ;;
            6) 
                test_latest_command_wins
                test_all_actuators
                test_invalid_commands
                echo "Skipping periodic republish test (too long for full suite)"
                test_system_status
                ;;
            7) real_time_monitor ;;
            q|Q) 
                echo "Goodbye!"
                exit 0
                ;;
            *) print_error "Invalid option" ;;
        esac
    done
}

# Check if mosquitto clients are installed
if ! command -v mosquitto_pub &> /dev/null; then
    print_error "mosquitto clients not found. Install with: sudo apt install mosquitto-clients"
    exit 1
fi

# Run main function
main 