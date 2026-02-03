#!/usr/bin/env python3
"""
Comprehensive tests for preprocessor-based .blh header support.

These tests verify the complete pipeline:
1. Preprocessor line marker parsing
2. Building line maps from preprocessor output
3. Transpilation with line tracking
4. Chaining mappings for error reporting
5. Error message patching
"""

import unittest
import sys
import os
import re
from typing import Dict, Tuple, List, Optional
from dataclasses import dataclass

# Add parent directory to path to import blcc
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


# =============================================================================
# Data structures (to be moved to blcc.py)
# =============================================================================

@dataclass
class SourceLocation:
    """Represents a location in a source file"""
    file: str
    line: int
    
    def __str__(self):
        return f"{self.file}:{self.line}"


@dataclass
class LineMarker:
    """Parsed preprocessor line marker"""
    line_num: int
    filename: str
    flags: List[int]
    
    @property
    def is_entering_file(self) -> bool:
        return 1 in self.flags
    
    @property
    def is_returning_from_include(self) -> bool:
        return 2 in self.flags
    
    @property
    def is_system_header(self) -> bool:
        return 3 in self.flags


# =============================================================================
# Reference implementations for testing
# =============================================================================

# Regex to match preprocessor line markers
# Format: # linenum "filename" [flags...]
# Examples:
#   # 1 "main.cpp"
#   # 1 "header.h" 1
#   # 5 "main.cpp" 2
#   # 1 "<built-in>" 3
LINE_MARKER_PATTERN = re.compile(
    r'^#\s+(\d+)\s+"([^"]+)"(?:\s+(.*))?$'
)


def parse_line_marker(line: str) -> Optional[LineMarker]:
    """Parse a preprocessor line marker.
    
    Args:
        line: A line from preprocessor output
        
    Returns:
        LineMarker if the line is a valid marker, None otherwise
    """
    match = LINE_MARKER_PATTERN.match(line.strip())
    if not match:
        return None
    
    line_num = int(match.group(1))
    filename = match.group(2)
    flags_str = match.group(3)
    
    flags = []
    if flags_str:
        flags = [int(f) for f in flags_str.split() if f.isdigit()]
    
    return LineMarker(line_num, filename, flags)


def build_line_map(preprocessor_output: str) -> Dict[int, SourceLocation]:
    """Build a mapping from output line numbers to source locations.
    
    Args:
        preprocessor_output: The output from running cpp/clang -E
        
    Returns:
        Dict mapping output line number -> SourceLocation(file, line)
    """
    line_map = {}
    current_file = None
    current_line = 1
    output_line = 0
    
    for line in preprocessor_output.split('\n'):
        marker = parse_line_marker(line)
        
        if marker:
            # Update current file and line from marker
            current_file = marker.filename
            current_line = marker.line_num
            # Line markers don't produce output, so don't increment output_line
        else:
            # This is a content line
            output_line += 1
            if current_file:
                line_map[output_line] = SourceLocation(current_file, current_line)
            current_line += 1
    
    return line_map


def strip_line_markers(preprocessor_output: str) -> str:
    """Remove line markers from preprocessor output, keeping only content.
    
    Args:
        preprocessor_output: The output from running cpp/clang -E
        
    Returns:
        The content with line markers removed
    """
    lines = []
    for line in preprocessor_output.split('\n'):
        if not parse_line_marker(line):
            lines.append(line)
    return '\n'.join(lines)


# =============================================================================
# Test Cases
# =============================================================================

class TestParseLineMarker(unittest.TestCase):
    """Tests for parse_line_marker function"""

    def test_simple_marker(self):
        """Parse a simple line marker without flags"""
        result = parse_line_marker('# 1 "main.cpp"')
        self.assertIsNotNone(result)
        self.assertEqual(result.line_num, 1)
        self.assertEqual(result.filename, "main.cpp")
        self.assertEqual(result.flags, [])

    def test_marker_with_single_flag(self):
        """Parse marker with entering file flag"""
        result = parse_line_marker('# 1 "header.h" 1')
        self.assertIsNotNone(result)
        self.assertEqual(result.line_num, 1)
        self.assertEqual(result.filename, "header.h")
        self.assertEqual(result.flags, [1])
        self.assertTrue(result.is_entering_file)

    def test_marker_with_return_flag(self):
        """Parse marker with returning from include flag"""
        result = parse_line_marker('# 5 "main.cpp" 2')
        self.assertIsNotNone(result)
        self.assertEqual(result.line_num, 5)
        self.assertEqual(result.filename, "main.cpp")
        self.assertEqual(result.flags, [2])
        self.assertTrue(result.is_returning_from_include)

    def test_marker_with_multiple_flags(self):
        """Parse marker with multiple flags"""
        result = parse_line_marker('# 1 "header.h" 1 3 4')
        self.assertIsNotNone(result)
        self.assertEqual(result.flags, [1, 3, 4])
        self.assertTrue(result.is_entering_file)
        self.assertTrue(result.is_system_header)

    def test_marker_with_builtin(self):
        """Parse marker for built-in definitions"""
        result = parse_line_marker('# 1 "<built-in>" 3')
        self.assertIsNotNone(result)
        self.assertEqual(result.filename, "<built-in>")
        self.assertTrue(result.is_system_header)

    def test_marker_with_command_line(self):
        """Parse marker for command line definitions"""
        result = parse_line_marker('# 1 "<command line>" 1')
        self.assertIsNotNone(result)
        self.assertEqual(result.filename, "<command line>")

    def test_marker_with_spaces_in_path(self):
        """Parse marker with spaces in filename"""
        result = parse_line_marker('# 10 "path with spaces/my file.h" 1')
        self.assertIsNotNone(result)
        self.assertEqual(result.filename, "path with spaces/my file.h")
        self.assertEqual(result.line_num, 10)

    def test_marker_with_windows_path(self):
        """Parse marker with Windows-style path"""
        # In preprocessor output, backslashes are escaped
        result = parse_line_marker(r'# 1 "C:\\Users\\test\\file.h"')
        self.assertIsNotNone(result)
        # The regex captures the escaped form
        self.assertEqual(result.filename, r"C:\\Users\\test\\file.h")

    def test_marker_with_extra_spaces(self):
        """Parse marker with extra whitespace"""
        result = parse_line_marker('#   42   "test.cpp"   1   2')
        self.assertIsNotNone(result)
        self.assertEqual(result.line_num, 42)
        self.assertEqual(result.filename, "test.cpp")
        self.assertEqual(result.flags, [1, 2])

    def test_not_a_marker_regular_code(self):
        """Regular code should not be parsed as marker"""
        self.assertIsNone(parse_line_marker('int x = 5;'))
        self.assertIsNone(parse_line_marker('    return 0;'))
        self.assertIsNone(parse_line_marker(''))

    def test_not_a_marker_preprocessor_directive(self):
        """Preprocessor directives should not be parsed as markers"""
        self.assertIsNone(parse_line_marker('#define FOO 1'))
        self.assertIsNone(parse_line_marker('#include <vector>'))
        self.assertIsNone(parse_line_marker('#pragma once'))
        self.assertIsNone(parse_line_marker('#ifdef DEBUG'))

    def test_not_a_marker_comment(self):
        """Comments should not be parsed as markers"""
        self.assertIsNone(parse_line_marker('// # 1 "fake.cpp"'))
        self.assertIsNone(parse_line_marker('/* # 1 "fake.cpp" */'))


class TestBuildLineMap(unittest.TestCase):
    """Tests for build_line_map function"""

    def test_single_file_no_includes(self):
        """Build line map for a file with no includes"""
        # Note: trailing newline creates an empty line at the end
        preprocessor_output = '# 1 "main.blcpp"\nint main():\n    return 0'
        line_map = build_line_map(preprocessor_output)
        
        self.assertEqual(len(line_map), 2)
        self.assertEqual(line_map[1].file, "main.blcpp")
        self.assertEqual(line_map[1].line, 1)
        self.assertEqual(line_map[2].file, "main.blcpp")
        self.assertEqual(line_map[2].line, 2)

    def test_single_include(self):
        """Build line map with one include"""
        preprocessor_output = '''\
# 1 "main.blcpp"
# 1 "header.blh" 1
int add(int a, int b):
    return a + b
# 3 "main.blcpp" 2
int main():
    return add(1, 2)
'''
        line_map = build_line_map(preprocessor_output)
        
        # Lines 1-2 are from header.blh
        self.assertEqual(line_map[1].file, "header.blh")
        self.assertEqual(line_map[1].line, 1)
        self.assertEqual(line_map[2].file, "header.blh")
        self.assertEqual(line_map[2].line, 2)
        
        # Lines 3-4 are from main.blcpp (starting at line 3)
        self.assertEqual(line_map[3].file, "main.blcpp")
        self.assertEqual(line_map[3].line, 3)
        self.assertEqual(line_map[4].file, "main.blcpp")
        self.assertEqual(line_map[4].line, 4)

    def test_nested_includes(self):
        """Build line map with nested includes"""
        preprocessor_output = '''\
# 1 "main.blcpp"
# 1 "outer.blh" 1
// outer header
# 1 "inner.blh" 1
int inner_func():
    return 1
# 3 "outer.blh" 2
int outer_func():
    return inner_func()
# 3 "main.blcpp" 2
int main():
    return outer_func()
'''
        line_map = build_line_map(preprocessor_output)
        
        # Line 1: outer.blh comment
        self.assertEqual(line_map[1].file, "outer.blh")
        self.assertEqual(line_map[1].line, 1)
        
        # Lines 2-3: inner.blh
        self.assertEqual(line_map[2].file, "inner.blh")
        self.assertEqual(line_map[2].line, 1)
        self.assertEqual(line_map[3].file, "inner.blh")
        self.assertEqual(line_map[3].line, 2)
        
        # Lines 4-5: outer.blh (after inner include)
        self.assertEqual(line_map[4].file, "outer.blh")
        self.assertEqual(line_map[4].line, 3)
        self.assertEqual(line_map[5].file, "outer.blh")
        self.assertEqual(line_map[5].line, 4)
        
        # Lines 6-7: main.blcpp
        self.assertEqual(line_map[6].file, "main.blcpp")
        self.assertEqual(line_map[6].line, 3)
        self.assertEqual(line_map[7].file, "main.blcpp")
        self.assertEqual(line_map[7].line, 4)

    def test_multiple_includes_same_level(self):
        """Build line map with multiple includes at same level"""
        preprocessor_output = '''\
# 1 "main.blcpp"
# 1 "a.blh" 1
int func_a():
    return 1
# 2 "main.blcpp" 2
# 1 "b.blh" 1
int func_b():
    return 2
# 3 "main.blcpp" 2
int main():
    return 0
'''
        line_map = build_line_map(preprocessor_output)
        
        # Lines 1-2: a.blh
        self.assertEqual(line_map[1].file, "a.blh")
        self.assertEqual(line_map[2].file, "a.blh")
        
        # Lines 3-4: b.blh
        self.assertEqual(line_map[3].file, "b.blh")
        self.assertEqual(line_map[4].file, "b.blh")
        
        # Lines 5-6: main.blcpp
        self.assertEqual(line_map[5].file, "main.blcpp")
        self.assertEqual(line_map[6].file, "main.blcpp")

    def test_skip_builtin_markers(self):
        """Built-in markers should be tracked but typically filtered later"""
        # No trailing newline to avoid empty line at end
        preprocessor_output = '''# 1 "main.blcpp"
# 1 "<built-in>" 1
# 1 "<built-in>" 3
# 384 "<built-in>" 3
# 1 "<command line>" 1
# 1 "<built-in>" 2
# 1 "main.blcpp" 2
int main():
    return 0'''
        line_map = build_line_map(preprocessor_output)
        
        # Only the actual code lines should be in the map
        self.assertEqual(len(line_map), 2)
        self.assertEqual(line_map[1].file, "main.blcpp")
        self.assertEqual(line_map[2].file, "main.blcpp")

    def test_empty_lines_preserved(self):
        """Empty lines should be counted in line numbers"""
        # No trailing newline to avoid extra empty line
        preprocessor_output = '''# 1 "main.blcpp"
int x = 1

int y = 2'''
        line_map = build_line_map(preprocessor_output)
        
        self.assertEqual(len(line_map), 3)
        self.assertEqual(line_map[1].line, 1)  # int x = 1
        self.assertEqual(line_map[2].line, 2)  # empty line
        self.assertEqual(line_map[3].line, 3)  # int y = 2


class TestStripLineMarkers(unittest.TestCase):
    """Tests for strip_line_markers function"""

    def test_strip_simple(self):
        """Strip markers from simple output"""
        preprocessor_output = '''\
# 1 "main.blcpp"
int main():
    return 0
'''
        result = strip_line_markers(preprocessor_output)
        expected = '''\
int main():
    return 0
'''
        self.assertEqual(result.strip(), expected.strip())

    def test_strip_with_includes(self):
        """Strip markers from output with includes"""
        preprocessor_output = '''\
# 1 "main.blcpp"
# 1 "header.blh" 1
int add(int a, int b):
    return a + b
# 3 "main.blcpp" 2
int main():
    return add(1, 2)
'''
        result = strip_line_markers(preprocessor_output)
        expected = '''\
int add(int a, int b):
    return a + b
int main():
    return add(1, 2)
'''
        self.assertEqual(result.strip(), expected.strip())

    def test_preserve_preprocessor_directives(self):
        """Preprocessor directives should be preserved"""
        preprocessor_output = '''\
# 1 "main.blcpp"
#pragma once
#define FOO 1
int x = FOO
'''
        result = strip_line_markers(preprocessor_output)
        self.assertIn('#pragma once', result)
        self.assertIn('#define FOO 1', result)


class TestChainedMapping(unittest.TestCase):
    """Tests for chaining preprocessor map with transpile map"""

    def test_chain_simple(self):
        """Test chaining two simple mappings"""
        # Preprocessor map: preprocessed_line -> (file, source_line)
        preproc_map = {
            1: SourceLocation("header.blh", 1),
            2: SourceLocation("header.blh", 2),
            3: SourceLocation("main.blcpp", 3),
            4: SourceLocation("main.blcpp", 4),
        }
        
        # Transpile map: transpiled_line -> preprocessed_line
        transpile_map = {
            1: 1,  # int add() {
            2: 2,  #     return a + b;
            3: 2,  # }  (closing brace maps to last line of block)
            4: 3,  # int main() {
            5: 4,  #     return add(1, 2);
            6: 4,  # }
        }
        
        # Chain: transpiled_line -> (file, source_line)
        def chain_lookup(transpiled_line: int) -> Optional[SourceLocation]:
            preproc_line = transpile_map.get(transpiled_line)
            if preproc_line is None:
                return None
            return preproc_map.get(preproc_line)
        
        # Verify chained lookups
        loc = chain_lookup(1)
        self.assertEqual(loc.file, "header.blh")
        self.assertEqual(loc.line, 1)
        
        loc = chain_lookup(3)  # Closing brace
        self.assertEqual(loc.file, "header.blh")
        self.assertEqual(loc.line, 2)
        
        loc = chain_lookup(5)
        self.assertEqual(loc.file, "main.blcpp")
        self.assertEqual(loc.line, 4)


class TestErrorPatching(unittest.TestCase):
    """Tests for patching compiler error messages"""

    def test_patch_gnu_error(self):
        """Test patching GNU-style error message"""
        error = "/tmp/xyz123.cpp:15:5: error: expected ';'"
        
        # Mapping: line 15 -> header.blh:8
        line_map = {15: SourceLocation("header.blh", 8)}
        
        # Expected: header.blh:8:5: error: expected ';'
        # Implementation would replace the file and line
        pass  # Will implement with actual function

    def test_patch_msvc_error(self):
        """Test patching MSVC-style error message"""
        error = r"C:\temp\xyz123.cpp(15): error C2143: expected ';'"
        
        # Mapping: line 15 -> header.blh:8
        line_map = {15: SourceLocation("header.blh", 8)}
        
        # Expected: header.blh(8): error C2143: expected ';'
        pass  # Will implement with actual function

    def test_patch_preserves_column(self):
        """Column numbers should be preserved when patching"""
        error = "temp.cpp:10:25: error: undeclared identifier"
        # After patching: original.blh:5:25: error: undeclared identifier
        # Column 25 should remain unchanged
        pass

    def test_patch_multiple_errors(self):
        """Test patching multiple errors in output"""
        errors = """\
temp.cpp:10:5: error: expected ';'
temp.cpp:10:5: note: to match this '{'
temp.cpp:15:10: error: undeclared identifier 'foo'
"""
        # Each line should be patched independently
        pass

    def test_no_patch_system_headers(self):
        """Errors in system headers should not be patched"""
        error = "/usr/include/vector:123:5: error: ..."
        # System header paths should be preserved
        pass


# =============================================================================
# Integration test data
# =============================================================================

# Realistic preprocessor output from clang -E
REALISTIC_CLANG_OUTPUT = '''\
# 1 "main.blcpp"
# 1 "<built-in>" 1
# 1 "<built-in>" 3
# 418 "<built-in>" 3
# 1 "<command line>" 1
# 1 "<built-in>" 2
# 1 "main.blcpp" 2
# 1 "./math_utils.blh" 1
// Simple math utilities header
#pragma once

int add(int a, int b):
    return a + b

int multiply(int a, int b):
    return a * b

class Calculator:
public:
    int value

    Calculator() : value(0) {}

    void add(int x):
        value += x

    void subtract(int x):
        value -= x

    int get() const:
        return value
# 2 "main.blcpp" 2

int main():
    int result = add(3, 4)
    result = multiply(result, 2)

    Calculator calc
    calc.add(10)
    calc.subtract(3)

    return calc.get() + result
'''


class TestRealisticScenarios(unittest.TestCase):
    """Tests with realistic preprocessor output"""

    def test_realistic_clang_output(self):
        """Test parsing realistic clang -E output"""
        line_map = build_line_map(REALISTIC_CLANG_OUTPUT)
        
        # First content line should be from math_utils.blh
        self.assertEqual(line_map[1].file, "./math_utils.blh")
        self.assertEqual(line_map[1].line, 1)  # // Simple math utilities header
        
        # Find where main.blcpp content starts
        main_lines = [(k, v) for k, v in line_map.items() if 'main.blcpp' in v.file]
        self.assertTrue(len(main_lines) > 0)

    def test_strip_realistic_output(self):
        """Test stripping markers from realistic output"""
        content = strip_line_markers(REALISTIC_CLANG_OUTPUT)
        
        # Should contain the actual code
        self.assertIn('int add(int a, int b):', content)
        self.assertIn('int main():', content)
        self.assertIn('Calculator calc', content)
        
        # Should not contain line markers
        self.assertNotIn('# 1 "main.blcpp"', content)
        self.assertNotIn('<built-in>', content)


if __name__ == '__main__':
    unittest.main(verbosity=2)
