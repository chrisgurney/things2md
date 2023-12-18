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

# Examples

Show tasks completed within the last week, grouped by project, ordered by project:
`python3 things2md.py --range "1 week ago" --groupby project --orderby project`

Show tasks completed today:
`python3 things2md.py --range "today"`

Show tasks completed today, and omit subtasks, notes, and cancelled tasks:
`python3 things2md.py --range "today" --simple`

Show tasks completed yesterday:
`python3 things2md.py --range "yesterday"`

...and ordered by project, but omit subtasks, notes, and cancelled tasks:
`python3 things2md.py --range "yesterday" --orderby project --simple`

Show tasks completed in the last 3 days, and omit subtasks, notes, and cancelled tasks:
`python3 things2md.py --range "3 days ago" --simple`

Show tasks completed in the last week, ordered by project, but omit subtasks, notes, and cancelled tasks:
`python3 things2md.py --range "1 week ago" --orderby project --simple`

Show uncompleted tasks, tagged with "focus", ordered how they're ordered by index, and show links that you can click to create a Google Calendar event:
`python3 things2md.py --tag "focus" --orderby index --gcallinks`

Show uncompleted tasks, tagged with "import", formatted in markdown with task names as headers, notes as body text, and subtasks as a list:
`python3 things2md.py --tag "import" --format import --orderby index`

# Usage with Obsidian

This script was designed for use in Obsidian for Daily Notes, but as it outputs plain text as markdown, it really can be used anywhere you can run a Python script.

Execute from Obsidian with the shell commands community plugin. Recommended configuration as follows:

- Output at cursor position