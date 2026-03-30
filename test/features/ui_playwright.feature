Feature: UI End-to-End With Playwright
  As a user
  I want to use the workflow-oriented UI across the 3 main stages
  So that core setup actions are validated end-to-end in a browser

  Background:
    Given the test web server is running
    And a browser page is open on the application

  Scenario: Main workflow tabs are visible
    Then I should see the main navigation tabs

  Scenario: I can navigate across the 3 workflow stages
    When I open the "initialization" tab
    Then the tab content "initialization" is visible
    When I open the "customization" tab
    Then the tab content "customization" is visible
    When I open the "export" tab
    Then the tab content "export" is visible

  Scenario: Settings save flow persists values
    When I open the "customization" tab
    And I set environment key "SYNC_DIR" to "/tmp/e2e-sync"
    And I save environment settings
    Then environment key "SYNC_DIR" should equal "/tmp/e2e-sync"

  Scenario: System settings are booleans as checkboxes and can be saved/applied
    When I open the "customization" tab
    Then the first boolean system setting row contains a shared checkbox
    When I check the first boolean system setting's shared checkbox
    And I save system settings
    And I apply system settings
    Then system settings output should contain "code"

  Scenario: Search package mode returns visible results area
    When I open the "customization" tab
    And I search for "git" in mode "package"
    Then the search results area is visible

  Scenario: Extensions tab refresh and save works
    When I open the "customization" tab
    And I refresh extensions list
    And I save extensions list
    Then extensions output should be available or list remains visible

  Scenario: Extensions list displays icons and official links
    When I open the "customization" tab
    And I refresh extensions list
    Then extension rows should expose at least one icon
    And extension rows should expose official extension links
