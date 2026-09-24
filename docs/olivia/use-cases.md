# v5 use cases: what a governable autonomous agent is for

Working notes for [ADR-0067](../adr/0067-v5-fork-governable-autonomy.md), the
fork now named **Olivia** ([ADR-0068](../adr/0068-olivia-design-answers.md)).
Kept at this path; new Olivia-only docs go under `docs/olivia/`. Not a spec.
They test the design against the work an enterprise actually pays an
autonomous agent to do, and against the same agent running a home.

The five workflows come from Algo Insights, "The 5 Most Valuable AI Automations
to Sell" (Coding Nexus, Medium, 2026-08-22,
<https://medium.com/coding-nexus/the-5-most-valuable-ai-automations-to-sell-de6039a16170>).
The article cites vendor surveys and case studies (Salesforce, Microsoft,
Zapier, McKinsey, Make, Fiverr) for demand. Those figures are its claims, not
checked here, and nothing below depends on them.

## The shared shape

The article's point is that all five workflows share one shape. Each step has a
home in v5:

| Step | What it means | Where it lives in v5 |
|---|---|---|
| Input | A form, a mail, a call, a document, an HR event | The trigger strategy: buffer and defer, steer, queue or refuse |
| Understand | What is this input asking for | System 1 decider (Jev or another): typed labels with confidence |
| Retrieve context | The customer, the order, the purchase order, the policy | Tools (MCP, HTTP, command), each call seen by the governor |
| Apply rules | The business's own definition of good, valid, allowed | Declarative rules and pure functions, written by a human |
| Decide | Pick the action the rules leave open | System 1 for a choice among labels, System 2 (the LLM) for drafting and extraction |
| Safe action or hand-off | Act, or pass it to a person | The governor allows what policy covers; the rest is refused or handed off |
| Record everything | Why this action, on whose authority | Events, the session JSONL, and the signed receipt |

Two things follow.

**Rules come before the model.** The article's strongest advice is to give the
system the business's rules explicitly rather than asking a model "is this
good?". That is edgar's habit already: routing, permissions and scheduling are
pure functions over declarative rules. In v5 the business rules are policy
files a person writes. A model decides only what the rules leave open, and
below a confidence threshold a fixed rule decides.

**Handing off is an action, not a prompt.** ADR-0067 removes the human prompt at
run time: anything the policy does not cover is denied. The article's "human
review" branch is not a prompt either. It is the agent creating something a
person picks up in the business's own system: a draft bill awaiting approval, a
support ticket, a CRM task. So the policy allows "prepare and hand off" for
risky work and nothing more. The agent's job ends at the draft. The approval
happens outside the agent, by a person, in the system of record.

## 1. Lead qualification and follow-up

A lead arrives, is enriched, scored, written to the CRM, routed to a salesperson
and followed up.

- **Trigger:** each lead is queued as its own run. Duplicates of the same
  contact within minutes are buffered and merged.
- **Rules:** the company's scoring rules (service area, customer type, budget,
  timeline) and the score thresholds that map to an action: send to sales, ask
  for more information, nurture.
- **System 1:** which salesperson or team, whether the lead is spam.
- **System 2:** the follow-up message; the explanation a salesperson reads.
- **Policy:** read and write the CRM record; send a follow-up only from approved
  templates; no pricing or commitments.
- **Record:** the score, the rules that produced it, and the route. The
  explanation for the salesperson is a readable view of the receipt.

## 2. Customer support resolution

Understand, retrieve, act, escalate. The agent does not guess an order's status;
it looks it up. It does not recall a return policy; it retrieves the approved
one.

- **Trigger:** a new ticket is queued. A customer's follow-up while its run is
  still going steers that run, as outside data, tainted.
- **Rules:** which actions are safe (status, tracking, approved policy answers)
  and which are risky (refunds above a limit, address changes, cancellations).
- **System 1:** intent (where is my order, return, change of address,
  complaint); urgency.
- **System 2:** the reply, grounded in retrieved records and policy text.
- **Policy:** safe actions allowed. An address change needs a verified customer:
  a caveat on the ticket that only an identity check can satisfy. Risky actions
  are handed off to a human queue with the context already gathered.
- **Record:** what was retrieved, what was done, what was handed off and why.

## 3. Voice reception and booking

Answer the call, find out what is needed, check availability, book, confirm,
update the CRM.

- **This does not fit v5 as drafted.** A caller waits seconds, not a
  scheduler's tick. An inbox drained by the tick cannot serve it, and a
  listener makes the agent a service, which ADR-0067 does not yet allow.
- **If it is in scope:** the voice platform owns the call and the speech; the
  agent is called per turn of the conversation, with the booking tools behind
  the governor. That needs the listener amendment and a latency budget.
- **Recommendation:** out of scope for the first v5 milestone. Revisit once the
  trigger and governor work on batch inputs.

## 4. Document-to-system processing

Invoices, purchase orders, forms, receipts, contracts: read them, extract the
fields, validate, match, enter them into the system of record.

- **Trigger:** documents land in an inbox and are buffered into a batch per
  vendor or per day; each document then becomes its own run.
- **Rules:** field validation, totals, and matching against the purchase order.
  A mismatch is an exception, never a guess.
- **System 1:** document type; which vendor; whether it is a duplicate.
- **System 2:** field extraction from the unstructured document.
- **Policy:** read the inbox and the purchasing system; create a **draft** bill
  only. Posting or paying is never allowed; a person approves the draft in the
  finance system.
- **Record:** the extracted fields, the match result, the exception and its
  cause.

## 5. Employee service and onboarding

Offer signed: create the record, work out the role, request access, assign
equipment and training, send the welcome, track what is missing, tell the
manager. Offboarding is the same in reverse and matters more.

- **Trigger:** an HR event (offer signed, leaver date set) is queued. HR and IT
  questions from staff are queued as tickets.
- **Rules:** the role-to-access table, as data a person maintains.
- **System 1:** request type (HR, IT, access, equipment); which team owns it.
- **System 2:** answers to HR questions from approved documents; the welcome
  message.
- **Policy:** create access **requests**, never grant access. Offboarding may
  revoke, because revoking tightens.
- **Record:** every request, who owns it, what is still open. The manager's
  status view is built from the record.

## What the use cases say about the design

1. **Inputs are untrusted.** Leads, tickets, mail, invoices and calls come from
   outside. ADR-0067's "an input is data, never authority" is not an edge case,
   it is every case.
2. **The governor needs caveats about the subject, not only the resource.** "Only
   for a verified customer" (support) and "only for this employee's own record"
   (HR) are caveats on who the action is for. ADR-0039's five caveats cover
   which tools, which paths and hosts, how many calls and until when
   (`broker/caveats.py`); none names a subject. The v5 governor must.
3. **Draft, then hand off, is the main safe pattern.** Three of the five end in
   a draft a person approves in another system. The policy language must make
   "may create a draft, may not post" easy to say.
4. **Self-learning must not learn customer or employee data.** The learning
   boundary already excludes tool output, which is where CRM, order and HR data
   arrive. A self-learning strategy may learn "invoices from this vendor put the
   PO number in the footer", never a customer's details.
5. **Real time is a separate decision.** Voice, and live support chat, need a
   listener. Batch work (documents, onboarding, lead follow-up, ticket queues)
   fits the inbox and the tick.
6. **Each use case needs an outcome measure** before it is automated: time to
   first contact, tickets resolved without hand-off, exceptions caught, days to
   full access. That becomes the v5 eval set.

## At home

The same agent at home integrates with Home Assistant and the other home
platforms (Philips Hue, Siemens appliances, Samsung SmartThings, Apple
HomeKit) and acts on what happens in the house.

- **One hub first.** Home Assistant already integrates most of these
  platforms, and it can expose its entities and services to an agent through
  its own MCP server integration. The agent talks to Home Assistant and goes to
  a vendor's API directly only for what Home Assistant cannot reach. One
  integration to govern instead of five.
- **Three ways to act, in order of preference:**
  1. **Write an automation.** It runs inside Home Assistant, can be read and
     switched off there, and keeps working when the agent is off.
  2. **Write a script.** A named routine Home Assistant runs on request.
  3. **A bespoke action.** The agent calls a service once, for something
     that will not repeat.
- **Two speeds.** Reflexes (motion turns on a light) must answer in
  milliseconds, and no agent run should sit in that path: they belong in
  automations the agent wrote. The agent handles what needs judgement and can
  wait a minute: a water leak while nobody is home, a heating pattern that
  wastes energy, an appliance that failed. Home Assistant hands those events
  to the agent's inbox, and the trigger strategy decides: buffer (ten motion
  events are one fact), queue, steer a running session, or refuse.
- **Rules:** which devices the agent may touch at all; quiet hours; which
  rooms are private.
- **System 1:** is this event normal for this hour; which room; how urgent.
- **System 2:** writing the automation or script; explaining what it did.
- **Policy:** lights, media and notifications allowed. Locks, garage doors,
  alarms, cameras, ovens and heating limits are physical safety: denied, or
  handed off as a notification a person acts on.
- **Record:** every service call and every automation written, with the event
  that caused it.

What home adds to the design:

1. **A written automation is standing authority.** It runs every day after the
   run that wrote it has ended, outside the governor. So it is handled like a
   learned skill: written into a machine-owned place (its own Home Assistant
   package or folder, never the person's own automations), created **disabled**,
   and switched on by a person. That is "draft, then hand off" again, and
   "machine writers never touch human files" (PRD §4). An automation that
   touches a denied device is never written at all.
2. **Learning routines is user modelling.** "The lights go on at seven"
   learned from watching the house is a model of the people living in it, and
   user modelling is on the Never list. ADR-0067 does not amend that. Either
   the fork amends it on purpose, with the household's consent and a place to
   see and delete what was learned, or the agent only proposes automations a
   person asked for.
3. **Presence is sensitive data.** Who is home, and when, must not leave the
   house in a prompt to a cloud model without the household choosing that
   model. No hidden hosts applies with more force at home than at work.
4. **Home needs no enterprise governor.** One household, one machine: the
   in-process broker is enough, as ADR-0039 intended. The governor adapter is
   what makes the same agent fit both.

## Which one first

The article's closing advice is to automate one workflow carefully before
expanding. For v5 the best first workload is **document-to-system processing**:

- it is batch, so it fits the inbox and the tick with no listener;
- its only write is a draft, so the governor's first policy is small;
- a mismatch is checkable by a pure function, so "done means verified" applies
  directly;
- its inputs are documents, the clearest case of untrusted data.

Support resolution is the natural second: it adds steering, subject caveats and
hand-off queues.
