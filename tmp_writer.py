import sys
import os

# Write to project directory to avoid path issues
output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tmp_check.txt')
try:
    with open(output_path, 'w') as f:
        f.write('Python works')
    print(f'Success: wrote to {output_path}')
except Exception as e:
    error_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tmp_error.txt')
    with open(error_path, 'w') as f:
        f.write(f'Error: {str(e)}')
    print(f'Error: {e}')
