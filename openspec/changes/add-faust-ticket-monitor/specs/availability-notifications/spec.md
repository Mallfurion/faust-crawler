## ADDED Requirements

### Requirement: Create an actionable availability alert
The system SHALL create one GitHub Issue for a performance when it first changes from a known non-available state to a state with one or more selectable seats. The issue SHALL be assigned to every user GitHub reports as assignable in the repository and SHALL include the performance date, selectable-seat count, direct ticket URL, and Entertix event ID.

#### Scenario: Tickets become available for the first time
- **WHEN** a performance has selectable seats and has no existing monitor issue
- **THEN** the system creates and assigns an open availability issue containing the purchase information

#### Scenario: Several performances become available
- **WHEN** selectable seats appear for multiple event IDs in the same run
- **THEN** the system creates an independently actionable issue for each event ID

### Requirement: Persist alert identity by event ID
The system SHALL identify monitor issues using both a dedicated label and a machine-readable event-ID marker in the issue body. Issue-title text alone MUST NOT determine identity.

#### Scenario: Performance title or date formatting changes
- **WHEN** an existing event's human-readable metadata changes but its Entertix event ID remains the same
- **THEN** the system associates the result with the existing monitor issue

### Requirement: Suppress duplicate persistent-availability alerts
The system SHALL NOT create a new issue or post a new alert comment while a matching availability issue remains open. It MAY update factual counts or links in the existing issue body without creating a new alert notification.

#### Scenario: Tickets remain available at the next hourly run
- **WHEN** a matching monitor issue is already open and the performance still has selectable seats
- **THEN** the system reuses the issue without generating another availability alert

### Requirement: Close alerts after confirmed sell-out
The system SHALL close an open monitor issue when a valid later seat map confirms that the performance has zero selectable seats.

#### Scenario: Available performance becomes sold out
- **WHEN** a valid seat map contains seats but none is selectable and the matching issue is open
- **THEN** the system closes the issue

### Requirement: Re-alert when availability returns
The system SHALL reopen the existing issue and add a new alert comment when selectable seats reappear after the corresponding issue was closed.

#### Scenario: Tickets reappear after sell-out
- **WHEN** a matching monitor issue is closed and a valid seat map again contains selectable seats
- **THEN** the system reopens the issue and posts a new comment with the current count and ticket link

### Requirement: Preserve notification state during uncertainty
The system MUST NOT create, close, or reopen an availability issue for an event whose current monitoring result is unknown.

#### Scenario: Entertix fails while an alert is open
- **WHEN** the event's current result is unknown and its monitor issue is open
- **THEN** the issue remains open and the workflow reports a failure

#### Scenario: Entertix fails while an alert is closed
- **WHEN** the event's current result is unknown and its monitor issue is closed
- **THEN** the issue remains closed and the workflow reports a failure

### Requirement: Surface notification failures
The system SHALL treat failure to complete a required issue creation, assignment, closure, reopening, or alert comment as a failed workflow run.

#### Scenario: GitHub issue mutation fails
- **WHEN** an availability transition requires an issue mutation and the GitHub API rejects or fails the operation
- **THEN** the workflow reports the notification error and finishes with a non-zero status
