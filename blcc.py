#!/usr/bin/env python3
"""
Braceless C++ Compiler (blcc)

Converts Python-style indented C++ to regular braced C++.
"""

import sys
import os
import re
import subprocess
import tempfile
import shutil
from typing import List, Tuple, Optional, Set, Dict, Callable
from enum import Enum, auto


class BlockType(Enum):
    NORMAL = auto()
    CLASS = auto()
    STRUCT = auto()
    ENUM = auto()
    UNION = auto()
    SWITCH = auto()
    LAMBDA = auto()
    REGULAR_BRACE = auto()  # Regular C++ braces (don't output closing brace)


class Compiler:
    def __init__(self, lines: List[str]):
        self.lines = [line.rstrip('\n\r') for line in lines]
        self.output = []
        self.current = 0
        self.indent_stack = [0]
        self.block_type_stack = [BlockType.NORMAL]
        self.whitespace_stack = ['']  # Track actual whitespace for closing braces (parallel to indent_stack)
        self.in_block_comment = False
        self.continuation_indent = None
        self.pending_blank_lines = []
        self.paren_depth = 0  # Track unclosed parentheses/brackets
        # Multiline control structure tracking
        self.control_keyword = None  # Tracks if/for/while/switch for multiline conditions
        self.control_condition_lines = []  # Accumulated condition lines
        self.control_start_indent = None  # Indent of the control keyword line
    
    def compile(self) -> str:
        """Compile the braceless C++ to regular C++"""
        while self.current < len(self.lines):
            self._process_line()
            self.current += 1
        
        # Close any remaining blocks
        # Move pending blank lines to after closing braces
        saved_blank_lines = self.pending_blank_lines
        self.pending_blank_lines = []
        
        while len(self.indent_stack) > 1:
            self.indent_stack.pop()  # Pop content indent
            block_type = self.block_type_stack.pop() if len(self.block_type_stack) > 1 else BlockType.NORMAL
            closing_ws = self.whitespace_stack.pop() if len(self.whitespace_stack) > 1 else ''
            self._output_closing_brace(block_type, closing_ws=closing_ws)
        
        # Output any remaining blank lines
        self.output.extend(saved_blank_lines)
        
        return '\n'.join(self.output) + '\n'
    
    def _process_line(self):
        """Process a single line"""
        line = self.lines[self.current]
        
        # Track if we start inside a block comment before updating state
        started_in_comment = self.in_block_comment
        
        # Update block comment state
        self._update_block_comment_state(line)
        
        # If we're inside a block comment (or started in one), output as-is
        if started_in_comment or self.in_block_comment:
            # Check if this line closes the block comment
            if '*/' in line:
                # This line closes the comment
                self.output.append(line)
                return
            else:
                # Still inside block comment
                self.output.append(line)
                return
        
        # Get indent level
        indent = self._get_indent(line)
        content = self._get_content(line)
        # Get the leading whitespace for this line (used when opening blocks)
        leading_ws = self._get_leading_ws(line)
        
        # Check if line is blank or comment-only
        if not content or content.lstrip().startswith('//'):
            # Dedent FIRST if this blank/comment is at a lower indent
            # BUT only if the next non-blank/comment line is also at that indent or lower
            # This prevents wrongly-indented comments from closing blocks
            # ALSO check if next line is an access specifier - those don't cause dedents
            if indent < self.indent_stack[-1]:
                # Check next meaningful line (not blank/comment)
                should_dedent = False
                for i in range(self.current + 1, len(self.lines)):
                    peek_line = self.lines[i]
                    peek_indent = self._get_indent(peek_line)
                    peek_content = self._get_content(peek_line)
                    if peek_content and not peek_content.lstrip().startswith('//'):
                        # Found a real code line
                        # Check if it's an access specifier (public/private/protected:)
                        is_access_specifier = False
                        peek_colon_info = self._find_trailing_colon(peek_content)
                        if peek_colon_info:
                            peek_before_colon = peek_colon_info[0].strip()
                            if peek_before_colon in ['public', 'private', 'protected']:
                                is_access_specifier = True
                        
                        if peek_indent <= indent and not is_access_specifier:
                            # Next code line is at same or lower indent - dedent now
                            should_dedent = True
                        break
                
                if should_dedent:
                    while len(self.indent_stack) > 1 and self.indent_stack[-1] > indent:
                        self.indent_stack.pop()
                        block_type = self.block_type_stack.pop() if len(self.block_type_stack) > 1 else BlockType.NORMAL
                        closing_ws = self.whitespace_stack.pop() if len(self.whitespace_stack) > 1 else ''
                        self._output_closing_brace(block_type, closing_ws)
            
            if not content:
                # Blank line - check if it should be moved after closing braces
                next_line = self._peek_next_line()
                should_buffer = False
                if next_line:
                    next_indent = self._get_indent(next_line)
                    # Buffer only if blank line's indent == dedented level
                    # This means the blank line separates blocks at the same level
                    if next_indent < self.indent_stack[-1] and indent == next_indent:
                        should_buffer = True
                
                if should_buffer:
                    # Buffer the blank line - it will be output after closing braces
                    self.pending_blank_lines.append(line)
                else:
                    # Keep the blank line where it is
                    self._flush_blank_lines()
                    self.output.append(line)
            else:
                # Comment line - check if next line will cause dedent
                next_line = self._peek_next_line()
                should_buffer_comment = False
                if next_line:
                    next_indent = self._get_indent(next_line)
                    # Buffer comment if next line will dedent
                    if next_indent < self.indent_stack[-1]:
                        should_buffer_comment = True
                
                if should_buffer_comment:
                    # Buffer the comment to output after closing braces
                    self.pending_blank_lines.append(line)
                else:
                    # Output comment now - flush pending blank lines first
                    self._flush_blank_lines()
                    self.output.append(line)
            return
        
        # Check if we're in a multiline control structure condition
        if self.control_keyword is not None:
            # We're collecting a multiline control condition
            # Check if this line has the colon
            colon_info = self._find_trailing_colon(content)
            if colon_info:
                # Found the colon - this completes the condition
                before_colon, after_colon = colon_info
                # Accumulate this final line (preserving the full line with indent)
                self.control_condition_lines.append(line[:line.rindex(before_colon) + len(before_colon)])
                
                # Build the complete condition (all lines as-is)
                # Insert opening paren on first line after keyword
                first_line = self.control_condition_lines[0]
                # Find where keyword ends
                keyword_len = len(self.control_keyword)
                keyword_end = first_line.index(self.control_keyword) + keyword_len
                wrapped_first = first_line[:keyword_end] + ' (' + first_line[keyword_end:].lstrip()
                
                # Output all lines
                self.output.append(wrapped_first)
                for i in range(1, len(self.control_condition_lines)):
                    self.output.append(self.control_condition_lines[i])
                
                # Add closing paren and opening brace on the last line
                # Actually need to modify the last output line
                self.output[-1] = self.output[-1] + ') {'
                if after_colon.strip():
                    self.output[-1] += after_colon
                
                # Determine block type
                block_type = self._detect_block_type(self.control_keyword)
                
                # Check next line indent
                next_line = self._peek_next_line()
                if next_line:
                    next_indent = self._get_indent(next_line)
                    next_content = self._get_content(next_line)
                    if next_content and not next_content.startswith('//') and next_indent > self.control_start_indent:
                        self.indent_stack.append(next_indent)
                        self.block_type_stack.append(block_type)
                        # Use opener line's whitespace for closing brace
                        opener_ws = self._get_leading_ws(self.control_condition_lines[0])
                        self.whitespace_stack.append(opener_ws)
                
                # Reset multiline control state
                self.control_keyword = None
                self.control_condition_lines = []
                self.control_start_indent = None
                return
            else:
                # No colon yet - accumulate this line and continue (preserve full line with indent)
                self.control_condition_lines.append(line)
                return
        
        # Check if this line starts a control structure without parentheses (multiline possibility)
        # Must do this BEFORE continuation check
        stripped = content.strip()
        control_keywords = ['if', 'for', 'while', 'switch']
        detected_keyword = None
        for kw in control_keywords:
            if stripped.startswith(kw + ' ') or stripped.startswith(kw + '\t'):
                detected_keyword = kw
                break
        
        # Also handle "else if"
        if stripped.startswith('else if ') or stripped.startswith('else if\t'):
            detected_keyword = 'else if'
        
        if detected_keyword:
            # Special case: check if this is a while clause for do-while (no colon, no block)
            if detected_keyword == 'while' and self._is_do_while():
                # This is do-while's while clause - handle immediately, don't collect multiline
                # (do-while condition doesn't open a block, just ends the do)
                # Let the existing do-while handler process it
                pass  # Fall through to existing logic
            else:
                # Check if line has colon (single-line control) or not (might be multiline)
                colon_info = self._find_trailing_colon(content)
                if not colon_info:
                    # No colon on this line - might be multiline control structure
                    # Check if condition starts with paren (traditional form) or not (braceless form)
                    condition_start = len(detected_keyword)
                    if detected_keyword == 'else if':
                        condition_start = 7
                    
                    condition_part = stripped[condition_start:].lstrip()
                    
                    # If no opening paren, this is braceless form and might be multiline
                    # BUT if it ends with {, it's a single-line control with optional parens + regular brace
                    if not condition_part.startswith('('):
                        # Check if this line has a regular brace (single-line with optional parens)
                        if '{' in content:
                            # Single-line control with optional parens but regular brace
                            # Need to wrap condition and keep the brace
                            # Extract condition (everything before the {)
                            brace_pos = content.index('{')
                            before_brace = content[:brace_pos].rstrip()
                            after_brace = content[brace_pos:]  # { and everything after
                            
                            # Wrap the condition part
                            wrapped = self._wrap_condition_if_needed(before_brace)
                            
                            # Output with the brace, preserving original whitespace
                            self.output.append(self._get_leading_ws(line) + wrapped + ' ' + after_brace)
                            
                            # Track this as a regular brace block
                            next_line = self._peek_next_line()
                            if next_line:
                                next_indent = self._get_indent(next_line)
                                next_content = self._get_content(next_line)
                                if next_content and not next_content.startswith('//') and next_indent > indent:
                                    self.indent_stack.append(next_indent)
                                    self.block_type_stack.append(BlockType.REGULAR_BRACE)
                                    self.whitespace_stack.append('')  # Not used for regular braces
                            return
                        else:
                            # No opening paren and no brace - this is multiline
                            # Start collecting multiline control condition
                            self.control_keyword = detected_keyword
                            self.control_condition_lines = [line]  # Store the full first line with keyword
                            self.control_start_indent = indent
                            return
                    # If has opening paren, let normal continuation handling take over
        
        # Track if we're ending a continuation with a colon
        ending_continuation_with_colon = False
        
        # Check if this is a continuation line
        if self.continuation_indent is not None:
            # We're in a multiline continuation
            if indent >= self.continuation_indent:
                # Still continuing - but check if this line ends with colon (ends the continuation and starts a block)
                colon_info = self._find_trailing_colon(content)
                if colon_info:
                    # This line ends the continuation and starts a block
                    ending_continuation_with_colon = True
                    self.continuation_indent = None
                    # Fall through to handle the colon
                else:
                    # Check if this is the last continuation line
                    # We need to check if cumulative paren/bracket depth is zero
                    # Count net paren/bracket change (can be negative)
                    open_count = content.count('(') + content.count('[')
                    close_count = content.count(')') + content.count(']')
                    self.paren_depth += open_count - close_count
                    
                    is_last_continuation = not self._is_continuation(content) and self.paren_depth <= 0
                    
                    # Check if ending with {} (inline function body in constructor initializer)
                    stripped_content = content.rstrip()
                    if (is_last_continuation and 
                        stripped_content.endswith('{}') and 
                        stripped_content.count('{') == stripped_content.count('}')):
                        # Ends with {} - could be constructor initializer with inline body
                        # Look back to find if this continuation started from a constructor/function
                        # with an initializer list (has : and function signature)
                        is_constructor_init = False
                        
                        for i in range(self.current - 1, -1, -1):
                            prev_line = self.lines[i]
                            prev_indent = self._get_indent(prev_line)
                            prev_content = self._get_content(prev_line)
                            if not prev_content or prev_content.lstrip().startswith('//'):
                                continue
                            # Check if less indented (start of statement)
                            if prev_indent < indent:
                                # Check for patterns:
                                # 1. func() : init... (same line has : and ())
                                # 2. func() followed by line starting with : (multi-line)
                                if ':' in prev_content and '(' in prev_content:
                                    is_constructor_init = True
                                elif '(' in prev_content and ')' in prev_content:
                                    # Function signature - check if CURRENT continuation chain has :
                                    # Look for : in any line between start and current
                                    for j in range(i, self.current + 1):
                                        check_line = self.lines[j]
                                        check_content = self._get_content(check_line)
                                        if ':' in check_content and not check_content.lstrip().startswith('//'):
                                            is_constructor_init = True
                                            break
                                break
                        force_semicolon = not is_constructor_init
                    else:
                        # Force semicolon if ending continuation with } (but not {})
                        force_semicolon = is_last_continuation and stripped_content.endswith('}') and not stripped_content.endswith('{}')
                    
                    self._output_with_semicolon(line, is_continuation=not is_last_continuation, force_semicolon=force_semicolon)
                    if is_last_continuation:
                        self.continuation_indent = None
                        self.paren_depth = 0
                    return
            else:
                # End of continuation
                self.continuation_indent = None
                # Fall through to process this line normally
        
        # Handle dedenting (closing blocks) - but not when started in block comment
        if not started_in_comment and indent < self.indent_stack[-1]:
            # Check if current line is an access specifier - if so, don't close class/struct blocks
            colon_info_check = self._find_trailing_colon(content)
            if colon_info_check:
                before_colon_check = colon_info_check[0]
                stripped_check = before_colon_check.strip()
                if stripped_check in ['public', 'private', 'protected']:
                    # Check if ANY block in the stack is a class/struct
                    has_class_or_struct = any(bt in [BlockType.CLASS, BlockType.STRUCT] 
                                             for bt in self.block_type_stack)
                    if has_class_or_struct:
                        # Save any buffered blank lines
                        saved_access_blank_lines = self.pending_blank_lines
                        self.pending_blank_lines = []
                        
                        # Close any inner blocks (methods, etc.) but keep class/struct open
                        # Find the class/struct level
                        while len(self.indent_stack) > 1:
                            if self.block_type_stack[-1] in [BlockType.CLASS, BlockType.STRUCT]:
                                # Stop - we've reached the class/struct level
                                break
                            # Close inner block
                            self.indent_stack.pop()
                            block_type = self.block_type_stack.pop() if len(self.block_type_stack) > 1 else BlockType.NORMAL
                            closing_ws = self.whitespace_stack.pop() if len(self.whitespace_stack) > 1 else ''
                            if block_type != BlockType.REGULAR_BRACE:
                                self._output_closing_brace(block_type, closing_ws, content)
                        
                        # Output blank lines before the access specifier
                        self.output.extend(saved_access_blank_lines)
                        
                        # Now output the access specifier
                        self.output.append(line)
                        return
            
            # Proceed with normal dedenting
            # Move pending blank lines to after closing braces
            saved_blank_lines = self.pending_blank_lines
            self.pending_blank_lines = []
            
            while len(self.indent_stack) > 1 and self.indent_stack[-1] > indent:
                self.indent_stack.pop()  # Pop the content indent
                block_type = self.block_type_stack.pop() if len(self.block_type_stack) > 1 else BlockType.NORMAL
                closing_ws = self.whitespace_stack.pop() if len(self.whitespace_stack) > 1 else ''
                # Only output closing brace for braceless blocks, not regular braces
                if block_type != BlockType.REGULAR_BRACE:
                    # Pass current line content to help determine if lambda needs semicolon
                    self._output_closing_brace(block_type, closing_ws, content)
            
            # Store blank lines to output later (after potential else/catch merge)
            self.pending_blank_lines = saved_blank_lines
        
        # Check if line is else/catch - if so, DON'T flush blank lines yet
        might_be_else_or_catch = False
        check_colon = self._find_trailing_colon(content)
        if check_colon:
            check_keyword = check_colon[0].strip().split()[0] if check_colon[0].strip() else ""
            if check_keyword in ['else', 'catch']:
                might_be_else_or_catch = True
        
        # Also check for regular brace else/catch
        if content.rstrip().endswith('{'):
            stripped_check = content.strip()
            if stripped_check.startswith('else ') or stripped_check.startswith('catch '):
                might_be_else_or_catch = True
        
        # Flush pending blank lines before processing a code line (unless it's else/catch)
        if not might_be_else_or_catch:
            self._flush_blank_lines()
        
        # Check if line ends with a regular opening brace {
        # We need to track the content indent for proper nesting
        if content.rstrip().endswith('{') and not content.rstrip().endswith('{{'):
            # Check if this line is 'else {' or 'catch {' (regular brace, not colon)
            # If so, merge with previous closing brace
            stripped_content = content.strip()
            if (stripped_content.startswith('else ') or stripped_content.startswith('catch ')) and '{' in stripped_content:
                if self.output and self.output[-1].strip() == '}':
                    # Merge with previous closing brace
                    self.output.pop()
                    self.output.append(self._get_leading_ws(line) + '} ' + stripped_content)
                    # Still need to track the indent for regular braces
                    next_line = self._peek_next_line()
                    if next_line:
                        next_indent = self._get_indent(next_line)
                        if next_indent > indent:
                            self.indent_stack.append(next_indent)
                            self.block_type_stack.append(BlockType.REGULAR_BRACE)
                            self.whitespace_stack.append('')  # Not used for regular braces
                    return
            
            # Regular brace - track the content indent
            self.output.append(line)
            next_line = self._peek_next_line()
            if next_line:
                next_indent = self._get_indent(next_line)
                next_content = self._get_content(next_line)
                if next_content and not next_content.startswith('//') and next_indent > indent:
                    # Track this indent level for proper closing brace placement
                    self.indent_stack.append(next_indent)
                    self.block_type_stack.append(BlockType.REGULAR_BRACE)
                    self.whitespace_stack.append('')  # Not used for regular braces
            return
        
        # Check if line has } while (do-while on same line)
        stripped_content = content.strip()
        if stripped_content.startswith('} while ') or stripped_content.startswith('} while('):
            # This is a do-while with } and while on the same line
            if self._is_do_while():
                # Extract the while part
                while_part = stripped_content[2:].lstrip()  # Skip '} '
                # Extract condition after 'while'
                if while_part.startswith('while '):
                    condition_part = while_part[6:].lstrip()  # 6 = len('while ')
                elif while_part.startswith('while('):
                    condition_part = while_part[5:]  # 5 = len('while')
                else:
                    condition_part = while_part
                
                # Remove trailing comment if present
                comment_pos = self._find_line_comment(condition_part)
                trailing_part = ""
                if comment_pos is not None:
                    # Keep whitespace before comment
                    code_part = condition_part[:comment_pos].rstrip()
                    spaces_before_comment = condition_part[len(code_part):comment_pos]
                    trailing_part = spaces_before_comment + condition_part[comment_pos:]
                    condition_part = code_part
                else:
                    condition_part = condition_part.rstrip()
                
                # Check if condition is already wrapped in parens
                if not (condition_part.startswith('(') and condition_part.endswith(')')):
                    # Wrap the condition
                    wrapped_content = '} while (' + condition_part + ');'
                else:
                    wrapped_content = '} while ' + condition_part + ';'
                
                # Add trailing part back (with whitespace and comment)
                if trailing_part:
                    wrapped_content += trailing_part
                
                self.output.append(self._get_leading_ws(line) + wrapped_content)
                return
        
        # Check if line is a regular closing brace
        if content.strip() == '}':
            # Check if we need to pop from stack
            if len(self.indent_stack) > 1 and indent < self.indent_stack[-1]:
                # Pop the tracked regular brace indent
                self.indent_stack.pop()
                if len(self.block_type_stack) > 1:
                    self.block_type_stack.pop()
                if len(self.whitespace_stack) > 1:
                    self.whitespace_stack.pop()
            self.output.append(line)
            return
        
        # Check if line starts a block (ends with colon)
        colon_info = self._find_trailing_colon(content)
        
        if colon_info:
            # Line ends with colon
            before_colon, after_colon = colon_info
            
            # Special cases that keep the colon
            if self._should_keep_colon(before_colon):
                # case, default - don't start a block
                self.output.append(self._get_leading_ws(line) + before_colon + ':' + after_colon)
                return
            
            # Determine block type
            block_type = self._detect_block_type(before_colon)
            
            # Handle special keywords
            stripped_before = before_colon.strip()
            keyword = stripped_before.split()[0] if stripped_before else ""
            
            # Check if this is else/catch (including else if)
            if keyword in ['else', 'catch']:
                # Wrap condition if needed (for else if)
                wrapped = self._wrap_condition_if_needed(stripped_before)
                leading_ws = self._get_leading_ws(line)
                
                # These go on same line as closing brace
                if self.output and self.output[-1].strip() == '}':
                    self.output.pop()
                    self.output.append(leading_ws + '} ' + wrapped + ' {' + after_colon)
                    # NOW flush blank lines after the merge
                    self._flush_blank_lines()
                else:
                    # Flush blank lines before outputting else/catch without merge
                    self._flush_blank_lines()
                    self.output.append(leading_ws + wrapped + ' {' + after_colon)
                
                # Start new block - need to track content indent, not the else line's indent
                # Check next line's indent
                next_line = self._peek_next_line()
                if next_line:
                    next_indent = self._get_indent(next_line)
                    next_content = self._get_content(next_line)
                    if next_content and not next_content.startswith('//') and next_indent > indent:
                        self.indent_stack.append(next_indent)
                        self.block_type_stack.append(block_type)
                        self.whitespace_stack.append(leading_ws)  # Use opener's whitespace
                else:
                    # No next line or not indented - empty block
                    self.indent_stack.append(indent + 4)
                    self.block_type_stack.append(block_type)
                    self.whitespace_stack.append(leading_ws)  # Use opener's whitespace
                
                self.continuation_indent = None
                return
            
            # Regular block start - replace : with {
            # Flush any pending blank lines first
            self._flush_blank_lines()
            
            # Check if we need to wrap condition in parentheses (optional parens feature)
            before_colon_wrapped = self._wrap_condition_if_needed(before_colon)
            
            # Preserve original leading whitespace from input
            output_line = self._get_leading_ws(line) + before_colon_wrapped + ' {' + after_colon
            self.output.append(output_line)
            
            # Check if next line has increased indent
            next_line = self._peek_next_line()
            if next_line:
                next_indent = self._get_indent(next_line)
                next_content = self._get_content(next_line)
                
                # If this is a class/struct and next line is an access specifier, look further
                if block_type in [BlockType.CLASS, BlockType.STRUCT] and next_content:
                    # Check if next line is access specifier
                    next_colon_info = self._find_trailing_colon(next_content)
                    if next_colon_info:
                        before_next_colon = next_colon_info[0].strip()
                        if before_next_colon in ['public', 'private', 'protected']:
                            # Look at the line after the access specifier
                            for i in range(self.current + 2, len(self.lines)):
                                peek_line = self.lines[i]
                                peek_indent = self._get_indent(peek_line)
                                peek_content = self._get_content(peek_line)
                                if peek_content and not peek_content.startswith('//'):
                                    next_indent = peek_indent
                                    next_content = peek_content
                                    break
                
                if next_content and not next_content.startswith('//'):
                    # Determine the base indent to compare against
                    # For continuation-ending colons, use the indent of the original line
                    # Otherwise use current line's indent
                    opener_ws = leading_ws  # Default to current line's whitespace
                    if ending_continuation_with_colon:
                        # The original line is where continuation_indent was set
                        # That was the first line of this multi-line statement
                        base_indent = 0  # Default
                        # Find the line that started the continuation
                        for i in range(self.current - 1, -1, -1):
                            prev_line = self.lines[i]
                            prev_indent = self._get_indent(prev_line)
                            prev_content = self._get_content(prev_line)
                            # Skip blanks and comments
                            if not prev_content or prev_content.lstrip().startswith('//'):
                                continue
                            # This is a code line - check if it's the start
                            if prev_indent < indent:
                                # This line is less indented, so it's the start
                                base_indent = prev_indent
                                opener_ws = self._get_leading_ws(prev_line)  # Use original opener's whitespace
                                break
                    else:
                        base_indent = indent
                    
                    # Check if next line is indented relative to the base
                    if next_indent > base_indent:
                        # Next line is part of the block
                        self.indent_stack.append(next_indent)
                        self.block_type_stack.append(block_type)
                        self.whitespace_stack.append(opener_ws)  # Use opener's whitespace
                    elif next_content.strip() == 'pass':
                        # Empty block
                        self.indent_stack.append(base_indent + 4)
                        self.block_type_stack.append(block_type)
                        self.whitespace_stack.append(opener_ws)  # Use opener's whitespace
            
            # Clear continuation since we've started a block
            self.continuation_indent = None
            return
        
        # Check if this is part of a do-while closing
        if self._is_while_clause_for_do(content):
            # This is "while (condition)" after a do block
            # The dedent logic already closed the do block and popped the stack
            # Need to wrap condition in parens if not already wrapped
            stripped_content = content.strip()
            
            # Extract the condition after 'while'
            if stripped_content.startswith('while '):
                condition_part = stripped_content[6:].lstrip()  # 6 = len('while ')
                
                # Remove trailing comment to check parens
                comment_pos = self._find_line_comment(condition_part)
                trailing_part = ""
                if comment_pos is not None:
                    code_part = condition_part[:comment_pos].rstrip()
                    spaces_before_comment = condition_part[len(code_part):comment_pos]
                    trailing_part = spaces_before_comment + condition_part[comment_pos:]
                    condition_part = code_part
                else:
                    condition_part = condition_part.rstrip()
                
                # Check if already has parens wrapping entire condition
                if not (condition_part.startswith('(') and condition_part.endswith(')')):
                    # Wrap the condition
                    wrapped_content = 'while (' + condition_part + ');'
                else:
                    wrapped_content = 'while ' + condition_part + ';'
                
                # Add trailing part back
                if trailing_part:
                    wrapped_content += trailing_part
            else:
                wrapped_content = stripped_content + ';'
            
            if self.output and self.output[-1].strip() == '}':
                self.output.pop()
                self.output.append(self._get_leading_ws(line) + '} ' + wrapped_content)
            else:
                self.output.append(self._get_leading_ws(line) + wrapped_content)
            return
        
        # Regular statement - check if it needs semicolon
        # Check if this line ends with continuation character
        is_continuing = self._is_continuation(content)
        self._output_with_semicolon(line, is_continuation=is_continuing)
        
        if is_continuing:
            self.continuation_indent = indent
            # Initialize paren depth for this continuation (can be negative)
            open_count = content.count('(') + content.count('[')
            close_count = content.count(')') + content.count(']')
            self.paren_depth = open_count - close_count
    
    def _output_with_semicolon(self, line: str, is_continuation=False, force_semicolon=False):
        """Output a line, adding semicolon if needed"""
        content = self._get_content(line)
        # Preserve the original leading whitespace (tabs and spaces)
        leading_ws = line[:len(line) - len(line.lstrip(' \t'))]
        
        if not content.strip():
            self.output.append(line)
            return
        
        # Check if line is 'pass'
        if content.strip() == 'pass':
            return
        
        # Check if we're inside an enum - enum items don't need semicolons
        if self.block_type_stack and self.block_type_stack[-1] == BlockType.ENUM:
            # Inside an enum, items don't need semicolons
            self.output.append(line)
            return
        
        # Check if needs semicolon
        if (not force_semicolon and not self._needs_semicolon(content)) or is_continuation:
            self.output.append(line)
            return
        
        # Add semicolon
        # Find where to add it (before comments, preserving trailing whitespace)
        
        # Find comment start in the original content
        comment_pos = self._find_line_comment(content)
        
        if comment_pos is not None:
            # Preserve spacing - find where code ends (last non-space before comment)
            before_comment_with_spaces = content[:comment_pos]
            code_part = before_comment_with_spaces.rstrip()
            spaces_before_comment = before_comment_with_spaces[len(code_part):]
            comment_part = content[comment_pos:]  # Preserve trailing whitespace in comment
            result = leading_ws + code_part + ';' + spaces_before_comment + comment_part
        else:
            # No comment - preserve trailing whitespace from input
            code_part = content.rstrip()
            trailing_spaces = content[len(code_part):]
            result = leading_ws + code_part + ';' + trailing_spaces
        
        self.output.append(result)
    
    def _output_closing_brace(self, block_type: BlockType, closing_ws: str = "", current_line_content: str = ""):
        """Output a closing brace with optional semicolon"""
        # Check if block needs semicolon
        needs_semicolon = block_type in [BlockType.CLASS, BlockType.STRUCT, BlockType.ENUM, BlockType.UNION, BlockType.LAMBDA]
        
        # For lambdas, check if current or next line is a continuation
        if block_type == BlockType.LAMBDA:
            # Check current line (the line that triggered the dedent)
            current_stripped = current_line_content.lstrip()
            if current_stripped.startswith('),') or current_stripped.startswith(')'):
                needs_semicolon = False
            else:
                # Check next line
                next_line = self._peek_next_line()
                if next_line:
                    next_content = next_line.lstrip()
                    # If next line starts with continuation markers, lambda is part of larger expression
                    if next_content and next_content[0] in '),;':
                        needs_semicolon = False
        
        closing = closing_ws + '}'
        if needs_semicolon:
            closing += ';'
        
        self.output.append(closing)
    
    def _get_indent(self, line: str) -> int:
        """Calculate visual indentation level (tabs count as 4 spaces)"""
        indent = 0
        for ch in line:
            if ch == ' ':
                indent += 1
            elif ch == '\t':
                indent += 4
            else:
                break
        return indent
    
    def _get_content(self, line: str) -> str:
        """Get the content of a line (everything after leading whitespace)"""
        return line.lstrip(' \t')
    
    def _get_leading_ws(self, line: str) -> str:
        """Get the original leading whitespace (tabs and spaces) from a line"""
        return line[:len(line) - len(line.lstrip(' \t'))]
    
    def _flush_blank_lines(self):
        """Output any pending blank lines"""
        if self.pending_blank_lines:
            self.output.extend(self.pending_blank_lines)
            self.pending_blank_lines = []
    
    def _update_block_comment_state(self, line: str):
        """Update whether we're inside a block comment"""
        # Scan for /* and */
        i = 0
        while i < len(line):
            if not self.in_block_comment and i + 1 < len(line) and line[i:i+2] == '/*':
                self.in_block_comment = True
                i += 2
            elif self.in_block_comment and i + 1 < len(line) and line[i:i+2] == '*/':
                self.in_block_comment = False
                i += 2
            else:
                i += 1
    
    def _find_trailing_colon(self, content: str) -> Optional[Tuple[str, str]]:
        """Find if line ends with colon outside strings/comments"""
        if not content:
            return None
        
        in_string = False
        string_delim = None
        last_colon = None
        i = 0
        
        while i < len(content):
            ch = content[i]
            
            # Escape sequences
            if i > 0 and content[i-1] == '\\':
                i += 1
                continue
            
            # Line comments
            if not in_string and i + 1 < len(content) and content[i:i+2] == '//':
                break
            
            # Strings
            if ch == '"' and not in_string:
                in_string = True
                string_delim = '"'
            elif ch == '"' and in_string and string_delim == '"':
                in_string = False
            elif ch == "'" and not in_string:
                in_string = True
                string_delim = "'"
            elif ch == "'" and in_string and string_delim == "'":
                in_string = False
            elif not in_string and ch == ':':
                last_colon = i
            
            i += 1
        
        if last_colon is not None:
            after = content[last_colon + 1:]
            # Check what comes after the colon
            after_stripped = after.strip()
            # Only treat as block-starting colon if there's nothing after except whitespace/comments
            if not after_stripped or after_stripped.startswith('//'):
                return (content[:last_colon].rstrip(), after)
        
        return None
    
    def _should_keep_colon(self, before_colon: str) -> bool:
        """Check if colon should be kept (case, default, etc.)"""
        stripped = before_colon.strip()
        return (stripped.startswith('case ') or 
                stripped == 'default' or
                stripped in ['public', 'private', 'protected'])
    
    def _wrap_condition_if_needed(self, before_colon: str) -> str:
        """Wrap condition in parentheses if it's a control structure without parens (optional parens feature)"""
        stripped = before_colon.strip()
        
        # Control keywords that need condition wrapping
        control_keywords = ['if', 'for', 'while', 'switch']
        
        # Check if line starts with a control keyword
        keyword = None
        for kw in control_keywords:
            if stripped.startswith(kw + ' ') or stripped.startswith(kw + '\t'):
                keyword = kw
                break
        
        # Also handle "else if"
        if stripped.startswith('else if ') or stripped.startswith('else if\t'):
            keyword = 'else if'
        
        if not keyword:
            # Not a control structure, return as-is
            return before_colon
        
        # Extract condition part after keyword
        condition_start = len(keyword)
        if stripped.startswith('else if'):
            condition_start = 7  # len('else if')
        
        condition_part = stripped[condition_start:].lstrip()
        
        # Check if condition is already wrapped in parentheses
        if condition_part.startswith('('):
            # Already has parentheses - check if they wrap the entire condition
            # Find matching closing paren
            paren_depth = 0
            for i, ch in enumerate(condition_part):
                if ch == '(':
                    paren_depth += 1
                elif ch == ')':
                    paren_depth -= 1
                    if paren_depth == 0:
                        # Found matching paren
                        if i == len(condition_part) - 1:
                            # Parens wrap entire condition, return as-is
                            return before_colon
                        # Parens don't wrap everything, fall through to wrap
                        break
        
        # No parens or partial parens - wrap the condition
        # Preserve leading whitespace from original
        leading_ws = before_colon[:len(before_colon) - len(before_colon.lstrip())]
        
        # Build output with wrapped condition
        if keyword == 'else if':
            result = leading_ws + 'else if (' + condition_part + ')'
        else:
            result = leading_ws + keyword + ' (' + condition_part + ')'
        
        return result
    
    def _detect_block_type(self, before_colon: str) -> BlockType:
        """Detect what type of block is starting"""
        stripped = before_colon.strip()
        
        # Check for enum first (before class) to handle "enum class"
        if stripped.startswith('enum ') or ' enum ' in stripped:
            return BlockType.ENUM
        if stripped.startswith('class ') or ' class ' in stripped:
            return BlockType.CLASS
        if stripped.startswith('struct ') or ' struct ' in stripped:
            return BlockType.STRUCT
        if stripped.startswith('union ') or ' union ' in stripped:
            return BlockType.UNION
        if stripped.startswith('switch '):
            return BlockType.SWITCH
        # Lambda detection: look for [](...) or [&](...) or [=](...) pattern
        if '[]' in stripped or '[&]' in stripped or '[=]' in stripped or (stripped.startswith('[') and '](' in stripped):
            return BlockType.LAMBDA
        
        return BlockType.NORMAL
    
    def _peek_next_line(self) -> Optional[str]:
        """Peek at the next non-blank, non-comment line"""
        for i in range(self.current + 1, len(self.lines)):
            line = self.lines[i]
            content = line.lstrip()
            if content and not content.startswith('//'):
                return line
        return None
    
    def _is_do_while(self) -> bool:
        """Check if we're currently in a do-while loop"""
        for i in range(len(self.output) - 1, -1, -1):
            line = self.output[i].strip()
            if line.startswith('do {'):
                return True
            if line.endswith('{') and 'do' not in line:
                return False
        return False
    
    def _is_while_clause_for_do(self, content: str) -> bool:
        """Check if this is the while clause of a do-while loop"""
        stripped = content.strip()
        if stripped.startswith('while ') or stripped.startswith('while('):
            return self._is_do_while()
        return False
    
    def _needs_semicolon(self, content: str) -> bool:
        """Check if line needs a semicolon"""
        stripped = content.rstrip()
        
        # Remove line comments
        comment_pos = self._find_line_comment(stripped)
        if comment_pos is not None:
            stripped = stripped[:comment_pos].rstrip()
        
        if not stripped:
            return False
        
        # Check if line starts with continuation from previous line
        first_non_space = stripped.lstrip()
        if first_non_space and first_non_space[0] == ',':
            # Line starts with comma - continuation from previous, no semicolon
            return False
        # Line starting with . is a method chain - check if there's more chaining after
        if first_non_space and first_non_space[0] == '.':
            # Check if next line also starts with . (more chaining)
            next_line = self._peek_next_line()
            if next_line:
                next_content = next_line.lstrip()
                if next_content.startswith('.'):
                    # More chaining continues, no semicolon
                    return False
            # Last line in chain or no more chaining - needs semicolon (will be determined by other rules)
            # Fall through to other checks
        # Line starting with ) followed by comma is a continuation
        if first_non_space.startswith('),'):
            # ), - part of multi-line call, no semicolon
            return False
        
        last_char = stripped[-1]
        
        # Already has semicolon
        if last_char in ';':
            return False
        
        # Opening brace - no semicolon
        if last_char == '{':
            return False
        
        # Closing brace - check context
        if last_char == '}':
            # Check if it looks like an initializer (has = { pattern)
            # Look for assignment followed by opening brace
            if '= {' in stripped or '={' in stripped:
                # Likely an initializer like "int arr[] = {1, 2, 3}"
                return True
            # Check for lambda (assignment, return, or statement): has lambda pattern [](...) { }
            if '[' in stripped and ']' in stripped and '(' in stripped and '{' in stripped:
                # Count braces to see if this is a complete lambda expression (not just opening a lambda block)
                if stripped.count('{') == stripped.count('}'):
                    # Complete lambda expression - check if it needs semicolon
                    # Needs semicolon if: assignment, return, or statement
                    if '=' in stripped or stripped.lstrip().startswith('return'):
                        return True
            # Check if line starts with : (constructor initializer list) and has inline body
            if first_non_space.startswith(':') and '{' in stripped and stripped.count('{') == stripped.count('}'):
                # Constructor initializer list with inline body like : member(value) {} - no semicolon
                return False
            # Otherwise no semicolon needed (block closing or inline block)
            return False
        
        # Preprocessor directive
        if stripped.lstrip().startswith('#'):
            return False
        
        # Check for ++ or -- (not continuation)
        if len(stripped) >= 2 and stripped[-2:] in ['++', '--']:
            return True
        
        # Continuation character
        if last_char in '+-*/%&|^=<>,([':
            return False
        
        # Check if line ends with ) and next line starts with ) or , or . (multi-line function call or method chain)
        if last_char == ')':
            next_line = self._peek_next_line()
            if next_line:
                next_content = next_line.lstrip()
                if next_content and next_content[0] in '),.':
                    # Check if next line is dedenting AND we're in a braceless block
                    next_indent = self._get_indent(next_line)
                    current_indent = self._get_indent(content) if hasattr(content, '__len__') else 0
                    # If we're processing a line, we need to get its original indent from the source
                    if self.current < len(self.lines):
                        current_indent = self._get_indent(self.lines[self.current])
                    if next_indent < current_indent:
                        # Next line is dedenting - check if we're in a braceless block
                        # If our current indent is in the indent_stack, we're in a braceless block
                        if current_indent in self.indent_stack:
                            # We're in a braceless block and dedenting - need semicolon
                            return True
                    # Next line continues the call or we're not in braceless block, so no semicolon
                    return False
        
        return True
    
    def _is_continuation(self, content: str) -> bool:
        """Check if line is a continuation"""
        stripped = content.rstrip()
        
        # Remove comments
        comment_pos = self._find_line_comment(stripped)
        if comment_pos is not None:
            stripped = stripped[:comment_pos].rstrip()
        
        if not stripped:
            return False
        
        # Check for ++ or -- (not continuation)
        if len(stripped) >= 2 and stripped[-2:] in ['++', '--']:
            return False
        
        last_char = stripped[-1]
        
        # Continuation characters
        if last_char in '+-*/%&|^=<>,([{':
            return True
        
        # String literal continuation - only if next line starts with a string
        if last_char == '"':
            next_line = self._peek_next_line()
            if next_line:
                next_content = next_line.lstrip()
                if next_content.startswith('"'):
                    return True
        
        # Check if we have unclosed parentheses or brackets (outside strings)
        paren_count = self._count_unmatched_parens(stripped)
        if paren_count > 0:
            return True
        
        # Check if line ends with ) and next line starts with : (constructor initializer list)
        if last_char == ')':
            next_line = self._peek_next_line()
            if next_line:
                next_content = next_line.lstrip()
                if next_content.startswith(':'):
                    return True
        
        return False
    
    def _count_unmatched_parens(self, text: str) -> int:
        """Count unmatched opening parentheses/brackets outside of strings"""
        in_string = False
        string_delim = None
        paren_depth = 0
        bracket_depth = 0
        
        i = 0
        while i < len(text):
            ch = text[i]
            
            # Handle escape sequences
            if i > 0 and text[i-1] == '\\':
                i += 1
                continue
            
            # Track string state
            if ch == '"' and not in_string:
                in_string = True
                string_delim = '"'
            elif ch == '"' and in_string and string_delim == '"':
                in_string = False
            elif ch == "'" and not in_string:
                in_string = True
                string_delim = "'"
            elif ch == "'" and in_string and string_delim == "'":
                in_string = False
            elif not in_string:
                if ch == '(':
                    paren_depth += 1
                elif ch == ')':
                    paren_depth -= 1
                elif ch == '[':
                    bracket_depth += 1
                elif ch == ']':
                    bracket_depth -= 1
            
            i += 1
        
        return max(0, paren_depth + bracket_depth)
    
    def _find_line_comment(self, text: str) -> Optional[int]:
        """Find the position of // comment start"""
        in_string = False
        for i in range(len(text)):
            if i > 0 and text[i-1] == '\\':
                continue
            if text[i] == '"':
                in_string = not in_string
            if not in_string and i + 1 < len(text) and text[i:i+2] == '//':
                return i
        return None


# =============================================================================
# Compiler Wrapper Infrastructure
# =============================================================================


class TrackedOutputList(list):
    """A list that tracks source line mappings for each appended item"""
    
    def __init__(self, get_source_line_func):
        super().__init__()
        self._get_source_line = get_source_line_func
        self.source_lines: List[int] = []
    
    def append(self, item):
        super().append(item)
        self.source_lines.append(self._get_source_line())
    
    def extend(self, items):
        for item in items:
            self.append(item)


class LineMapper:
    """Provides source line lookup from tracked output"""
    
    def __init__(self, tracked_output: TrackedOutputList):
        self._tracked_output = tracked_output
    
    def get_source_line(self, output_line: int) -> int:
        """Get the source line for a given output line (1-based)"""
        idx = output_line - 1
        if 0 <= idx < len(self._tracked_output.source_lines):
            return self._tracked_output.source_lines[idx]
        return output_line


class MappingCompiler(Compiler):
    """Extended compiler that tracks line number mappings at the point of emission"""
    
    def __init__(self, lines: List[str]):
        super().__init__(lines)
        self._source_line_context = 1
        self.output = TrackedOutputList(lambda: self._source_line_context)
        self.line_mapper = LineMapper(self.output)
    
    def compile(self) -> str:
        """Compile the braceless C++ to regular C++, tracking line mappings"""
        while self.current < len(self.lines):
            self._source_line_context = self.current + 1
            self._process_line()
            self.current += 1
        
        self._source_line_context = len(self.lines) if self.lines else 1
        saved_blank_lines = self.pending_blank_lines
        self.pending_blank_lines = []
        
        while len(self.indent_stack) > 1:
            self.indent_stack.pop()
            block_type = self.block_type_stack.pop() if len(self.block_type_stack) > 1 else self.block_type_stack[0]
            closing_ws = self.whitespace_stack.pop() if len(self.whitespace_stack) > 1 else ''
            self._output_closing_brace(block_type, closing_ws=closing_ws)
        
        self.output.extend(saved_blank_lines)
        
        return '\n'.join(self.output) + '\n'


class ErrorFormat(Enum):
    """Compiler error message formats"""
    MSVC = auto()      # file(line): error/warning
    GNU = auto()       # file:line:col: error/warning


# MSVC-style: file(line): or file(line,col):
MSVC_ERROR_PATTERN = re.compile(
    r'^(.*?)\((\d+)(,\d+)?\)\s*:\s*(error|warning|note|fatal error)',
    re.IGNORECASE
)

# GNU-style: file:line:col: or file:line:
GNU_ERROR_PATTERN = re.compile(
    r'^(.+?):(\d+):(\d+)?:?\s*(error|warning|note|fatal error)',
    re.IGNORECASE
)


def is_blcpp_file(filepath: str) -> bool:
    """Check if a file is a braceless C++ file"""
    return filepath.lower().endswith('.blcpp')


def is_blh_file(filepath: str) -> bool:
    """Check if a file is a braceless C++ header"""
    return filepath.lower().endswith('.blh')


# Pattern to match #include "*.blh" directives
BLH_INCLUDE_PATTERN = re.compile(r'^(\s*)#\s*include\s*"([^"]*\.blh)"', re.IGNORECASE)


def resolve_include(filename: str, search_dirs: List[str]) -> Optional[str]:
    """Find a header file in search directories.
    
    Args:
        filename: The filename from the #include directive
        search_dirs: List of directories to search
        
    Returns:
        Absolute path to the file if found, None otherwise
    """
    for dir_path in search_dirs:
        full_path = os.path.join(dir_path, filename)
        if os.path.exists(full_path):
            return os.path.abspath(full_path)
    return None


def expand_blh_includes(
    source_path: str,
    include_dirs: List[str] = None,
    included_files: Set[str] = None
) -> Tuple[List[str], Dict[int, Tuple[str, int]]]:
    """Expand all #include "*.blh" directives recursively.
    
    This function reads a source file and inlines any .blh headers it includes,
    tracking the original source location of each line.
    
    Args:
        source_path: Path to the source file to process
        include_dirs: Additional directories to search for headers
        included_files: Set of already-included files (for #pragma once handling)
        
    Returns:
        Tuple of:
        - lines: List of lines with .blh content inlined
        - line_map: Dict mapping output_line_num -> (original_file, original_line_num)
    """
    if included_files is None:
        included_files = set()
    
    source_path = os.path.abspath(source_path)
    source_dir = os.path.dirname(source_path)
    search_dirs = [source_dir] + (include_dirs or [])
    
    lines = []
    line_map = {}
    
    try:
        with open(source_path, 'r', encoding='utf-8') as f:
            source_lines = f.readlines()
    except FileNotFoundError:
        raise FileNotFoundError(f"Cannot open source file: {source_path}")
    
    for src_line_num, line in enumerate(source_lines, 1):
        match = BLH_INCLUDE_PATTERN.match(line)
        
        if match:
            indent = match.group(1)
            blh_name = match.group(2)
            blh_path = resolve_include(blh_name, search_dirs)
            
            if blh_path is None:
                # Header not found - keep the include line as-is
                # The C++ compiler will report the error
                output_line = len(lines) + 1
                lines.append(line)
                line_map[output_line] = (source_path, src_line_num)
            elif blh_path in included_files:
                # Already included (handles #pragma once semantics)
                # Skip this include entirely
                pass
            else:
                # Expand the header
                included_files.add(blh_path)
                sub_lines, sub_map = expand_blh_includes(blh_path, include_dirs, included_files)
                
                # Add all lines from the included file
                base_output_line = len(lines)
                for i, sub_line in enumerate(sub_lines):
                    output_line = base_output_line + i + 1
                    lines.append(sub_line)
                    # Copy the source location from the sub-expansion
                    line_map[output_line] = sub_map[i + 1]
        else:
            # Regular line - add it with its source location
            output_line = len(lines) + 1
            lines.append(line)
            line_map[output_line] = (source_path, src_line_num)
    
    return lines, line_map


def extract_include_dirs(args: List[str]) -> List[str]:
    """Extract include directories from compiler arguments.
    
    Handles both -I dir and -Idir forms.
    """
    include_dirs = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == '-I' and i + 1 < len(args):
            include_dirs.append(args[i + 1])
            i += 2
        elif arg.startswith('-I'):
            include_dirs.append(arg[2:])
            i += 1
        elif arg.startswith('/I'):  # MSVC style
            if len(arg) > 2:
                include_dirs.append(arg[2:])
            elif i + 1 < len(args):
                include_dirs.append(args[i + 1])
                i += 1
            i += 1
        else:
            i += 1
    return include_dirs


class SourceLocationMapper:
    """Maps transpiled line numbers back to original source file locations.
    
    This handles the case where .blh files have been expanded inline,
    so errors can be reported with the correct original file and line.
    """
    
    def __init__(self, blh_line_map: Dict[int, Tuple[str, int]], transpile_mapper: LineMapper):
        """
        Args:
            blh_line_map: Maps expanded_line -> (original_file, original_line)
            transpile_mapper: Maps transpiled_line -> expanded_line
        """
        self._blh_map = blh_line_map
        self._transpile_mapper = transpile_mapper
    
    def get_source_location(self, transpiled_line: int) -> Tuple[str, int]:
        """Get the original source file and line for a transpiled line number.
        
        Returns:
            Tuple of (original_file_path, original_line_number)
        """
        # First map transpiled line to expanded line
        expanded_line = self._transpile_mapper.get_source_line(transpiled_line)
        # Then map expanded line to original source location
        if expanded_line in self._blh_map:
            return self._blh_map[expanded_line]
        # Fallback: return unknown location
        return ("<unknown>", expanded_line)


def transpile_file(source_path: str, output_path: str, include_dirs: List[str] = None) -> SourceLocationMapper:
    """Transpile a braceless C++ file to regular C++.
    
    This function expands any #include "*.blh" directives, transpiles the
    combined braceless code to braced C++, and returns a mapper that can
    translate transpiled line numbers back to original source locations.
    
    Args:
        source_path: Path to the .blcpp source file
        output_path: Path where the transpiled .cpp will be written
        include_dirs: Additional directories to search for .blh headers
        
    Returns:
        SourceLocationMapper for mapping error line numbers back to original files
    """
    # Expand .blh includes recursively
    lines, blh_line_map = expand_blh_includes(source_path, include_dirs)
    
    # Transpile the expanded content
    compiler = MappingCompiler(lines)
    output = compiler.compile()
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(output)
    
    # Return a mapper that chains: transpiled_line -> expanded_line -> (file, line)
    return SourceLocationMapper(blh_line_map, compiler.line_mapper)


def expand_response_file(response_file: str) -> List[str]:
    """Expand @response_file to its contents"""
    try:
        filepath = response_file[1:]
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        args = []
        current = []
        in_quotes = False
        for char in content:
            if char == '"':
                in_quotes = not in_quotes
            elif char in ' \t\n\r' and not in_quotes:
                if current:
                    args.append(''.join(current))
                    current = []
            else:
                current.append(char)
        if current:
            args.append(''.join(current))
        return args
    except Exception:
        return [response_file]


def parse_gnu_args(args: List[str]) -> Tuple[List[str], Dict[str, str]]:
    """Parse GNU-style compiler arguments and identify source files."""
    source_files = {}
    expanded_args = []
    force_files = False
    
    i = 0
    while i < len(args):
        arg = args[i]
        
        if arg == '--':
            force_files = True
            expanded_args.append(arg)
            i += 1
            continue
        
        if force_files:
            if is_blcpp_file(arg):
                source_files[arg] = arg
            expanded_args.append(arg)
            i += 1
            continue
        
        if arg.startswith('@'):
            expanded = expand_response_file(arg)
            expanded_args.extend(expanded)
            _, nested_sources = parse_gnu_args(expanded)
            source_files.update(nested_sources)
            i += 1
            continue
        
        if arg == '-x' and i + 1 < len(args):
            expanded_args.append(arg)
            expanded_args.append(args[i + 1])
            i += 2
            continue
        
        if arg in ('-o', '-I', '-L', '-D', '-U', '-include', '-isystem', 
                   '-idirafter', '-iprefix', '-iwithprefix', '-MF', '-MT', '-MQ',
                   '-target', '--target', '-arch', '-framework', '-isysroot'):
            expanded_args.append(arg)
            if i + 1 < len(args):
                expanded_args.append(args[i + 1])
                i += 2
            else:
                i += 1
            continue
        
        if arg.startswith('-'):
            expanded_args.append(arg)
            i += 1
            continue
        
        if is_blcpp_file(arg):
            source_files[arg] = arg
        
        expanded_args.append(arg)
        i += 1
    
    return expanded_args, source_files


def parse_msvc_args(args: List[str]) -> Tuple[List[str], Dict[str, str]]:
    """Parse MSVC-style compiler arguments (cl.exe, clang-cl) and identify source files."""
    source_files = {}
    expanded_args = []
    
    i = 0
    while i < len(args):
        arg = args[i]
        
        if arg.startswith('@'):
            expanded = expand_response_file(arg)
            expanded_args.extend(expanded)
            _, nested_sources = parse_msvc_args(expanded)
            source_files.update(nested_sources)
            i += 1
            continue
        
        # Handle /Tp and /Tc (force treat file as C++ or C)
        if arg.upper().startswith('/TP') or arg.upper().startswith('/TC'):
            if len(arg) > 3:
                filepath = arg[3:]
                if is_blcpp_file(filepath):
                    source_files[filepath] = filepath
            elif i + 1 < len(args):
                filepath = args[i + 1]
                if is_blcpp_file(filepath):
                    source_files[filepath] = filepath
            expanded_args.append(arg)
            i += 1
            continue
        
        if arg.startswith('/') or arg.startswith('-'):
            expanded_args.append(arg)
            i += 1
            continue
        
        if is_blcpp_file(arg):
            source_files[arg] = arg
        
        expanded_args.append(arg)
        i += 1
    
    return expanded_args, source_files


def _normalize_path(path: str) -> str:
    """Normalize a path for comparison"""
    return os.path.normcase(os.path.normpath(path))


def _paths_match(path1: str, path2: str) -> bool:
    """Check if two paths refer to the same file"""
    if _normalize_path(path1) == _normalize_path(path2):
        return True
    return os.path.basename(path1).lower() == os.path.basename(path2).lower()


def _build_basename_map(file_mappings: Dict[str, SourceLocationMapper]) -> Dict[str, str]:
    """Build a map of basenames to temp paths"""
    basename_to_temp = {}
    for temp_path in file_mappings:
        basename = os.path.basename(temp_path).lower()
        if basename.endswith('.cpp'):
            basename_to_temp[basename] = temp_path
    return basename_to_temp


def patch_compiler_output(
    output: str,
    file_mappings: Dict[str, SourceLocationMapper],
    error_format: ErrorFormat
) -> str:
    """Patch compiler output to map line numbers back to original source files.
    
    This handles errors from transpiled .cpp files, mapping them back to the
    original .blcpp or .blh source files and line numbers.
    
    Args:
        output: Compiler stdout or stderr
        file_mappings: Maps temp_cpp_path -> SourceLocationMapper
        error_format: MSVC or GNU error message format
        
    Returns:
        Patched output with corrected file paths and line numbers
    """
    basename_to_temp = _build_basename_map(file_mappings)
    lines = output.split('\n')
    patched_lines = []
    
    pattern = MSVC_ERROR_PATTERN if error_format == ErrorFormat.MSVC else GNU_ERROR_PATTERN
    
    for line in lines:
        match = pattern.match(line)
        if match:
            filepath = match.group(1)
            line_num = int(match.group(2))
            
            matched_temp_path = None
            for temp_path in file_mappings:
                if _paths_match(filepath, temp_path):
                    matched_temp_path = temp_path
                    break
            
            if not matched_temp_path:
                basename = os.path.basename(filepath).lower()
                if basename in basename_to_temp:
                    matched_temp_path = basename_to_temp[basename]
            
            if matched_temp_path:
                mapper = file_mappings[matched_temp_path]
                # Get the original source file and line
                original_path, source_line = mapper.get_source_location(line_num)
                
                if error_format == ErrorFormat.MSVC:
                    column_part = match.group(3) or ''
                    old_loc = f'({line_num}{column_part})'
                    new_loc = f'({source_line}{column_part})'
                    line = line.replace(filepath, original_path, 1)
                    line = line.replace(old_loc, new_loc, 1)
                else:
                    col_part = match.group(3)
                    if col_part:
                        old_loc = f'{filepath}:{line_num}:{col_part}:'
                        new_loc = f'{original_path}:{source_line}:{col_part}:'
                    else:
                        old_loc = f'{filepath}:{line_num}:'
                        new_loc = f'{original_path}:{source_line}:'
                    line = line.replace(old_loc, new_loc, 1)
        
        patched_lines.append(line)
    
    return '\n'.join(patched_lines)


def run_compiler_wrapper(
    wrapper_name: str,
    compiler_exe: str,
    args: List[str],
    parse_args_func,
    error_format: ErrorFormat,
    verbose: bool = False,
    keep_temp: bool = False
) -> int:
    """Generic compiler wrapper runner."""
    all_args, source_files = parse_args_func(args)
    blcpp_files = {path: path for path in source_files if is_blcpp_file(path)}
    
    if not blcpp_files:
        if verbose:
            print(f"[{wrapper_name}] No .blcpp files found, passing through to: {compiler_exe}", file=sys.stderr)
        cmd = subprocess.list2cmdline([compiler_exe] + args)
        result = subprocess.run(cmd, capture_output=False, shell=True)
        return result.returncode
    
    temp_dir = tempfile.mkdtemp(prefix=f'{wrapper_name}_')
    
    if verbose:
        print(f"[{wrapper_name}] Temp directory: {temp_dir}", file=sys.stderr)
    
    # Extract include directories for .blh resolution
    include_dirs = extract_include_dirs(all_args)
    
    try:
        file_mappings = {}
        new_args = list(all_args)
        
        for original_path in blcpp_files:
            base_name = os.path.basename(original_path)
            temp_name = os.path.splitext(base_name)[0] + '.cpp'
            temp_path = os.path.join(temp_dir, temp_name)
            
            try:
                if verbose:
                    print(f"[{wrapper_name}] Transpiling: {original_path} -> {temp_path}", file=sys.stderr)
                mapper = transpile_file(original_path, temp_path, include_dirs)
                file_mappings[temp_path] = mapper
                
                for i, arg in enumerate(new_args):
                    if arg == original_path:
                        new_args[i] = temp_path
            except FileNotFoundError as e:
                print(f"{wrapper_name}: error: {e}", file=sys.stderr)
                return 1
            except Exception as e:
                print(f"{wrapper_name}: error transpiling {original_path}: {e}", file=sys.stderr)
                return 1
        
        if verbose:
            print(f"[{wrapper_name}] Running: {compiler_exe} {' '.join(new_args)}", file=sys.stderr)
        
        cmd = subprocess.list2cmdline([compiler_exe] + new_args)
        result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
        
        if result.stdout:
            patched = patch_compiler_output(result.stdout, file_mappings, error_format)
            print(patched, end='')
        
        if result.stderr:
            patched = patch_compiler_output(result.stderr, file_mappings, error_format)
            print(patched, end='', file=sys.stderr)
        
        return result.returncode
        
    finally:
        if not keep_temp:
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass
        elif verbose:
            print(f"[{wrapper_name}] Keeping temp directory: {temp_dir}", file=sys.stderr)


# Compiler configurations: (compiler_exe, error_format, parse_args_func)
COMPILERS = {
    'blcl':       ('cl.exe',    ErrorFormat.MSVC, parse_msvc_args),
    'blclang-cl': ('clang-cl',  ErrorFormat.MSVC, parse_msvc_args),
    'blgcc':      ('gcc',       ErrorFormat.GNU,  parse_gnu_args),
    'blg++':      ('g++',       ErrorFormat.GNU,  parse_gnu_args),
    'blclang':    ('clang',     ErrorFormat.GNU,  parse_gnu_args),
    'blclang++':  ('clang++',   ErrorFormat.GNU,  parse_gnu_args),
    'blemcc':     ('emcc',      ErrorFormat.GNU,  parse_gnu_args),
    'blem++':     ('em++',      ErrorFormat.GNU,  parse_gnu_args),
}


def wrapper_main(wrapper_name: str):
    """Main entry point for compiler wrappers."""
    if wrapper_name not in COMPILERS:
        print(f"Unknown wrapper: {wrapper_name}", file=sys.stderr)
        sys.exit(1)
    
    compiler_exe, error_format, parse_args_func = COMPILERS[wrapper_name]
    
    if len(sys.argv) < 2:
        print(f"{wrapper_name} - Braceless C++ wrapper for {compiler_exe}", file=sys.stderr)
        print(f"Usage: {wrapper_name} [{compiler_exe} options] <source files>", file=sys.stderr)
        print(f"       Accepts .blcpp files (braceless C++) in addition to regular C++ files", file=sys.stderr)
        print("", file=sys.stderr)
        print("Options:", file=sys.stderr)
        print("  --verbose    Show verbose output", file=sys.stderr)
        print("  --keep-temp  Don't delete temporary transpiled files", file=sys.stderr)
        sys.exit(1)
    
    args = sys.argv[1:]
    
    verbose = '--verbose' in args
    keep_temp = '--keep-temp' in args
    args = [arg for arg in args if arg not in ('--verbose', '--keep-temp')]
    
    exit_code = run_compiler_wrapper(
        wrapper_name=wrapper_name,
        compiler_exe=compiler_exe,
        args=args,
        parse_args_func=parse_args_func,
        error_format=error_format,
        verbose=verbose,
        keep_temp=keep_temp,
    )
    sys.exit(exit_code)


def main():
    # Check if invoked as a compiler wrapper
    if len(sys.argv) >= 3 and sys.argv[1] == '--wrapper':
        wrapper_name = sys.argv[2]
        sys.argv = [sys.argv[0]] + sys.argv[3:]  # Remove --wrapper and name from args
        wrapper_main(wrapper_name)
        return
    
    # Otherwise, run as transpiler
    if len(sys.argv) < 2:
        print("Usage: blcc <input.blcpp> [-I<include_dir>]...", file=sys.stderr)
        print("       blcc --wrapper <name> [compiler options] <source files>", file=sys.stderr)
        sys.exit(1)
    
    # Parse arguments
    filename = None
    include_dirs = []
    
    for arg in sys.argv[1:]:
        if arg.startswith('-I'):
            include_dirs.append(arg[2:])
        elif arg == '-I':
            continue  # Next arg will be the directory
        elif not filename:
            filename = arg
        elif sys.argv[sys.argv.index(arg) - 1] == '-I':
            include_dirs.append(arg)
    
    if not filename:
        print("Error: No input file specified", file=sys.stderr)
        sys.exit(1)
    
    try:
        # Expand .blh includes and transpile
        lines, _ = expand_blh_includes(filename, include_dirs)
        compiler = Compiler(lines)
        output = compiler.compile()
        print(output, end='')
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
