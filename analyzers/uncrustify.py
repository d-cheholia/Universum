#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import argparse
import difflib
import sys
import os

import re
import sh

from . import utils

# The maximum number of lines to write separate comments for
# If exceeded, summarized comment will be provided instead
MAX_LINES = 11


def replace_invisible_symbols(line):
    for old_str, new_str in zip([u" ", u"\t", u"\n"],
                                [u"\u00b7", u"\u2192\u2192\u2192\u2192", u"\u2193\u000a"]):
        return line.replace(old_str, new_str)


def add_files_recursively(item_path):
    files = []
    item_path = os.path.join(os.getcwd(), item_path)
    if os.path.isfile(item_path):
        files.append(item_path)
    elif os.path.isdir(item_path):
        for root_dir, _, file_names in os.walk(item_path):
            for file_name in file_names:
                files.append(os.path.join(root_dir, file_name))
    else:
        sys.stderr.write(item_path + " doesn't exist.")
        return 2

    return files


def get_issue_json_format(src_file, diff):
    issue = dict()
    issue["symbol"] = "Uncrustify Code Style issue"
    # Check block size
    diff_size = len(diff["before"].splitlines())
    if diff_size > MAX_LINES:
        issue["message"] = "\nLarge block of code (" + str(diff_size) + \
                           " lines) has issues\n"
    else:
        # Message with before&after
        issue["message"] = "\nOriginal code:\n```diff\n" + diff["before"] + "```\n" + \
                           "Uncrustify generated code:\n```diff\n" + diff['after'] + "```\n"

    issue["path"] = os.path.relpath(src_file, os.getcwd())
    issue["line"] = diff["line"]
    return issue


def get_text_for_block(start, end, lines):
    return replace_invisible_symbols(''.join(lines[start: end]))


def get_mismatching_block(first_match, second_match, src_lines, fixed_lines):
    block = dict()
    first_match_end = first_match.a + first_match.size
    second_match_start = second_match.a
    if first_match_end != second_match_start:
        block['line'] = second_match_start
        block["before"] = get_text_for_block(first_match_end - 1, second_match_start, src_lines)
        block['after'] = get_text_for_block(first_match_end - 1, second_match_start, fixed_lines)
    return block


class UncrustifyAnalyzer(object):
    """
    Uncrustify runner.
    Specify parameters such as file list, config file for code report tool.
    For example: universum_uncrustify --files *.py tests/
    Output: json of the found issues in the code.
    """
    @staticmethod
    def define_arguments():
        parser = argparse.ArgumentParser(description="Uncrustify analyzer")
        parser.add_argument("--files", "-f", dest="file_names", nargs="*", default=[],
                            help="File or directory to check; accepts multiple values; "
                                 "all files specified by both '--files' and '--file-list' "
                                 "are gathered into one combined list of files")
        parser.add_argument("--file-list", "-fl", dest="file_lists", nargs="*", default=[],
                            help="Text file with list of files or directories to check; "
                                 "can be used with '--files'; accepts multiple values; "
                                 "all files specified by both '--files' and '--file-list' "
                                 "are gathered into one combined list of files")
        parser.add_argument("--cfg-file", "-cf", dest="cfg_file",
                            help="Name of the configuration file of Uncrustify; "
                                 "can also be set via 'UNCRUSTIFY_CONFIG' env. variable")
        parser.add_argument("--filter-regex", "-r", dest="pattern_form", nargs="*", default=[],
                            help="(optional) Regular expression filter to apply to "
                                 "combined list of files to check")

        utils.add_common_arguments(parser)
        return parser

    def __init__(self, settings):
        self.settings = settings
        self.uncrustify_folder = os.path.join(os.getcwd(), "uncrustify")

    def parse_files(self):
        files = []
        file_lines = []
        for file_name in self.settings.file_names:
            files.extend(add_files_recursively(file_name))
        for file_list in self.settings.file_lists:
            with open(file_list) as f:
                for file_name in f.readlines():
                    file_lines.append(file_name.strip())
        for file_name in file_lines:
            files.extend(add_files_recursively(file_name))
        for pattern in self.settings.pattern_form:
            regexp = re.compile(pattern)
            files = [file_name for file_name in files if regexp.match(file_name)]
        if not files:
            sys.stderr.write("Please provide at least one file for analysis")
            return 2

        return files

    def get_file_issues(self, src_file):
        # Uncrustify copies absolute path in its target folder, that's why we use '+'
        uncrustify_file = self.uncrustify_folder + src_file

        with open(src_file) as src:
            src_lines = src.readlines()
        with open(uncrustify_file) as fixed:
            fixed_lines = fixed.readlines()

        file_issues = []
        matching_blocks = difflib.SequenceMatcher(a=src_lines, b=fixed_lines).get_matching_blocks()
        previous_match = matching_blocks[0]
        for match in matching_blocks[1:]:
            block = get_mismatching_block(previous_match, match, src_lines, fixed_lines)
            previous_match = match
            if block:
                file_issues.append(get_issue_json_format(src_file, block))

        # Generate html diff
        if file_issues:
            differ = difflib.HtmlDiff(tabsize=8, wrapcolumn=82)
            with open(uncrustify_file + '.html', 'w') as outfile:
                outfile.write(differ.make_file(src_lines, fixed_lines, context=False))

        return file_issues

    def execute(self):
        if not self.settings.cfg_file and ('UNCRUSTIFY_CONFIG' not in os.environ):
            sys.stderr.write("Please specify the '--cfg_file' parameter "
                             "or set an env. variable 'UNCRUSTIFY_CONFIG'")
            return 2

        files = self.parse_files()
        try:
            cmd = sh.Command("uncrustify")
            cmd("-c", self.settings.cfg_file, "--prefix", self.uncrustify_folder, files)
        except sh.ErrorReturnCode as e:
            sys.stderr.write(str(e)+"\n")

        issues_loads = []
        for file_name in files:
            issues_loads.extend(self.get_file_issues(file_name))
        if issues_loads:
            utils.analyzers_output(self.settings.result_file, issues_loads)
            return 1

        return 0


def form_arguments_for_documentation():
    return UncrustifyAnalyzer.define_arguments()


def main():
    analyzer_namespace = UncrustifyAnalyzer.define_arguments().parse_args()
    analyze = UncrustifyAnalyzer(analyzer_namespace)
    return analyze.execute()


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
