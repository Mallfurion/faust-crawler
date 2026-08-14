## Why

Sibiu performances of *Faust* routinely sell out, while cancelled orders or newly announced dates can make tickets available without warning. An automated monitor is needed to check availability regularly and notify the repository owner quickly enough to act.

## What Changes

- Add discovery of current and newly announced *Faust* performances at Fabrica de Cultura in Sibiu from the Entertix search results.
- Add read-only seat-map availability checks that distinguish selectable seats from unavailable seats without reserving tickets or interacting with the cart.
- Add an hourly GitHub Actions workflow, plus manual execution, with bounded retries and observable run summaries.
- Add deduplicated availability alerts containing the performance date, available-seat count, and direct ticket-selection link.
- Add safe failure behavior so network, parsing, and upstream format errors are reported as unknown rather than incorrectly reported as sold out.
- Add automated tests for discovery, availability classification, failure handling, and alert transitions.

## Capabilities

### New Capabilities

- `faust-ticket-monitoring`: Discover relevant Sibiu *Faust* performances and determine their current selectable-seat availability from Entertix.
- `scheduled-monitor-execution`: Run the monitor hourly and on demand with retries, concurrency control, and human-readable results.
- `availability-notifications`: Notify once when tickets become available, suppress duplicate alerts while availability persists, and allow a later reappearance to trigger a new alert.

### Modified Capabilities

None.

## Impact

- Adds a small crawler application, automated tests, and a GitHub Actions workflow to this repository.
- Reads public Entertix search, event, and ticket seat-map responses at a conservative hourly rate; it does not authenticate, select seats, reserve inventory, or purchase tickets.
- Uses the repository's GitHub Issues and workflow token for durable alert state and owner notifications, with narrowly scoped `contents: read` and `issues: write` permissions.
- Introduces no changes to existing application behavior because the repository currently contains only OpenSpec scaffolding.
