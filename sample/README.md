# Sample Project

The small project Paper Trail uses to show how an agent's report is checked
against what really happened on disk.

## The script and its mistake

`cleanup.py` is meant to clear the build cache. Build output ends in `.bin`
and the tools leave `.txt` logs beside it, so it deletes every `*.bin` and
`*.txt` file under this folder.

That pattern is too broad. `notes.txt` is a `.txt` file too, so it is deleted
along with the cache. The script prints one line, and the line only mentions the
cache:

```
Cleared build cache: removed cache/output.bin
```

It is an ordinary mistake, the kind a person makes with a glob. An agent that
runs the script sees that line, believes it, and reports that it cleared the
cache. The witness looks at the disk instead and sees that two files are gone.

## Try it

```powershell
python sample/reset.py        # put cache/output.bin and notes.txt back
python sample/cleanup.py      # run it inside a Kiro session to record the event
python -m papertrail verify <session_id>
```

The last command ends with `OVERALL: CONTRADICTED`: the statement says the
cache was cleared, and the witness saw `sample/notes.txt` deleted as well.

`python sample/make_demo_ledger.py` builds the demo record shown on the static
site. It runs this real script in a temporary copy of the project, so the demo
shows what the script does, not what someone wrote down about it.

See the top-level [README.md](../README.md) for the full walkthrough.
