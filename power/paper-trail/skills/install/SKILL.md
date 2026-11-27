---
name: install
description: Set up Paper Trail in a Kiro project, so every tool call is recorded and every session is checked by an independent witness. Use when the user wants to install, set up or repair Paper Trail.
---

# Install Paper Trail in a project

A power cannot carry hooks or an always-on steering rule, so this step is still
needed. It copies them into the project.

## Step 1: Check Paper Trail is installed for `python`

Run `python -c "import papertrail"` in the project folder. If it fails, ask the
user for the folder that holds Paper Trail and run `pip install <that folder>`.

## Step 2: Set up the project

Run this, with the project folder in place of `<project_folder>`:

```
python -m papertrail init <project_folder>
```

It copies four hook files and two hook scripts into `.kiro/hooks`, the statement
rule into `.kiro/steering`, adds the `paper-trail` server to
`.kiro/settings/mcp.json` and `.papertrail/` to `.gitignore`. It never replaces a
file that differs. If it says "Left alone", show the user the line and ask
before running it again with `--force`.

## Step 3: Check the result

Run `python -m papertrail doctor <project_folder>` and read it back to the user.
Every line should start with OK. For a MISSING line, follow its "Fix:" line.

Running `init` again is safe: when nothing is missing it changes nothing.
