import json
import os
from ...common.configuration import FSMConfiguration  
# Load and compare configs
def compare_configs():
    # Get absolute path to temperature_driver config
    current_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(current_dir, 'control/temperature_driver/config')
    
    # Generate new config
    config = FSMConfiguration(config_path)
    test_output_path = os.path.join(config_path, 'test_output.json')
    config.save_full_config(test_output_path)
    
    # Load both configs
    with open(os.path.join(config_path, 'pruned_reference.json'), 'r') as f:
        reference = json.load(f)
    with open(test_output_path, 'r') as f:
        test_output = json.load(f)
    
    # Compare points sections
    ref_points = reference['points']
    test_points = test_output['points']
    
    # Compare microcontrollers
    print("Reference microcontrollers:", list(ref_points['microcontrollers'].keys()))
    print("Test microcontrollers:", list(test_points['microcontrollers'].keys()))
    
    # Compare C2 control points
    ref_cps = ref_points['microcontrollers']['C2']['control_points']
    test_cps = test_points['microcontrollers']['C2']['control_points']
    print("\nReference control points:", list(ref_cps.keys()))
    print("Test control points:", list(test_cps.keys()))
    
    # Compare drivers
    print("\nReference driver points:", ref_points['drivers'])
    print("Test driver points:", test_points['drivers'])
    
    assert ref_points == test_points, "Points configs don't match"
    print("Points match!")

if __name__ == "__main__":
    compare_configs() 