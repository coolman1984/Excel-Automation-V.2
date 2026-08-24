# Questions for the business owner

Ask only these. They are the questions whose answers change the numbers.
Everything else (architecture, storage, ports, packaging) belongs to the
template, not to a business user.

Ask them in plain language, a few at a time, and repeat the answers back as a
short summary before you build anything.

1. What work should this replace? What are you doing by hand today?
2. Which files are used? What are they called when they arrive?
3. What does each file contain, and which tab?
4. **What does one row represent?** ("one invoice line", "one employee-month")
5. Which values, together, identify the same record if the file is sent again?
6. Can an old record be corrected by a later file? Should the new value win?
7. If a record disappears from the next file, does it mean "finished" or just
   "not in this file"?
8. How are the files related to each other? (for example sales → customers)
9. If two sources disagree about the same value, which one wins?
10. **Which totals prove the result is correct?** (the number you check by hand today)
11. Which numbers do you want to see first? Which exceptions matter?
12. What decision should the page support?
13. Who is allowed to approve that these numbers mean what we said?
14. How often will this be run?

## Rules while asking

- Never invent an answer. Anything unknown stays `PENDING_APPROVAL` in
  `project.json`, and the run will refuse to publish until it is confirmed.
- You may propose a value ("I think a row is one invoice line - is that right?").
  You may not approve it.
- Ask for one small, safe sample file per source. Never ask for real personal or
  customer data if a sample will do.
- Do not ask about Python, SQL, databases, ports, packaging or configuration
  files. Those are your job.

## What you write down afterwards

Fill in `approval` and `business` in `project.json`, put the grain in each
source's `grain`, put the checking numbers in `control_totals`, and record the
conversation in `.ai/ADAPTATION_REPORT.md`.
