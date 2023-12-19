Things3 Logbook -> Markdown conversion script.

# Installation

`pip3 install -r requirements.txt`

Copy `.env.example` to `.env` and update with the path to your Things3 sqlite database file.

# Usage

Run without any parameters to see the full list of arguments available:

```
--debug             If set will show script debug information
--format {import}   Format mode. Import: Outputs tasks as headings, notes as body text, subtasks as bullets.
--groupby {date,project}
                    How to group the tasks
--orderby {date,index,project}
                    How to order the tasks
--range RANGE       Relative date range to get completed tasks for (e.g., "0 days ago", "1 day ago", "1 week ago")
--simple            If set will hide task subtasks + notes and cancelled tasks
--tag TAG           If provided, only uncompleted tasks with this tag are fetched
--gcallinks         If provided, appends links to create a Google calendar event for the task.
```

Only the `range` or `tag` parameter is required, at a minimum.

Note that nothing will be returned of no tasks match the given arguments.

# Examples

## Completed Tasks

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

## Todo Tasks

_To narrow down tasks to be done, I tag them with a special tag and retrieve just those tasks:_

Show uncompleted tasks, tagged with "focus", ordered how they're ordered by index, and show links that you can click to create a Google Calendar event:
```
python3 things2md.py --tag "focus" --orderby index --gcallinks
```

## Tasks as Content to be Exported (into Obsidian, or another note-taking tool)

_I frequently draft content in Things and just want to get it out as simple markdown:_

Show uncompleted tasks, tagged with "import", formatted in markdown with task names as headers, notes as body text, and subtasks as a list:
```
python3 things2md.py --tag "import" --format import --orderby index
```

# Usage with Obsidian

This script was designed for use in Obsidian for Daily Notes, but as it outputs plain text as markdown, it really can be used anywhere you can run a Python script.

I call this script via the [shell commands community plugin](https://github.com/Taitava/obsidian-shellcommands). Recommended configuration as follows:

1. Add the command per the above example. Make sure your path to the things2md.py script is absolute.
1. Click the gear icon for each command, and adjust these settings:
    - In the _General_ tab, set an alias for the command. For example, _tasks_today_ (You'll execute this from a slash command.)
    - In the _Output_ tab, under _Output channel for stdout_ set it to _Current file: caret position_

# FUTURE IDEAS

- I have attempted to get just the tasks that are in today's list, but I haven't figured out how to do that yet. My current workflow (or workaround, depending on your needs) is to tag tasks to be fetched using the `--tag` argument.