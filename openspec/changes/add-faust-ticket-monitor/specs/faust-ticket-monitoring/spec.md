## ADDED Requirements

### Requirement: Discover relevant Faust performances
The system SHALL discover current Entertix event listings on every run and SHALL retain only events whose title is *Faust*, venue is Fabrica de Cultura (Sala Faust), and city is Sibiu. The system SHALL identify and deduplicate performances by their numeric Entertix event ID.

#### Scenario: Current performances are discovered
- **WHEN** the Entertix search response contains one or more matching Sibiu *Faust* performances
- **THEN** the system returns one normalized performance record per distinct event ID

#### Scenario: A newly announced performance appears
- **WHEN** a matching event ID is added to the Entertix search results after an earlier run
- **THEN** the next run includes the new performance without a code or configuration change

#### Scenario: Unrelated search result is present
- **WHEN** a search result does not match the required title, venue, and city
- **THEN** the system excludes that event from monitoring

### Requirement: Resolve published ticket-selection pages
The system SHALL obtain each monitored performance's ticket-selection URL from its event-detail page rather than constructing the URL from an assumed route pattern.

#### Scenario: Ticket link is published
- **WHEN** a verified event-detail page contains a ticket-selection link
- **THEN** the system associates that exact URL with the normalized performance record

#### Scenario: Ticket link is missing
- **WHEN** a verified future event does not contain a ticket-selection link
- **THEN** the system reports that performance as unknown and does not report it as sold out

### Requirement: Determine selectable-seat availability
The system SHALL request the structured seat-map data for each ticket-selection page and SHALL count a seat as available only when its class-token list contains `seatingseatactive`.

#### Scenario: Selectable seats exist
- **WHEN** a valid seat map contains at least one seat with the `seatingseatactive` class token
- **THEN** the system reports the performance as available with the exact selectable-seat count

#### Scenario: Valid map is sold out
- **WHEN** a valid seat map contains one or more seats and none contains the `seatingseatactive` class token
- **THEN** the system reports the performance as sold out with an available-seat count of zero

#### Scenario: Class name contains a misleading substring
- **WHEN** a seat class contains the text `seatingseatactive` only as part of a different token
- **THEN** the system does not count that seat as selectable

### Requirement: Fail safely on uncertain upstream data
The system MUST classify a performance as unknown when network retries are exhausted or when a required search, event, or seat-map response cannot be validated. Unknown results MUST NOT be converted to sold-out results.

#### Scenario: Seat-map response is malformed
- **WHEN** Entertix returns invalid JSON or a response without a valid non-empty seat collection
- **THEN** the system reports the affected performance as unknown and returns a failing run status

#### Scenario: Discovery response cannot be validated
- **WHEN** the search response cannot be fetched or parsed sufficiently to establish a valid discovery result
- **THEN** the system fails the run rather than reporting that no performances or tickets are available

### Requirement: Perform read-only monitoring
The system MUST NOT select seats, add items to a cart, create reservations, authenticate to Entertix, or attempt a purchase.

#### Scenario: Availability is checked
- **WHEN** the system monitors a performance
- **THEN** it sends only discovery requests and the public read-only seat-map data request

### Requirement: Produce structured monitoring results
The system SHALL produce a result for each discovered performance containing its event ID, title, performance date, event URL, ticket URL, total-seat count, selectable-seat count, status, and any diagnostic error.

#### Scenario: Run completes with mixed results
- **WHEN** multiple performances produce available, sold-out, or unknown states
- **THEN** the output contains an independently traceable record for every discovered performance

