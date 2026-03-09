#!/usr/bin/env python3
"""
Installation Verification Script for Q2 Solution
================================================

Verifies all files exist and can be imported correctly.
"""

import sys
from pathlib import Path
import importlib

# Color codes for terminal output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
RESET = '\033[0m'
BOLD = '\033[1m'


def check_file_exists(filepath: str) -> bool:
    """Check if file exists."""
    return Path(filepath).exists()


def check_import(module_name: str) -> tuple:
    """Check if module can be imported."""
    try:
        importlib.import_module(module_name)
        return True, None
    except Exception as e:
        return False, str(e)


def main():
    """Run verification checks."""
    print(f"\n{BOLD}{'='*70}{RESET}")
    print(f"{BOLD}Q2 SOLUTION - INSTALLATION VERIFICATION{RESET}")
    print(f"{BOLD}{'='*70}{RESET}\n")

    # Required files
    required_files = {
        'Core Modules': [
            'signal_classifier.py',
            'disruption_scorer.py',
            'innovation_radar.py',
            'strategic_report_generator.py'
        ],
        'Enhanced Pipeline': [
            'models.py',
            'agents.py',
            'storage.py',
            'pipeline.py'
        ],
        'Original Pipeline': [
            'q2_pipeline.py'
        ],
        'Documentation': [
            'README.md',
            'EXECUTION_SUMMARY.md',
            'COMPARATIVE_ANALYSIS.md',
            'QUICK_START.md'
        ]
    }

    # Check files
    print(f"{BOLD}1. Checking Required Files{RESET}\n")
    all_files_exist = True

    for category, files in required_files.items():
        print(f"  {category}:")
        for filename in files:
            exists = check_file_exists(filename)
            status = f"{GREEN}✓{RESET}" if exists else f"{RED}✗{RESET}"
            print(f"    {status} {filename}")
            if not exists:
                all_files_exist = False
        print()

    # Check imports
    print(f"{BOLD}2. Checking Module Imports{RESET}\n")
    modules_to_test = [
        'models',
        'signal_classifier',
        'disruption_scorer',
        'innovation_radar',
        'strategic_report_generator',
        'agents',
        'storage',
        'pipeline',
        'q2_pipeline'
    ]

    all_imports_ok = True
    for module in modules_to_test:
        success, error = check_import(module)
        status = f"{GREEN}✓{RESET}" if success else f"{RED}✗{RESET}"
        print(f"  {status} {module:30s}", end='')
        if not success:
            print(f" {RED}ERROR: {error}{RESET}")
            all_imports_ok = False
        else:
            print(f" {GREEN}OK{RESET}")

    # Check dependencies
    print(f"\n{BOLD}3. Checking Python Dependencies{RESET}\n")
    dependencies = [
        'pydantic',
        'pandas',
        'numpy',
        'plotly',
        'matplotlib'
    ]

    all_deps_ok = True
    for dep in dependencies:
        success, error = check_import(dep)
        status = f"{GREEN}✓{RESET}" if success else f"{RED}✗{RESET}"
        print(f"  {status} {dep:30s}", end='')
        if not success:
            print(f" {YELLOW}NOT INSTALLED{RESET}")
            all_deps_ok = False
        else:
            print(f" {GREEN}OK{RESET}")

    # Check test files
    print(f"\n{BOLD}4. Checking Test Files{RESET}\n")
    test_dir = Path('../tests/q2')
    if test_dir.exists():
        test_files = [
            'test_signal_classifier.py',
            'test_disruption_scorer.py',
            'test_pipeline.py',
            'test_agents_pytest.py'
        ]
        for test_file in test_files:
            exists = (test_dir / test_file).exists()
            status = f"{GREEN}✓{RESET}" if exists else f"{RED}✗{RESET}"
            print(f"  {status} {test_file}")
    else:
        print(f"  {YELLOW}⚠{RESET} Test directory not found at {test_dir}")

    # Summary
    print(f"\n{BOLD}{'='*70}{RESET}")
    print(f"{BOLD}VERIFICATION SUMMARY{RESET}")
    print(f"{BOLD}{'='*70}{RESET}\n")

    if all_files_exist and all_imports_ok and all_deps_ok:
        print(f"{GREEN}{BOLD}✓ ALL CHECKS PASSED{RESET}")
        print(f"\n{GREEN}Your Q2 solution is correctly installed and ready to use!{RESET}")
        print(f"\n{BOLD}Next steps:{RESET}")
        print(f"  1. Run the enhanced pipeline: {YELLOW}python pipeline.py{RESET}")
        print(f"  2. Or run the original demo: {YELLOW}python q2_pipeline.py --demo{RESET}")
        print(f"  3. Run tests: {YELLOW}cd ../tests/q2 && pytest test_agents_pytest.py -v{RESET}")
        return 0
    else:
        print(f"{RED}{BOLD}✗ SOME CHECKS FAILED{RESET}\n")
        if not all_files_exist:
            print(f"{RED}• Some required files are missing{RESET}")
        if not all_imports_ok:
            print(f"{RED}• Some modules cannot be imported{RESET}")
        if not all_deps_ok:
            print(f"{YELLOW}• Some Python dependencies are missing{RESET}")
            print(f"\n{BOLD}Install missing dependencies:{RESET}")
            print(f"  {YELLOW}pip install pydantic pandas numpy plotly matplotlib{RESET}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
