## 1. Project Setup

- [x] 1.1 Create the Python 3.12 package structure under `src/faust_monitor/`, a module entry point, and project metadata with no runtime dependencies.
- [x] 1.2 Define typed performance, availability-result, status, and diagnostic models shared by crawling, reporting, and notification code.
- [x] 1.3 Add configuration for the Entertix search URL, request timeout, retry limit, user agent, and GitHub repository.

## 2. Entertix Monitoring

- [x] 2.1 Implement a sequential HTTP transport with form-encoded POST support, explicit timeouts, a descriptive user agent, and bounded retry/backoff for transient failures.
- [x] 2.2 Implement search-page parsing, strict title/venue/city filtering, numeric event-ID extraction, and event-ID deduplication.
- [x] 2.3 Implement event-detail verification and extraction of the published `/bilete/` ticket-selection URL without deriving the route.
- [x] 2.4 Implement `do=getmapdata` requests, seat-map schema validation, exact class-token matching, total/selectable seat counting, and safe unknown results.
- [x] 2.5 Implement the CLI orchestration that discovers all events, checks them sequentially, emits structured JSON, renders a Markdown summary, supports dry-run mode, and returns failure for unknown results.

## 3. GitHub Issue Notifications

- [x] 3.1 Implement the GitHub Issues client for ensuring the monitor label, listing open and closed monitor issues, and identifying issues by their machine-readable event-ID marker.
- [x] 3.2 Implement creation and assignment of actionable issues for newly available events, including date, count, event ID, and direct ticket URL.
- [x] 3.3 Implement idempotent updates for persistent availability, closure after confirmed sell-out, and reopening plus a new alert comment when availability returns.
- [x] 3.4 Ensure unknown monitoring results never mutate issue state and ensure every required GitHub API mutation failure causes a failing process status.
- [x] 3.5 Discover all GitHub-assignable repository users at run time, enforce GitHub's ten-assignee limit, and synchronize open availability issues when that list changes.

## 4. Automation and Documentation

- [x] 4.1 Add the hourly GitHub Actions monitor workflow with minute-17 `Europe/Bucharest` scheduling, manual dispatch, five-minute timeout, serialized concurrency, and only `contents: read` plus `issues: write` permissions.
- [x] 4.2 Add a separate pull-request and push CI workflow that runs the offline test suite without Entertix or GitHub write access.
- [x] 4.3 Write the repository README covering local dry runs, notification configuration, manual workflow execution, GitHub notification settings, rate and safety behavior, known scheduler limitations, and rollback.

## 5. Tests and Verification

- [x] 5.1 Add synthetic search, event-detail, sold-out map, available map, and malformed map fixtures without storing full production venue data.
- [x] 5.2 Add unit tests for strict event filtering, new-event discovery, deduplication, ticket-link resolution, exact active-class matching, sold-out classification, and structured output.
- [x] 5.3 Add transport tests for retry eligibility, backoff limits, timeouts, permanent failures, and exhausted-retry unknown results.
- [x] 5.4 Add mocked GitHub API tests covering first alert, multiple events, persistent availability deduplication, sell-out closure, reappearance reopening, unknown-state preservation, and mutation failures.
- [x] 5.5 Run the complete offline suite and a manual live dry run, verify all eight current Faust performances are discovered without issue mutations, and inspect the generated Markdown summary.
- [x] 5.6 Validate the OpenSpec change, inspect the final workflow permissions and schedule, and document any live-site deviations discovered during verification.
