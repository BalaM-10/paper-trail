# Sample Project

This is the demo project used by Paper Trail to illustrate evidence recording
and claim verification.

## What it does

`cleanup.py` claims to only clear the build cache, but also silently deletes
`notes.txt`. Running it inside a Kiro session lets Paper Trail catch the
discrepancy: the witness sees that `notes.txt` was deleted, the agent's
statement does not mention it, and the verifier stamps the session
`CONTRADICTED`.

## Usage

See the top-level [README.md](../README.md) for the full demo walkthrough.

```powershell
python sample/reset.py        # restore sample files before each demo run
python sample/cleanup.py      # run inside a Kiro session to record the event
```
