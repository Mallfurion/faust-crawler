## Context

The repository is newly initialized and has no application code or established runtime conventions. Entertix renders the relevant search and event links in server-generated HTML. Its ticket page then loads the venue map by posting `do=getmapdata` to the ticket-page URL. The JSON response represents sold-out seats with the base `seatingseat` class and selectable seats with the additional `seatingseatactive` class.

The monitor is a read-only personal automation. It must discover future dates rather than rely on a fixed event list, run unattended on GitHub-hosted infrastructure, avoid false sold-out results when Entertix changes or fails, and deliver an alert without requiring a separate hosted database.

## Goals / Non-Goals

**Goals:**

- Discover current and newly listed *Faust* performances at Fabrica de Cultura in Sibiu.
- Determine availability from Entertix's structured seat-map response.
- Run hourly in GitHub Actions and support manual diagnostic runs.
- Deliver durable, deduplicated alerts with direct purchase links.
- Remain low-cost, low-rate, dependency-light, and safe when upstream behavior changes.
- Make parsing and state transitions testable without live network access.

**Non-Goals:**

- Selecting, holding, reserving, or purchasing tickets.
- Bypassing authentication, CAPTCHAs, rate limits, or access controls.
- Monitoring non-*Faust* events or other ticket vendors.
- Guaranteeing exact-to-the-minute execution or detecting availability windows shorter than the hourly interval.
- Building a web UI or long-running hosted service.

## Decisions

### Use a small Python standard-library application

Use Python 3.12 with `urllib`, `html.parser`, `json`, and `unittest`. Separate Entertix access, domain models, notification state, and the CLI into small modules under `src/faust_monitor/`.

This avoids browser automation and third-party dependency installation on every hourly run while retaining a real HTML parser. A single shell script was rejected because nested page discovery, JSON validation, retries, and tests would become fragile. Playwright was rejected because the authoritative availability data is available before rendering and does not require JavaScript execution.

### Discover events on every run

Fetch the Entertix search URL, collect event-detail links, and verify each candidate against the event title, venue, and city. Extract the numeric event ID as the stable identity, deduplicate candidates by that ID, then follow each verified event page to its published ticket-selection link.

Hard-coding the eight currently known event IDs was rejected because later performances would not be monitored. Deriving ticket URLs by replacing `/evenimente/` with `/bilete/` was rejected because following the published link is more resilient to routing changes.

### Classify availability from seat-map JSON

For every ticket URL, send a form-encoded POST with `do=getmapdata`. Validate the response shape, flatten seats from all sectors, and treat a seat as selectable only when `seatingseatactive` is a complete class token. Report the total and selectable counts.

An event is sold out only when a valid map contains at least one seat and the selectable count is zero. Missing sectors, zero parsed seats, invalid JSON, unexpected HTML, or exhausted network retries produce `unknown` and a failing run. The legend text is retained for diagnostics but is not the primary signal because class tokens directly match the site's click behavior.

### Keep the crawler read-only and courteous

The application sends only GET requests needed for discovery and the same read-only map-data POST used by the public page. It does not invoke seat-selection or cart operations. Requests are sequential, identify the monitor with a descriptive user agent, use a timeout, and retry only transient failures with bounded exponential backoff.

At the current eight performances, a successful run requires approximately seventeen small requests per hour. Parallel fetching was rejected because the latency savings are immaterial for an hourly task and sequential access reduces upstream load.

### Use GitHub Issues as both alert channel and durable state

Maintain one issue per Entertix event ID, identified by a label and a machine-readable marker in the issue body. When selectable seats first appear, create an issue assigned to the configured GitHub username. Include the performance date, count, direct ticket URL, and event ID. If the matching issue is already open, update its factual content without posting another alert comment.

When a known event returns to a valid sold-out state, close its open issue. If availability later returns, reopen the issue and add a new alert comment. Never close or reopen issues based on an `unknown` result. Notification API failures fail the workflow.

This provides durable transition state without commits, caches, artifacts, or a database. Sending every hour was rejected as too noisy. GitHub Actions caches were rejected because they are best-effort and immutable. Committing a state file was rejected because it creates repository churn and may conflict with branch protection. Telegram or email can be added later as secondary channels without changing the monitoring contract.

### Run off the top of the hour

Define both `schedule` and `workflow_dispatch` triggers. The schedule runs at minute 17 of every hour in `Europe/Bucharest`, reducing the chance of GitHub's top-of-hour queue congestion. Set a five-minute timeout and a repository-wide concurrency group so a stale run cannot overlap a newer run.

The workflow checks out the repository, sets up Python, runs tests when code changes through a separate CI trigger, runs the monitor, and writes a Markdown status table to the job summary. The scheduled job receives only `contents: read` and `issues: write` permissions.

## Risks / Trade-offs

- **Entertix changes HTML paths or seat-map JSON** → Validate all required structures, retain fixture-based parser tests, fail as `unknown`, and include actionable diagnostics in the job summary.
- **GitHub delays or drops a scheduled run** → Run at minute 17, retain manual dispatch, and document that GitHub scheduling is not a real-time SLA.
- **A ticket appears and disappears between hourly runs** → Accept this limitation for the requested polling rate; keep the interval configurable for a future policy change.
- **GitHub does not notify the intended person** → Assign alert issues to an explicit `ALERT_ASSIGNEE` repository variable, default it to the repository owner for personal repositories, and document enabling GitHub email or mobile notifications.
- **A public repository disables an inactive scheduled workflow** → Recommend a private personal repository for unattended use and document GitHub's public-repository inactivity behavior.
- **The issue API is unavailable after availability is detected** → Fail the run visibly and retry the complete monitor on the next schedule; never mark the event as alerted locally unless the issue transition succeeds.
- **A performance disappears from search results** → Do not infer sold-out status from absence. Expired events can be closed only after their recorded date passes; unexplained future-event disappearance is reported for review.

## Migration Plan

1. Add the Python package, CLI, tests, workflow, and documentation without enabling external side effects in tests.
2. Run fixture tests and a manual live dry run that prints availability without writing issues.
3. Configure `ALERT_ASSIGNEE` if the repository owner is not the desired recipient.
4. Merge the workflow onto the default branch and manually dispatch it once with issue writes enabled.
5. Confirm the job summary and issue permissions, then rely on the hourly schedule.

Rollback consists of disabling or removing the workflow. Existing alert issues remain ordinary GitHub issues and can be closed manually; no Entertix-side state exists to clean up.

## Open Questions

- Whether a secondary push channel such as Telegram should be added after the GitHub Issue flow is proven. This is not required for the initial implementation.

