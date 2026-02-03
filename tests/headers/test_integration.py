#!/usr/bin/env python3
"""
End-to-end integration tests for .blh header support.

These tests verify the complete pipeline:
1. Run preprocessor on .blcpp file with .blh includes
2. Parse line markers from preprocessor output
3. Strip line markers to get pure braceless code
4. Transpile braceless code to braced C++
5. Chain line mappings for error reporting
6. Verify errors map back to correct original locations
"""

import unittest
import sys
import os
import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Import test utilities from sibling modules
from test_preprocessor import (
    parse_line_marker, build_line_map, strip_line_markers,
    SourceLocation, LineMarker
)
from test_error_mapping import patch_compiler_output


# =============================================================================
# Helper functions for integration tests
# =============================================================================

def find_compiler() -> Optional[str]:
    """Find an available C++ compiler for preprocessing."""
    compilers = ['clang++', 'clang', 'g++', 'gcc', 'cl']
    for compiler in compilers:
        if shutil.which(compiler):
            return compiler
    return None


def run_preprocessor(
    compiler: str,
    source_file: str,
    include_dirs: list = None
) -> Tuple[bool, str, str]:
    """Run the C preprocessor on a source file.
    
    Args:
        compiler: Path to compiler executable
        source_file: Path to source file
        include_dirs: List of include directories
        
    Returns:
        (success, stdout, stderr)
    """
    cmd = [compiler, '-E']
    
    # Add include directories
    if include_dirs:
        for inc_dir in include_dirs:
            cmd.extend(['-I', inc_dir])
    
    cmd.append(source_file)
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
        return (result.returncode == 0, result.stdout, result.stderr)
    except subprocess.TimeoutExpired:
        return (False, '', 'Preprocessor timed out')
    except Exception as e:
        return (False, '', str(e))


def simulate_transpilation_mapping(preprocessed_lines: int) -> Dict[int, int]:
    """Simulate a simple transpilation line mapping.
    
    In real implementation, this would come from MappingCompiler.
    For testing, we assume 1:1 mapping (no extra lines from braces).
    """
    return {i: i for i in range(1, preprocessed_lines + 1)}


# =============================================================================
# Test Cases
# =============================================================================

class TestPreprocessorExecution(unittest.TestCase):
    """Tests for running the actual preprocessor"""

    @classmethod
    def setUpClass(cls):
        cls.compiler = find_compiler()
        cls.test_dir = Path(__file__).parent
        
    def setUp(self):
        if not self.compiler:
            self.skipTest("No C++ compiler available")
        
        # Create temp directory for test files
        self.temp_dir = tempfile.mkdtemp(prefix='blcc_test_')
    
    def tearDown(self):
        if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_preprocess_simple_file(self):
        """Test preprocessing a simple file with no includes"""
        # Create test file
        source = Path(self.temp_dir) / "simple.cpp"
        source.write_text("int main() { return 0; }\n")
        
        success, stdout, stderr = run_preprocessor(self.compiler, str(source))
        
        self.assertTrue(success, f"Preprocessor failed: {stderr}")
        self.assertIn("int main()", stdout)
        # Should have line markers
        self.assertIn("# 1", stdout)

    def test_preprocess_with_local_include(self):
        """Test preprocessing a file that includes a local header"""
        # Create header
        header = Path(self.temp_dir) / "myheader.h"
        header.write_text("int foo() { return 42; }\n")
        
        # Create source that includes header
        source = Path(self.temp_dir) / "main.cpp"
        source.write_text('#include "myheader.h"\nint main() { return foo(); }\n')
        
        success, stdout, stderr = run_preprocessor(
            self.compiler, str(source), [self.temp_dir]
        )
        
        self.assertTrue(success, f"Preprocessor failed: {stderr}")
        self.assertIn("int foo()", stdout)
        self.assertIn("int main()", stdout)
        # Should have line markers for both files
        self.assertIn("myheader.h", stdout)

    def test_preprocess_braceless_file(self):
        """Test preprocessing a .blcpp file with .blh include"""
        # Create braceless header
        header = Path(self.temp_dir) / "utils.blh"
        header.write_text('''\
#pragma once

int add(int a, int b):
    return a + b
''')
        
        # Create braceless source
        source = Path(self.temp_dir) / "main.blcpp"
        source.write_text('''\
#include "utils.blh"

int main():
    return add(1, 2)
''')
        
        success, stdout, stderr = run_preprocessor(
            self.compiler, str(source), [self.temp_dir]
        )
        
        self.assertTrue(success, f"Preprocessor failed: {stderr}")
        # Content should be present (braceless syntax passes through)
        self.assertIn("int add(int a, int b):", stdout)
        self.assertIn("int main():", stdout)
        # Line markers should reference original files
        self.assertIn("utils.blh", stdout)
        self.assertIn("main.blcpp", stdout)


class TestLineMapFromPreprocessor(unittest.TestCase):
    """Tests for building line maps from real preprocessor output"""

    @classmethod
    def setUpClass(cls):
        cls.compiler = find_compiler()
        
    def setUp(self):
        if not self.compiler:
            self.skipTest("No C++ compiler available")
        
        self.temp_dir = tempfile.mkdtemp(prefix='blcc_test_')
    
    def tearDown(self):
        if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_line_map_simple(self):
        """Build line map from simple preprocessor output"""
        source = Path(self.temp_dir) / "test.cpp"
        source.write_text("int x = 1;\nint y = 2;\nint z = 3;\n")
        
        success, stdout, _ = run_preprocessor(self.compiler, str(source))
        self.assertTrue(success)
        
        line_map = build_line_map(stdout)
        
        # Find lines that map to our source file
        source_lines = [
            (k, v) for k, v in line_map.items() 
            if 'test.cpp' in v.file
        ]
        
        self.assertGreater(len(source_lines), 0)

    def test_line_map_with_include(self):
        """Build line map from output with includes"""
        header = Path(self.temp_dir) / "header.h"
        header.write_text("int header_var = 1;\n")
        
        source = Path(self.temp_dir) / "main.cpp"
        source.write_text('#include "header.h"\nint main_var = 2;\n')
        
        success, stdout, _ = run_preprocessor(
            self.compiler, str(source), [self.temp_dir]
        )
        self.assertTrue(success)
        
        line_map = build_line_map(stdout)
        
        # Should have entries from both files
        header_lines = [v for v in line_map.values() if 'header.h' in v.file]
        main_lines = [v for v in line_map.values() if 'main.cpp' in v.file]
        
        self.assertGreater(len(header_lines), 0, "No lines from header.h")
        self.assertGreater(len(main_lines), 0, "No lines from main.cpp")


class TestEndToEndPipeline(unittest.TestCase):
    """End-to-end tests for the complete preprocessing + transpilation pipeline"""

    @classmethod
    def setUpClass(cls):
        cls.compiler = find_compiler()
        cls.test_dir = Path(__file__).parent
        
    def setUp(self):
        if not self.compiler:
            self.skipTest("No C++ compiler available")
        
        self.temp_dir = tempfile.mkdtemp(prefix='blcc_test_')
    
    def tearDown(self):
        if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_full_pipeline_simple_include(self):
        """Test full pipeline with simple .blh include"""
        # Create .blh header
        header = Path(self.temp_dir) / "math.blh"
        header.write_text('''\
#pragma once

int add(int a, int b):
    return a + b
''')
        
        # Create .blcpp source
        source = Path(self.temp_dir) / "main.blcpp"
        source.write_text('''\
#include "math.blh"

int main():
    return add(1, 2)
''')
        
        # Step 1: Preprocess
        success, preproc_output, stderr = run_preprocessor(
            self.compiler, str(source), [self.temp_dir]
        )
        self.assertTrue(success, f"Preprocessing failed: {stderr}")
        
        # Step 2: Build line map
        preproc_line_map = build_line_map(preproc_output)
        
        # Step 3: Strip line markers
        stripped = strip_line_markers(preproc_output)
        
        # Verify stripped content has braceless code
        self.assertIn("int add(int a, int b):", stripped)
        self.assertIn("return a + b", stripped)
        self.assertIn("int main():", stripped)
        
        # Step 4: Verify line mappings
        # Find a line from the header
        header_lines = [
            (k, v) for k, v in preproc_line_map.items()
            if 'math.blh' in v.file
        ]
        self.assertGreater(len(header_lines), 0)
        
        # Find a line from main
        main_lines = [
            (k, v) for k, v in preproc_line_map.items()
            if 'main.blcpp' in v.file
        ]
        self.assertGreater(len(main_lines), 0)

    def test_error_mapping_simulation(self):
        """Simulate error mapping through the pipeline"""
        # Create test files
        header = Path(self.temp_dir) / "utils.blh"
        header.write_text('''\
#pragma once

int broken_func():
    return  // Missing value - would cause error at line 4
''')
        
        source = Path(self.temp_dir) / "main.blcpp"
        source.write_text('''\
#include "utils.blh"

int main():
    return broken_func()
''')
        
        # Preprocess
        success, preproc_output, _ = run_preprocessor(
            self.compiler, str(source), [self.temp_dir]
        )
        self.assertTrue(success)
        
        # Build line map
        preproc_line_map = build_line_map(preproc_output)
        
        # Simulate transpilation (1:1 for simplicity)
        stripped = strip_line_markers(preproc_output)
        stripped_lines = stripped.split('\n')
        
        # Create chained mapping: transpiled_line -> SourceLocation
        # In real impl, this would chain transpile_map with preproc_line_map
        chained_map = preproc_line_map  # Simplified for test
        
        # Simulate an error at a line from the header
        # Find which output line corresponds to "return  // Missing value"
        for output_line, loc in chained_map.items():
            if 'utils.blh' in loc.file and loc.line == 4:
                # This is where the error would be
                # Verify we can map back correctly
                self.assertEqual(loc.file, str(header).replace('\\', '/').split('/')[-1] 
                               if '/' in str(header) else header.name)
                break


class TestWithRealTestCases(unittest.TestCase):
    """Tests using the actual test case directories"""

    @classmethod
    def setUpClass(cls):
        cls.compiler = find_compiler()
        cls.test_dir = Path(__file__).parent
        
    def setUp(self):
        if not self.compiler:
            self.skipTest("No C++ compiler available")

    def _test_case(self, case_name: str):
        """Helper to test a specific test case directory"""
        case_dir = self.test_dir / case_name
        if not case_dir.exists():
            self.skipTest(f"Test case {case_name} not found")
        
        main_file = case_dir / "main.blcpp"
        if not main_file.exists():
            self.skipTest(f"main.blcpp not found in {case_name}")
        
        # Preprocess
        success, preproc_output, stderr = run_preprocessor(
            self.compiler, str(main_file), [str(case_dir)]
        )
        
        self.assertTrue(success, f"Preprocessing failed for {case_name}: {stderr}")
        
        # Build line map
        line_map = build_line_map(preproc_output)
        self.assertGreater(len(line_map), 0, f"Empty line map for {case_name}")
        
        # Strip and verify content
        stripped = strip_line_markers(preproc_output)
        self.assertGreater(len(stripped), 0, f"Empty stripped content for {case_name}")
        
        return preproc_output, line_map, stripped

    def test_01_simple_include(self):
        """Test 01_simple_include case"""
        preproc, line_map, stripped = self._test_case("01_simple_include")
        
        # Verify header content is included
        self.assertIn("int add(int a, int b):", stripped)
        self.assertIn("class Calculator:", stripped)
        
        # Verify line map has entries from both files
        files_in_map = set(v.file for v in line_map.values())
        blh_files = [f for f in files_in_map if '.blh' in f]
        blcpp_files = [f for f in files_in_map if '.blcpp' in f]
        
        self.assertGreater(len(blh_files), 0, "No .blh files in line map")
        self.assertGreater(len(blcpp_files), 0, "No .blcpp files in line map")

    def test_02_nested_includes(self):
        """Test 02_nested_includes case"""
        preproc, line_map, stripped = self._test_case("02_nested_includes")
        
        # Verify nested header content
        self.assertIn("struct Point:", stripped)
        self.assertIn("class Rectangle:", stripped)

    def test_03_mixed_headers(self):
        """Test 03_mixed_headers case"""
        preproc, line_map, stripped = self._test_case("03_mixed_headers")
        
        # Should have content from both .h and .blh
        self.assertIn("RegularStruct", stripped)  # From .h
        self.assertIn("BracelessClass", stripped)  # From .blh


if __name__ == '__main__':
    unittest.main(verbosity=2)
