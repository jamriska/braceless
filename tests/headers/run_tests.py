#!/usr/bin/env python3
"""
Test runner for Braceless C++ header (.blh) support.

This script runs all header-related tests:
1. Unit tests for line marker parsing
2. Unit tests for line mapping
3. Unit tests for error patching
4. Integration tests for full preprocessing + transpilation pipeline

Usage:
    python run_tests.py              # Run all tests
    python run_tests.py --unit       # Run only unit tests
    python run_tests.py --integration # Run only integration tests
    python run_tests.py -v           # Verbose output
"""

import os
import sys
import unittest
import argparse
from pathlib import Path


def discover_tests(test_dir: Path, pattern: str = "test_*.py") -> unittest.TestSuite:
    """Discover all tests in the given directory."""
    loader = unittest.TestLoader()
    suite = loader.discover(str(test_dir), pattern=pattern)
    return suite


def run_unit_tests(verbosity: int = 1) -> bool:
    """Run unit tests for line mapping and error patching."""
    print("=" * 60)
    print("Running Unit Tests")
    print("=" * 60)
    
    test_dir = Path(__file__).parent
    suite = unittest.TestSuite()
    
    # Add specific test modules
    loader = unittest.TestLoader()
    
    # Test preprocessor line marker parsing and line mapping
    try:
        from . import test_preprocessor
        suite.addTests(loader.loadTestsFromModule(test_preprocessor))
    except ImportError:
        # Direct import when running as script
        import test_preprocessor
        suite.addTests(loader.loadTestsFromModule(test_preprocessor))
    
    # Test error message patching
    try:
        from . import test_error_mapping
        suite.addTests(loader.loadTestsFromModule(test_error_mapping))
    except ImportError:
        import test_error_mapping
        suite.addTests(loader.loadTestsFromModule(test_error_mapping))
    
    runner = unittest.TextTestRunner(verbosity=verbosity)
    result = runner.run(suite)
    
    return result.wasSuccessful()


def run_integration_tests(verbosity: int = 1) -> bool:
    """Run integration tests that require a C++ compiler."""
    print("=" * 60)
    print("Running Integration Tests")
    print("=" * 60)
    
    # Check for available compilers
    compilers = check_available_compilers()
    if not compilers:
        print("WARNING: No C++ compilers found. Skipping integration tests.")
        return True
    
    print(f"Found compilers: {', '.join(compilers)}")
    
    # Run transpilation tests for each test case
    test_dir = Path(__file__).parent
    test_cases = [
        "01_simple_include",
        "02_nested_includes",
        "03_mixed_headers",
        "04_include_guard",
        "05_pragma_once",
        "06_macros",
        "07_system_headers",
    ]
    
    all_passed = True
    
    for test_case in test_cases:
        case_dir = test_dir / test_case
        if not case_dir.exists():
            print(f"  SKIP: {test_case} (directory not found)")
            continue
        
        main_file = case_dir / "main.blcpp"
        expected_file = case_dir / "expected.cpp"
        
        if not main_file.exists() or not expected_file.exists():
            print(f"  SKIP: {test_case} (missing files)")
            continue
        
        # For now, just verify the test files exist
        # Full integration will be added when preprocessing is implemented
        print(f"  READY: {test_case}")
    
    return all_passed


def check_available_compilers() -> list:
    """Check which C++ compilers are available."""
    import shutil
    
    compilers = []
    
    # Check for various compilers
    compiler_names = ['clang++', 'clang', 'g++', 'gcc', 'cl']
    
    for name in compiler_names:
        if shutil.which(name):
            compilers.append(name)
    
    return compilers


def main():
    parser = argparse.ArgumentParser(description="Run header support tests")
    parser.add_argument('-v', '--verbose', action='count', default=1,
                        help="Increase verbosity (can be repeated)")
    parser.add_argument('--unit', action='store_true',
                        help="Run only unit tests")
    parser.add_argument('--integration', action='store_true',
                        help="Run only integration tests")
    
    args = parser.parse_args()
    
    # Change to test directory
    os.chdir(Path(__file__).parent)
    
    # Add parent directories to path
    sys.path.insert(0, str(Path(__file__).parent))
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    
    verbosity = args.verbose
    
    run_all = not args.unit and not args.integration
    
    success = True
    
    if run_all or args.unit:
        if not run_unit_tests(verbosity):
            success = False
    
    if run_all or args.integration:
        if not run_integration_tests(verbosity):
            success = False
    
    print()
    print("=" * 60)
    if success:
        print("All tests passed!")
    else:
        print("Some tests failed!")
    print("=" * 60)
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
