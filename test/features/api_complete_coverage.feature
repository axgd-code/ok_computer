Feature: API Complete Coverage Matrix
  As a maintainer
  I want feature-level API tests for all major endpoint groups
  So that behavior is documented and verified consistently

  Background:
    Given an isolated API test client

  Scenario: Logging and environment endpoints
    When I call POST "/api/log" with json payload
    Then the API response status code should be 200
    When I call GET "/api/env"
    Then the API response status code should be 200
    And the API response should be json
    When I call POST "/api/env/init"
    Then the API response status code should be 200
    When I call GET "/api/env/exists"
    Then the API response status code should be 200
    When I call GET "/api/env/location"
    Then the API response status code should be 200

  Scenario: Package and discovery endpoints
    When I call GET "/api/packages"
    Then the API response status code should be 200
    When I call GET "/api/check?app=git"
    Then the API response status code should be 200
    When I call GET "/api/icon?name=git"
    Then the API response status code should be 200
    When I call GET "/api/search?q=git"
    Then the API response status code should be 200

  Scenario: Extensions and system settings endpoints
    When I call GET "/api/extensions"
    Then the API response status code should be 200
    And configured extensions should include metadata links or icons
    When I call GET "/api/extensions/scan"
    Then the API response status code should be 200
    And scanned extensions should include metadata links or icons
    When I call POST "/api/extensions/update" with lines payload
    Then the API response status code should be 200
    When I call GET "/api/system-settings"
    Then the API response status code should be 200
    When I call POST "/api/system-settings/update" with lines payload
    Then the API response status code should be 200

  Scenario: Dashboard action endpoints
    When I call POST "/api/action/update"
    Then the API response status code should be 200
    When I call POST "/api/action/install" with install payload
    Then the API response status code should be 200
    When I call POST "/api/action/import-installed"
    Then the API response status code should be 200

  Scenario: Export and automation endpoints
    When I call GET "/api/export/default-path"
    Then the API response status code should be 200
    When I call POST "/api/action/export-config" with export payload
    Then the API response status code should be 200
    When I call GET "/api/automation/status"
    Then the API response status code should be 200
    When I call GET "/api/auto-update/status"
    Then the API response status code should be 200
    When I call POST "/api/auto-update/toggle" with enable payload
    Then the API response status code should be 200
    When I call POST "/api/auto-update/cron-install"
    Then the API response status code should be 200
    When I call POST "/api/auto-update/cron-remove"
    Then the API response status code should be 200

  Scenario: Zip init and wifi validation endpoints
    When I call GET "/api/action/init-status/unknown-job"
    Then the API response status code should be 404
    When I call POST "/api/action/wifi-export" with missing db payload
    Then the API response status code should be 400
    When I call POST "/api/action/wifi-export" with missing password payload
    Then the API response status code should be 400
