Feature: Dashboard Quick Actions
  As a user of ok_computer
  I want the dashboard quick actions to work correctly
  So that I can manage my Mac configuration efficiently

  Background:
    Given the application is running
    And a valid ".env.example" file exists
    And a valid "packages.conf" file exists

  # ---------------------------------------------------------------------------
  # Run Update
  # ---------------------------------------------------------------------------

  Scenario: Run Update executes the update script
    When I trigger "Run Update"
    Then the response contains an exit code
    And no backend error is returned

  Scenario: Run Update reports an error when update.sh is missing
    Given the script "update.sh" does not exist
    When I trigger "Run Update"
    Then the response contains an error message
    And the error message mentions the missing script

  # ---------------------------------------------------------------------------
  # Import Installed Packages
  # ---------------------------------------------------------------------------

  Scenario: Import Installed runs the import script with skip-cross-check flag
    When I trigger "Import Installed"
    Then the backend invokes "import_installed.sh" with "--skip-cross-check"
    And the response contains an exit code
    And no backend error is returned

  Scenario: Import Installed reports an error when script is missing
    Given the script "import_installed.sh" does not exist
    When I trigger "Import Installed"
    Then the response contains an error message

  # ---------------------------------------------------------------------------
  # Export Configuration
  # ---------------------------------------------------------------------------

  Scenario: Export Configuration creates a zip file with config files
    Given ".env.local" exists with some settings
    When I trigger "Export Configuration" to a temp path
    Then a zip file is created at that path
    And the zip contains ".env.local"
    And the zip contains "packages.conf"
    And the zip contains "extensions.conf"
    And the response status is "ok"

  Scenario: Export Configuration uses the default path when no output path is given
    Given ".env.local" exists with some settings
    When I trigger "Export Configuration" without specifying a path
    Then a zip file is created at the default location
    And the response status is "ok"

  Scenario: Export Configuration returns a default path suggestion
    When I request the default export path
    Then the response contains a "default_path" field ending with ".zip"
    And the response contains a "default_dir" field

  Scenario: Export Configuration fails gracefully when no config files exist
    Given ".env.local" does not exist
    And "packages.conf" does not exist
    And "extensions.conf" does not exist
    When I trigger "Export Configuration" to a temp path
    Then the response contains an error message

  # ---------------------------------------------------------------------------
  # Wi-Fi Export
  # ---------------------------------------------------------------------------

  Scenario: Wi-Fi Export requires a DB path
    When I trigger "Wi-Fi Export" without a DB path
    Then the response contains an error message about the missing DB path

  Scenario: Wi-Fi Export requires a password
    When I trigger "Wi-Fi Export" with a DB path but no password
    Then the response contains an error message about the missing password

  Scenario: Wi-Fi Export falls back to WIFI_KDBX_DB from env when no DB path sent
    Given ".env.local" has "WIFI_KDBX_DB" set to "/fake/vault.kdbx"
    And the script "wifi_from_keychain.sh" is mocked to succeed
    When I trigger "Wi-Fi Export" without a DB path but with a password
    Then the backend uses "/fake/vault.kdbx" as the DB path
    And the response contains an exit code

  Scenario: Wi-Fi Export reports an error when the script is missing
    Given the script "wifi_from_keychain.sh" does not exist
    When I trigger "Wi-Fi Export" with valid DB path and password
    Then the response contains an error about the missing script

  # ---------------------------------------------------------------------------
  # Initialize from Zip
  # ---------------------------------------------------------------------------

  Scenario: Init from Zip requires a zip path
    When I trigger "Init from Zip" without a zip path
    Then the response status is 400
    And the response contains an error message

  Scenario: Init from Zip requires the zip file to exist
    When I trigger "Init from Zip" with a non-existent zip path
    Then the response status is 404
    And the response contains an error message

  Scenario: Init from Zip starts a background job and returns a jobId
    Given a valid configuration zip file exists at a temp path
    When I trigger "Init from Zip" with that zip path
    Then the response contains a "jobId"
    And the response status field is "started"

  Scenario: Init from Zip job status can be polled
    Given a background init job has been started
    When I poll the job status
    Then the status contains a "progress" field
    And the status contains a "done" field

  # ---------------------------------------------------------------------------
  # Auto Update Toggle
  # ---------------------------------------------------------------------------

  Scenario: Auto update status is readable
    When I request the auto-update status
    Then the response contains an "enabled" field
    And the response contains a "mode" field

  Scenario: Enabling auto-update calls the setup script
    Given the script "setup_auto_update.sh" is mocked to succeed
    When I toggle auto-update to enabled
    Then the setup script is invoked
    And the response status is "ok"
    And the response "enabled" field is true

  Scenario: Disabling auto-update on macOS unloads the LaunchAgent
    Given auto-update is currently enabled
    When I toggle auto-update to disabled
    Then the response status is "ok"
    And the response "enabled" field is false
