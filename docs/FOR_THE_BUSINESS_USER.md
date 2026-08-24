# For the business user

You do not need to understand anything technical. There are two moments.

## 1. Asking for the report to be built (once)

Start a chat with the coding assistant and give it three things:

1. the file **`Project-Template.zip`**;
2. your Excel file(s), or a small sample of each;
3. a plain description of the work you do by hand today.

You can copy this message:

> I have attached `Project-Template.zip`, my Excel files and an explanation of
> what I need.
>
> Please follow `PROJECT_SKILL.md` inside the ZIP. Do not rebuild the engine -
> adapt the existing template by configuration, ask me the business questions,
> and return one `ProjectName.zip` that I can extract and run offline by
> double-clicking START.
>
> What I do today: <describe it in your own words - which files arrive, what one
> row means, which totals you check, what decision you make from the result>.

The assistant will ask you a handful of questions about meaning - what one row
represents, which totals prove the result is right, who approves the numbers.
Answer those in your own words. It will not ask you about programs, databases or
settings; those are not your job.

At the end it gives you one file: `YourProject.zip`.

## 2. Using the report (every time)

1. Save the ZIP somewhere on your computer and extract it.
2. Open the new folder and double-click **START**.
3. Your browser opens the report by itself.
4. Drag your Excel files onto the page and press **Process**.
5. Read the result:
   - **PASS** - every total matched;
   - **WARNING** - the totals matched, but some rows need your attention;
   - **BLOCK** - nothing was published and your previous result is untouched.
6. Use the dashboard, download a CSV, or press Print.

Nothing is installed. Nothing is sent anywhere. It works with no internet
connection. If something goes wrong, the page tells you what happened, whether
your previous results are still safe, and the one thing to do next - plus a
short support code to pass on.

## Why this saves time and cost

The engine is already built and tested. The assistant only has to understand
*your* files and *your* meaning, not invent a system from nothing. That is a
short conversation instead of a long build - and the result is the same product
every time.
