Things3 database -> Markdown conversion script.

# Installation

`pip3 install -r requirements.txt`

Copy `.env.example` to `.env` and set:

- Optional: `SKIP_TAGS` = a comma-separated list of tags for any tasks you want excluded from the output, for example: `"personal,pers"`; note this only works at the line-item (task) level

# Usage

Run without any parameters to see the full list of arguments available:

```
--date DATE         Date to get completed tasks for, in ISO format (e.g., 2023-10-07).
--debug             If set will show script debug information.
--due               If set will show incomplete tasks with deadlines.
--format {import,noemojis,wikilinks} [{import,noemojis,wikilinks} ...]
                    Format modes. Pick one or more of:
                     import: Outputs each task as a formatted note.
                     noemojis: Strips emojis.
                     wikilinks: Formats project names as wikilinks.
--gcallinks         If provided, appends links to create a Google calendar event for the task.
--groupby {date,project}
                    How to group the tasks
--orderby {date,index,project}
                    How to order the tasks
--range RANGE       Relative date range to get completed tasks for (e.g., "0 days ago", "1 day ago", "1 week ago",
                    "this week" which starts on Monday). Completed tasks are relative to midnight of the day requested.
--simple            If set will hide task subtasks + notes and cancelled tasks.
--tag TAG           If provided, only uncompleted tasks with this tag are fetched.
--today             If set will show incomplete tasks in Today.
--oprojects         If set will show a list of projects, formatted for Obsidian + Dataview.
```

The `--due`, `--range`, `--tag`, or `--today` parameter is required, at a minimum.

Notes:

- nothing will be returned if no tasks match the given arguments; and
- any tasks tagged with any tags in `SKIP_TAGS` as defined in `.env` are not included in the output.

# Examples

## Listing Completed Tasks

Show tasks completed within the last week, grouped by project, ordered by project:
```
python3 things2md.py --range "1 week ago" --groupby project --orderby project
```

Show tasks completed today:
```
python3 things2md.py --range "today"
```

Show tasks completed today, and omit subtasks, notes, and cancelled tasks:
```
python3 things2md.py --range "today" --simple
```

BETA: Show tasks completed on a specific date (in ISO format). Potentially fixed: I think due to dates being stored in GMT, if the completion date falls near midnight, it may show up if you're querying tasks for the next day.
```
python3 things2md.py --date 2024-02-25
```

Show tasks completed yesterday:
```
python3 things2md.py --range "yesterday"
```

...and ordered by project, but omit subtasks, notes, and cancelled tasks:
```
python3 things2md.py --range "yesterday" --orderby project --simple
```

Show tasks completed in the last 3 days, and omit subtasks, notes, and cancelled tasks:
```
python3 things2md.py --range "3 days ago" --simple
```

Show tasks completed in the last week, ordered by project, but omit subtasks, notes, and cancelled tasks:
```
python3 things2md.py --range "1 week ago" --orderby project --simple
```

## Listing Todo Tasks

Show uncompleted tasks in Today. Note: Evening tasks aren't grouped at the bottom due to things.py lacking support for [the `startBucket` column](https://github.com/chrisgurney/things2md/pull/2#issuecomment-1885672010).
```
python3 things2md.py --today
```

_To further narrow down tasks to be done, I tag them with a special tag and retrieve just those tasks:_

Show uncompleted tasks, tagged with "focus", ordered how they're ordered in Things (though Evening tasks seem to show at the top), and show links that you can click to create a Google Calendar event:
```
python3 things2md.py --tag "focus" --orderby index --gcallinks
```

Show uncompleted tasks with deadlines set, and those deadline dates, ordered by deadline:
```
python3 things2md.py --due
```

## Exporting Tasks as Simple Markdown to be Imported (into Obsidian, or another note-taking tool)

_I frequently draft notes in Things that I just want to get it out as simple markdown._

Show uncompleted tasks, tagged with "import", formatted in markdown with task names as headers, notes as body text, and subtasks as a list:
```
python3 things2md.py --tag "import" --format import --orderby index
```

# Usage with Obsidian

This script was designed for use in [Obsidian](https://obsidian.md/) for Daily Notes, but as it outputs plain text as markdown, it really can be used anywhere you can run a Python script.

I call this script via the [shell commands community plugin](https://github.com/Taitava/obsidian-shellcommands). Recommended configuration as follows:

1. Add the command per the above example. Make sure your path to the things2md.py script is absolute.
1. Click the gear icon for each command, and adjust these settings:
    - In the _General_ tab, set an alias for the command. For example, _tasks_today_ (You'll execute this from a slash command.)
    - In the _Output_ tab, under _Output channel for stdout_ set it to _Current file: caret position_

# References

- [obsidian-things-logbook](https://github.com/liamcain/obsidian-things-logbook) - This is an [Obsidian](https://obsidian.md/) plugin that periodically syncs the Things logook with your Obsidian vault. This wasn't the behavior I was looking for, hence why I developed `things2md`.
- [things.py](https://github.com/thingsapi/things.py) - Had I done more research first, I may have maybe used this instead of writing my own SQL queries. `things2md` has now been refactored to use this library, thanks to contributions from [@mikez](https://github.com/mikez)!
- [things.sh](https://github.com/AlexanderWillner/things.sh) - I found this shell script late in the development of `things2md`, but it looks like another good interpretation of how to query the Things database.