## ADDED Requirements

### Requirement: Execute the monitor hourly
The system SHALL define a GitHub Actions schedule that runs once per hour at minute 17 using the `Europe/Bucharest` timezone.

#### Scenario: Hourly schedule is active
- **WHEN** the workflow exists on the repository's default branch and GitHub scheduling is available
- **THEN** GitHub requests one monitor run during each hourly schedule window

### Requirement: Support manual execution
The system SHALL expose a manual GitHub Actions trigger using the same monitoring logic as scheduled execution.

#### Scenario: Operator starts a diagnostic run
- **WHEN** an authorized repository user invokes the workflow manually
- **THEN** the system performs a complete monitoring run and publishes the normal run summary

### Requirement: Bound and serialize scheduled work
The workflow SHALL have a five-minute execution timeout and SHALL use a single concurrency group for monitor runs so concurrent runs do not mutate notification state simultaneously.

#### Scenario: A previous run is still active
- **WHEN** another scheduled or manual monitor run begins
- **THEN** the workflow concurrency policy prevents both runs from updating alert state concurrently

#### Scenario: A run becomes stuck
- **WHEN** a monitor run exceeds five minutes
- **THEN** GitHub terminates the run and marks it failed

### Requirement: Retry transient Entertix failures conservatively
The monitor SHALL perform sequential requests with explicit timeouts and bounded exponential backoff for transient network errors, rate limits, and server errors.

#### Scenario: A transient request succeeds on retry
- **WHEN** an eligible request initially fails and succeeds within the retry limit
- **THEN** the monitor continues without duplicating a performance result

#### Scenario: Retry budget is exhausted
- **WHEN** an eligible request continues failing after the configured retry limit
- **THEN** the affected result is unknown and the workflow fails

### Requirement: Publish observable run results
Every execution SHALL publish a human-readable GitHub Actions job summary listing each performance's date, status, selectable-seat count, and ticket link. A run containing any unknown result or notification failure SHALL finish with a non-zero status.

#### Scenario: All results are known
- **WHEN** every discovered performance is successfully classified and all required alert transitions succeed
- **THEN** the workflow summary contains all performances and the workflow succeeds

#### Scenario: At least one result is unknown
- **WHEN** any performance cannot be classified safely
- **THEN** the workflow summary identifies the error and the workflow fails

### Requirement: Limit workflow permissions
The scheduled job SHALL request only `contents: read` and `issues: write` permissions from the GitHub workflow token.

#### Scenario: Workflow permissions are evaluated
- **WHEN** the monitor job starts
- **THEN** all unspecified GitHub token permissions are unavailable to the job

