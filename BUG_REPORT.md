# Bug Report — Pretty Good AI Clinic Voice Agent

**Tester:** Amirjon Abdunayimov
**Method:** Automated patient-simulator bot (Twilio + OpenAI Realtime API) placed 10
scenario-driven calls to the clinic test line (+1-805-439-8008) from a single number
(+1-223-217-8770). Each call drives a realistic patient goal to stress-test the agent.
Recordings and transcripts for every call are in `submission/recordings/` and
`submission/transcripts/`, named by scenario.

Bugs are ordered by severity. Each entry lists what happened, why it matters, and which
call(s) reproduce it.

---

## CRITICAL

### 1. Agent cannot complete any action task — dead-ends after full verification
**What happens:** For every task that requires an action (reschedule, cancel, refill,
referral, booking that needs a record lookup), the agent collects the patient's full
identity — name, date of birth, name spelling, phone number — then says it "can't
proceed," promises to connect the patient to a support team, and instead plays
"Hello, you've reached the Pretty Good AI test line. Goodbye" and hangs up.
**Why it matters:** This is the core failure mode. The patient does all the
verification work, is promised a transfer, and is dropped with their task unresolved.
It also means PII is collected for an action the agent never had the ability to perform.
**Reproduced in:** `02_reschedule`, `03_cancel`, `04_refill`, `06_insurance`,
`07_weekend_trap`, `08_test_results`, `09_referral_billing`, `10_hard_name_interrupt`
(8 of 10 calls).

### 2. Cross-call identity bleed — every caller is greeted as "Marcus"
**What happens:** The agent opens nearly every call with "Am I speaking with Marcus?"
regardless of who is calling. "Marcus" was the patient in call 01; the name then
persisted across all later calls and even appeared as a third party ("are you calling
on behalf of Marcus?"). In one call it cycled through several names for one caller
(Marcus -> Brad -> Greg).
**Why it matters:** Strongly suggests state from one call/session is leaking into
others. In production this is a privacy and correctness risk — patients could be
addressed by, or associated with, another patient's identity.
**Reproduced in:** all 10 calls (greeting); third-party form in `06_insurance`,
`08_test_results`; name-cycling in the weekend-trap calls.

---

## HIGH

### 3. Broken / fake transfer
**What happens:** The agent says "connecting you to a representative, please wait,"
then immediately plays the test-line goodbye and ends the call. No transfer occurs.
**Why it matters:** A promised hand-off that silently fails is worse than refusing —
the patient waits, expecting help, and is dropped.
**Reproduced in:** same calls as Bug 1.

### 4. Over-collection of PII for general information questions
**What happens:** Asked a generic question that needs no record lookup — "Do you accept
Blue Cross Blue Shield PPO, and is there a copay for a routine visit?" — the agent
demanded date of birth, name spelling, and phone number, then still failed to answer.
**Why it matters:** Collecting identifying information that isn't needed for the request
is a privacy concern and a poor experience. Compare to `05_hours_location`, where a
general question (Saturday hours, parking) was answered correctly with no verification —
so handling of general questions is inconsistent.
**Reproduced in:** `06_insurance`.

### 5. Failed to catch closed-weekend booking
**What happens:** The patient repeatedly pushed to book "this Sunday at 10 a.m." The
agent engaged with the request and proceeded into verification without ever stating the
office is closed on weekends.
**Why it matters:** This is the kind of constraint a scheduling agent must enforce; it
should respond "we're closed Sundays, here are weekday options," not move toward booking
an impossible slot.
**Reproduced in:** `07_weekend_trap`.

---

## MEDIUM

### 6. Entity-capture errors (names, dates, phone numbers)
**What happens:** The agent mis-captures spoken details. Examples: patient said phone
"...9011," agent read back "...8888" (`07_weekend_trap`); patient said DOB "August 14th,"
an earlier run confirmed "August 4th" (`10`); last name "Brzezinski" rendered as
"Wojcik Brzezinski" (`10`); a hallucinated DOB appeared in an earlier scheduling run.
**Why it matters:** In a medical context, wrong identifiers can attach actions to the
wrong record. Numbers and spelled names need exact capture.
**Reproduced in:** `07_weekend_trap`, `10_hard_name_interrupt` (and earlier runs).

### 7. Out-of-order conversation logic
**What happens:** The agent emits steps out of sequence — e.g. saying "connecting you to
a representative" and only afterward asking "is that correct?" (`07`); asking "anything
else I can help with?" before actually answering the question (`05`); in an earlier
scheduling run, confirming a booking and then offering slots it had already booked.
**Why it matters:** Breaks the conversational contract and confuses the caller about
what state the request is in.
**Reproduced in:** `05_hours_location`, `07_weekend_trap` (and earlier runs).

### 8. Premature hang-up mid-task
**What happens:** While the patient was still spelling a difficult last name, the agent
said "Cool. Bye." mid-verification before being re-engaged.
**Why it matters:** Ending a call while the caller is actively providing required
information is an abrupt, trust-damaging failure.
**Reproduced in:** `10_hard_name_interrupt`.

---

## LOW

### 9. Garbled proper nouns (clinic name, company name, providers)
**What happens:** The agent frequently mangles fixed names: "Pretty **Dude** AI" instead
of Pretty Good AI; "**Evett** Point Orthopedics" instead of Pivot Point; provider names
like "Doogie Houser," "broker," "do V Hauser"; "follows up" rendered as "pawls up."
**Why it matters:** Getting its own clinic and company name wrong undermines credibility;
garbled provider names make bookings ambiguous.
**Reproduced in:** `05_hours_location`, `06_insurance`, `01_schedule_new` (and others).

### 10. Inconsistent / mis-rendered bilingual intro
**What happens:** The Spanish recording disclaimer appears on some calls and not others,
and in one call was itself garbled ("grabada para **trabajos** de calidad" instead of
"propósitos de calidad").
**Why it matters:** Minor, but an inconsistent and sometimes-corrupted standard greeting
looks unpolished.
**Reproduced in:** intermittent across calls; garbled form in `10_hard_name_interrupt`.

### 11. Foreign-language hallucination (observed in earlier run)
**What happens:** In an earlier weekend-trap call, the agent emitted a line of Korean
mid-conversation that read as a news-broadcast sign-off, unrelated to anything said.
**Why it matters:** Indicates the speech model can drop into unrelated
training-data text — jarring and a sign of instability.
**Reproduced in:** earlier `07_weekend_trap` run.

---

## What the agent did well (for balance)

- **General information answered correctly:** Saturday hours and parking were answered
  accurately and concisely (`05_hours_location`).
- **Protected sensitive results:** When asked to read lab/bloodwork results over the
  phone, the agent did not read them out and deferred to the clinic team
  (`08_test_results`) — correct handling of sensitive medical data.
- **Happy-path scheduling can work end-to-end:** In one new-patient run the agent found
  morning slots, handled a "that's not a morning" correction, booked a specific time,
  and offered a confirmation text (`01_schedule_new`).

---

## Summary

The agent handles simple, read-only questions reasonably well, but **cannot complete any
task that requires a record lookup or an action**: it gathers full PII, fails, and
dead-ends a fake transfer (Bugs 1, 3). The most systemic correctness/privacy issue is
**identity bleed across calls** (Bug 2). Supporting issues — unnecessary PII collection
(Bug 4), missed scheduling constraints (Bug 5), entity-capture errors (Bug 6), and
out-of-order logic (Bug 7) — compound the core failure. Proper-noun garbling and an
occasional language hallucination (Bugs 9, 11) point to speech-layer instability.