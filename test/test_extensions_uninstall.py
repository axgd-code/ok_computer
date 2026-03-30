"""Test extension uninstall functionality"""
import json
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock
import sys
import os

# Add ui directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'ui'))
os.chdir(Path(__file__).parent.parent)

from app import app, uninstall_extension, uninstall_chrome_extension, uninstall_firefox_extension


def test_uninstall_extension_mock_chrome():
    """Test uninstall_extension routes to chrome handler"""
    result = uninstall_extension('chrome', 'test-id')
    assert result['status'] == 'error'  # Expected: not found
    assert 'not found' in result['message'].lower()


def test_uninstall_extension_mock_firefox():
    """Test uninstall_extension routes to firefox handler"""
    result = uninstall_extension('firefox', 'test-addon-id')
    assert result['status'] == 'error'  # Expected: not found
    assert 'not found' in result['message'].lower()


def test_uninstall_extension_unknown_browser():
    """Test uninstall_extension with unknown browser"""
    result = uninstall_extension('safari', 'test-id')
    assert result['status'] == 'error'
    assert 'unknown' in result['message'].lower()


def test_api_extensions_uninstall():
    """Test API endpoint for uninstalling extensions"""
    with app.test_client() as client:
        # Test missing browser
        response = client.post('/api/extensions/uninstall',
                              json={'id': 'test-id'})
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
        
        # Test missing id
        response = client.post('/api/extensions/uninstall',
                              json={'browser': 'chrome'})
        assert response.status_code == 400
        
        # Test uninstall non-existent extension (should still work but fail)
        response = client.post('/api/extensions/uninstall',
                              json={'browser': 'chrome', 'id': 'nonexistent'})
        assert response.status_code == 400  # Will return error but 400 is appropriate
        data = json.loads(response.data)
        assert 'status' in data
        assert data['status'] == 'error'


def test_api_extensions_scan():
    """Test API endpoint for scanning extensions"""
    with app.test_client() as client:
        response = client.get('/api/extensions/scan')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert isinstance(data, list)
        
        # Each item should have these fields
        for item in data[:1]:  # Check at least first item
            assert 'browser' in item
            assert 'id' in item
            assert 'name' in item


if __name__ == '__main__':
    print("Running extension uninstall tests...")
    print()
    
    tests = [
        test_uninstall_extension_mock_chrome,
        test_uninstall_extension_mock_firefox,
        test_uninstall_extension_unknown_browser,
        test_api_extensions_uninstall,
        test_api_extensions_scan,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            print(f"Running {test.__name__}...", end=' ')
            test()
            print("✓ PASS")
            passed += 1
        except AssertionError as e:
            print(f"✗ FAIL: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ ERROR: {e}")
            failed += 1
    
    print()
    print(f"Results: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("✓ All tests passed!")
