#!/usr/bin/env python
"""Quick test of extension uninstall functions"""
import sys
sys.path.insert(0, '/Users/axgd/Documents/dev/init_mac-main/ui')

from app import uninstall_extension, scan_chrome_family_extensions, scan_firefox_extensions

print("Testing extension uninstall functions...")
print()

# Test scanning
print("=== Scanning for extensions ===")
try:
    chromes = scan_chrome_family_extensions()
    print(f"✓ Chrome family: {len(chromes)} extensions found")
    if chromes:
        for e in chromes[:3]:
            print(f"  - {e['browser']}: {e['name']} ({e['id']})")
except Exception as e:
    print(f"✗ Chrome scan failed: {e}")

print()

try:
    firefoxes = scan_firefox_extensions()
    print(f"✓ Firefox: {len(firefoxes)} extensions found")
    if firefoxes:
        for e in firefoxes[:3]:
            print(f"  - {e['name']} ({e['id']})")
except Exception as e:
    print(f"✗ Firefox scan failed: {e}")

print()
print("=== Uninstall function available ===")
print(f"✓ uninstall_extension function: {callable(uninstall_extension)}")
print()
print("Testing uninstall with fake ID (should fail gracefully):")
result = uninstall_extension('chrome', 'nonexistent-extension-id')
print(f"  Result: {result}")
