#!/usr/bin/env python3
"""
Test runner for Braceless C++ Compiler (blcc)

This script runs all test cases and verifies that blcc produces the expected output.
Each test consists of a .blcpp file (input) and a .cpp file (expected output).
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import Tuple, List
import difflib

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def find_test_pairs(test_dir: Path) -> List[Tuple[Path, Path]]:
    """Find all test pairs (.blcpp and .cpp files) in the test directory."""
    test_pairs = []
    
    for blcpp_file in test_dir.rglob("*.blcpp"):
        cpp_file = blcpp_file.with_suffix(".cpp")
        if cpp_file.exists():
            test_pairs.append((blcpp_file, cpp_file))
        else:
            print(f"{Colors.YELLOW}Warning: No matching .cpp file for {blcpp_file}{Colors.RESET}")
    
    return sorted(test_pairs)

def run_blcc(blcc_path: str, input_file: Path) -> Tuple[bool, str, str]:
    """
    Run blcc compiler on the input file.
    Returns: (success, stdout, stderr)
    """
    try:
        result = subprocess.run(
            [sys.executable, blcc_path, str(input_file)],
            capture_output=True,
            text=True,
            timeout=10
        )
        return (result.returncode == 0, result.stdout, result.stderr)
    except subprocess.TimeoutExpired:
        return (False, "", "Timeout: blcc took too long to execute")
    except FileNotFoundError:
        return (False, "", f"Error: blcc compiler not found at {blcc_path}")
    except Exception as e:
        return (False, "", f"Error running blcc: {str(e)}")

def compare_outputs(actual: str, expected: str) -> Tuple[bool, str]:
    """
    Compare actual output with expected output.
    Returns: (match, diff_text)
    """
    if actual == expected:
        return (True, "")
    
    # Generate unified diff for better readability
    diff = difflib.unified_diff(
        expected.splitlines(keepends=True),
        actual.splitlines(keepends=True),
        fromfile="expected.cpp",
        tofile="actual.cpp",
        lineterm=""
    )
    
    return (False, ''.join(diff))

def run_single_test(blcc_path: str, blcpp_file: Path, cpp_file: Path) -> Tuple[bool, str]:
    """
    Run a single test case.
    Returns: (passed, message)
    """
    # Run blcc compiler
    success, stdout, stderr = run_blcc(blcc_path, blcpp_file)
    
    if not success:
        return (False, f"Compilation failed:\n{stderr}")
    
    # Read expected output
    try:
        with open(cpp_file, 'r', encoding='utf-8') as f:
            expected = f.read()
    except Exception as e:
        return (False, f"Error reading expected output: {str(e)}")
    
    # Compare outputs
    match, diff = compare_outputs(stdout, expected)
    
    if match:
        return (True, "Output matches expected")
    else:
        return (False, f"Output mismatch:\n{diff}")

def main():
    # Parse command line arguments
    # Default to blcc.py in the parent folder
    script_dir = Path(__file__).parent
    default_blcc_path = script_dir.parent.parent / "blcc.py"
    
    if len(sys.argv) >= 2:
        blcc_path = sys.argv[1]
        test_dir = Path(sys.argv[2] if len(sys.argv) > 2 else script_dir.parent)
    else:
        blcc_path = str(default_blcc_path)
        test_dir = script_dir.parent
    
    if not Path(blcc_path).exists():
        print(f"{Colors.RED}Error: blcc compiler not found at '{blcc_path}'{Colors.RESET}")
        print(f"Default location: {default_blcc_path}")
        print(f"Usage: {sys.argv[0]} [path_to_blcc_compiler] [test_directory]")
        sys.exit(1)
    
    if not test_dir.exists():
        print(f"{Colors.RED}Error: Test directory '{test_dir}' not found{Colors.RESET}")
        sys.exit(1)
    
    # Find all test pairs
    test_pairs = find_test_pairs(test_dir)
    
    if not test_pairs:
        print(f"{Colors.YELLOW}No test pairs found in {test_dir}{Colors.RESET}")
        sys.exit(0)
    
    print(f"{Colors.BOLD}Running Braceless C++ Compiler Tests{Colors.RESET}")
    print(f"Compiler: {blcc_path}")
    print(f"Test directory: {test_dir}")
    print(f"Found {len(test_pairs)} test cases\n")
    
    # Run all tests
    passed = 0
    failed = 0
    failed_tests = []
    
    for blcpp_file, cpp_file in test_pairs:
        test_name = str(blcpp_file.relative_to(test_dir))
        print(f"Testing {test_name}...", end=" ")
        
        success, message = run_single_test(blcc_path, blcpp_file, cpp_file)
        
        if success:
            print(f"{Colors.GREEN}PASS{Colors.RESET}")
            passed += 1
        else:
            print(f"{Colors.RED}FAIL{Colors.RESET}")
            failed += 1
            failed_tests.append((test_name, message))
    
    # Print summary
    print(f"\n{Colors.BOLD}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}Test Summary{Colors.RESET}")
    print(f"Total: {len(test_pairs)}")
    print(f"{Colors.GREEN}Passed: {passed}{Colors.RESET}")
    print(f"{Colors.RED}Failed: {failed}{Colors.RESET}")
    
    # Print failed test details
    if failed_tests:
        print(f"\n{Colors.BOLD}Failed Tests:{Colors.RESET}")
        for test_name, message in failed_tests:
            print(f"\n{Colors.RED}{test_name}:{Colors.RESET}")
            print(message)
    
    # Exit with appropriate code
    sys.exit(0 if failed == 0 else 1)

if __name__ == "__main__":
    main()
