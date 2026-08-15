# Faust ticket monitor

A read-only hourly monitor for tickets to *Faust* performances at Fabrica de Cultura (Sala Faust) in Sibiu.

The monitor discovers current and newly announced performances from [Entertix's Faust search](https://www.entertix.ro/evenimente?s=faust), follows each event's published ticket-selection link, and requests the same structured seat-map data used by the public page. A seat is reported as selectable only when its class-token list contains `seatingseatactive`.

The monitor never selects seats, writes to a cart, reserves inventory, authenticates to Entertix, or attempts a purchase.

## How alerts work

GitHub Issues provide both the notification channel and durable transition state:

- The first selectable seat for an event creates an issue labeled `faust-ticket-monitor` and assigns it to every user GitHub reports as assignable in the repository.
- The issue contains the performance date, current selectable-seat count, event ID, and direct ticket-selection link.
- Repeated hourly checks do not post another alert while that issue remains open.
- A confirmed return to zero selectable seats closes the issue.
- Later availability comments on and reopens the same issue, generating a new alert.
- A network or parsing error is `unknown`; it fails the workflow and never closes or reopens the event's issue.

Assignment is important because it triggers GitHub's email or mobile notification for each recipient. Confirm that GitHub notifications are enabled for assigned issues in each account's settings.

### Managing alert recipients

Recipients are discovered at run time through GitHub's repository assignees API. For this personal repository, manage the list under **Settings → Collaborators**: invite someone and have them accept to make them eligible, or remove their repository access to remove them from future alert assignments.

The monitor deliberately does not use the repository's commit-contributors list. Contributors are derived from permanent commit history, can be cached for several hours, and are not necessarily eligible issue assignees. GitHub issues support at most ten assignees, so the workflow fails clearly instead of creating a partially assigned alert if the eligible list grows beyond ten.

When tickets remain available, each hourly run also synchronizes the open alert issue with the current assignable-user list. Both the real monitor and the test-notification workflow use the same recipient source.

## Local use

Python 3.12 or newer is required. There are no runtime dependencies.

Run a read-only check without changing GitHub Issues:

```bash
PYTHONPATH=src python3.12 -m faust_monitor --dry-run
```

The command prints a Markdown table and writes the full structured result to `monitor-report.json`. Use another path or print JSON to standard output with:

```bash
PYTHONPATH=src python3.12 -m faust_monitor --dry-run --json-output -
```

Optional configuration variables:

| Variable | Default | Purpose |
|---|---|---|
| `FAUST_SEARCH_URL` | Entertix Faust search | Override discovery for diagnostics or tests |
| `REQUEST_TIMEOUT_SECONDS` | `15` | Timeout for each request |
| `REQUEST_RETRY_LIMIT` | `3` | Retries for transient Entertix failures |
| `REQUEST_BACKOFF_SECONDS` | `1` | Initial exponential-backoff delay |
| `FAUST_MONITOR_USER_AGENT` | Descriptive monitor agent | Identify the read-only client |

On macOS, Python.org builds do not always load the operating system's public root certificates. The transport securely adds the macOS system root keychains to Python's normal verified TLS context; certificate verification is never disabled.

## Automated workflow

[`.github/workflows/monitor.yml`](.github/workflows/monitor.yml) runs at minute 17 of every hour in the `Europe/Bucharest` timezone and supports manual dispatch from **Actions → Monitor Faust tickets → Run workflow**.

The scheduled job:

- has a five-minute timeout;
- serializes monitor runs to avoid concurrent issue transitions;
- writes its performance table to the GitHub Actions job summary;
- requests only `contents: read` and `issues: write` permissions.

Before enabling it:

1. Push the repository and keep the workflow on the default branch.
2. In **Settings → Actions → General → Workflow permissions**, allow the workflow token to write issues if the repository or organization default is read-only.
3. Confirm the intended recipients appear under **Settings → Collaborators** and have accepted their invitations.
4. Manually dispatch one run and inspect its job summary.

No custom token is required in GitHub Actions; `GITHUB_TOKEN` is provided automatically. Do not add a personal access token unless repository policy specifically requires one.

GitHub scheduled workflows are not a real-time service. Runs can be delayed during platform load, and an availability window shorter than one hour can be missed. GitHub can also disable scheduled workflows in public repositories after 60 days without repository activity, so a private personal repository is preferable for unattended use. See [GitHub's scheduled workflow documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

## Tests

The offline suite uses synthetic HTML and JSON fixtures and never contacts Entertix or GitHub:

```bash
PYTHONPATH=src python3.12 -m unittest discover -s tests -v
```

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs this suite on pushes and pull requests with read-only repository permissions.

## Test phone notifications

The separate [`test-notification.yml`](.github/workflows/test-notification.yml) workflow creates a new issue assigned to every user GitHub reports as assignable in the repository. Manually running it from **Actions → Test issue notification → Run workflow** always creates the test issue.

Hourly issue creation is disabled by default. Its scheduled-test switch is near the top of the workflow:

```yaml
env:
  ENABLE_SCHEDULED_NOTIFICATION_TEST: "false"
```

To temporarily create test issues every hour at minute 29, edit the workflow from GitHub and change the value to `"true"`:

```yaml
env:
  ENABLE_SCHEDULED_NOTIFICATION_TEST: "true"
```

Commit that one-line change to the default branch. Change it back to `"false"` to stop hourly test issues; manual runs will continue to work. The scheduled workflow still starts briefly to read the switch, but skips issue creation while the switch is false.

Each manual run or enabled hourly run intentionally creates a fresh issue so that it can generate a new assignment notification. Close the test issues after confirming delivery.

## Request rate and failure behavior

Requests are sequential. With the eight performances listed during initial development, a successful run sends roughly seventeen small requests per hour: one search request, one event-detail request per performance, and one seat-map request per performance.

Transient network errors, HTTP 408/425/429 responses, and server errors are retried with bounded exponential backoff. Invalid HTML, missing ticket links, invalid JSON, or zero parsed seats produce an `unknown` result and a failed workflow rather than a false sold-out report.

## Live verification baseline

On 14 August 2026, a read-only dry run discovered Entertix event IDs `40017` through `40024`. Each map contained 440 seats and zero `seatingseatactive` seats, matching the sold-out map shown by Entertix.

The same verification confirmed two upstream details guarded by the parser:

- actual search results use `a.eventitem`, while unrelated recommendations use different classes;
- a valid empty search contains the explicit text `0 rezultate gasite`.

If neither verified structure exists, the monitor fails as `unknown` instead of silently treating a changed page as an empty or sold-out result.

## Rollback

Disable **Monitor Faust tickets** from the Actions page or remove `.github/workflows/monitor.yml`. Existing monitor issues remain ordinary GitHub Issues and can be closed manually. The monitor creates no Entertix-side state to clean up.
