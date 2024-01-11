# Things3 Logbook -> Markdown conversion script.
# For use in Obsidian for Daily Notes.
# Execute from Obsidian with the shellcommands community plugin.

import argparse
import os
import re
import urllib.parse
from datetime import datetime
from dateutil.relativedelta import *
from dotenv import load_dotenv
import things

# #############################################################################
# CONFIGURATION
# #############################################################################

# get config from .env
load_dotenv()

# get path to main.sqllite from .env
# TODO: Note: can also automatically be deduced by things.py
ENV_THINGS_DB = os.getenv("THINGS_DB")
if not ENV_THINGS_DB:
    print(f"ERROR: .env is missing the THINGS_DB variable (path to your Things database)")
    exit()
ENV_THINGS_DB = os.path.expanduser(ENV_THINGS_DB)

# optional
ENV_SKIP_TAGS = os.getenv("SKIP_TAGS")
if ENV_SKIP_TAGS:
    ENV_SKIP_TAGS = ENV_SKIP_TAGS.split(",")

# #############################################################################
# CLI ARGUMENTS
# #############################################################################

parser = argparse.ArgumentParser(description='Things3 database -> Markdown conversion script.')

parser.add_argument('--debug', default=False, action='store_true', help='If set will show script debug information.')
parser.add_argument('--due', default=False, action='store_true', help='If set will show incomplete tasks with deadlines.')
parser.add_argument('--format', choices=['import'], help='Format mode. Import: Outputs tasks as headings, notes as body text, subtasks as bullets.')
parser.add_argument('--gcallinks', default=False, action='store_true', help='If provided, appends links to create a Google calendar event for the task.')
parser.add_argument('--groupby', default='date', choices=['date','project'], help='How to group the tasks.')
parser.add_argument('--orderby', default='date', choices=['date','index','project'], help='How to order the tasks.')
parser.add_argument('--range', help='Relative date range to get completed tasks for (e.g., "today", "1 day ago", "1 week ago", "this week" which starts on Monday). Completed tasks are relative to midnight of the day requested.')
parser.add_argument('--simple', default=False, action='store_true', help='If set will hide task subtasks + notes and cancelled tasks.')
parser.add_argument('--tag', help='If provided, only uncompleted tasks with this tag are fetched.')
parser.add_argument('--today', default=False, action='store_true', help='If set will show incomplete tasks in Today.')

args = parser.parse_args()

DEBUG = args.debug
ARG_DUE = args.due
ARG_FORMAT = args.format
ARG_GCAL_LINKS = args.gcallinks
ARG_GROUPBY = args.groupby
ARG_ORDERBY = args.orderby
ARG_RANGE = args.range
ARG_SIMPLE = args.simple # TODO: deprecate and fold into 'format' argument
ARG_TAG = args.tag
ARG_TODAY = args.today

if ARG_RANGE == None and ARG_TAG == None and not ARG_TODAY and not ARG_DUE:
    print(f"ERROR: The --due, --range, --tag, or --today parameter is required")
    parser.print_help()
    exit(0)

# #############################################################################
# GLOBALS
# #############################################################################

EMOJI_PATTERN = re.compile("["
                           u"\U0001F600-\U0001F64F"
                           u"\U0001F300-\U0001F5FF"
                           u"\U0001F680-\U0001F6FF"
                           u"\U0001F700-\U0001F77F"
                           u"\U0001F780-\U0001F7FF"
                           u"\U0001F800-\U0001F8FF"
                           u"\U0001F900-\U0001F9FF"
                           u"\U0001FA00-\U0001FA6F"
                           u"\U0001FA70-\U0001FAFF"
                           u"\U00002702-\U000027B0"
                           u"\U000024C2-\U0001F251"
                           "]+", flags=re.UNICODE)

# default GCal event times to 9am-9:30am today
event_start_time = datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)
event_finish_time = event_start_time + relativedelta(minutes=30)
event_start_rfc5545 = event_start_time.strftime('%Y%m%dT%H%M%S')
event_finish_rfc5545 = event_finish_time.strftime('%Y%m%dT%H%M%S')
GCAL_EVENT_DATES = f"{event_start_rfc5545}/{event_finish_rfc5545}"

QUERY_LIMIT = 100

TODAY = datetime.today()
TODAY_DATE = TODAY.date()
TODAY_INT = int(TODAY_DATE.strftime('%Y%m%d'))
TODAY_TIMESTAMP = datetime(TODAY.year, TODAY.month, TODAY.day).timestamp()
TOMORROW = datetime(TODAY.year, TODAY.month, TODAY.day) + relativedelta(days=1)
TOMORROW_TIMESTAMP = TOMORROW.timestamp()

# #############################################################################
# FUNCTIONS
# #############################################################################

def get_time_range(date_range):
    '''
    Returns ISO dates for the given date range, relative to today.
    Supported: today, yesterday, X days ago, X weeks ago, X months ago, X years ago
    "this week" is also supported, and starts on Monday
    '''
    splitted = date_range.split()
    start_time = None
    end_time = None
    start_date = None
    end_date = None
    if date_range == "this week":
        start_date = TODAY - relativedelta(days=TODAY.weekday())
        end_date = start_date + relativedelta(days=6)
        start_time = start_date.timestamp()
        end_time = end_date.timestamp()
    elif len(splitted) == 1 and splitted[0].lower() == 'today':
        start_time = TODAY.timestamp()
    elif len(splitted) == 1 and splitted[0].lower() == 'yesterday':
        start_date = TODAY - relativedelta(days=1)
        start_time = start_date.timestamp()
    elif splitted[1].lower() in ['day', 'days', 'd']:
        start_date = TODAY - relativedelta(days=int(splitted[0]))
        start_time = start_date.timestamp()
    elif splitted[1].lower() in ['wk', 'wks', 'week', 'weeks', 'w']:
        start_date = TODAY - relativedelta(weeks=int(splitted[0]))
        start_time = start_date.timestamp()
    elif splitted[1].lower() in ['mon', 'mons', 'month', 'months', 'm']:
        start_date = TODAY - relativedelta(months=int(splitted[0]))
        start_time = start_date.timestamp()
    elif splitted[1].lower() in ['yrs', 'yr', 'years', 'year', 'y']:
        start_date = TODAY - relativedelta(years=int(splitted[0]))
        start_time = start_date.timestamp()

    if start_time:
        # get the day previous to the one requested, to ensure we get all tasks
        start_date = datetime.fromtimestamp(float(start_time)) - relativedelta(days=1)
        start_date = start_date.date().isoformat()

    if end_time:
        # TODO: return end_date with adjustment
        # get 11:59:59 of the day requested, to ensure we get all tasks
        end_date = datetime.fromtimestamp(float(end_time))
        end_date = end_date.date().isoformat()

    return start_date, end_date

def indent_string(string_to_indent):
    '''
    Indents a multi-line string with tabs.
    '''
    lines = string_to_indent.split("\n")
    indented_lines = ["\t" + line for line in lines]
    indented_string = "\n".join(indented_lines)
    return indented_string

def query_projects(end_time):
    '''
    Fetches projects not finished, or finished after the timestamp provided.
    '''

    # TODO: filepath can be omitted; things.py will find default location
    kwargs = dict(status=None, filepath=ENV_THINGS_DB)
    if DEBUG: kwargs['print_sql'] = True; print("\nPROJECT QUERY:")

    projects = things.projects(stop_date=False, **kwargs)
    if end_time is not None:
        projects += things.projects(stop_date=f'>{end_time}', **kwargs)

    return projects

def query_subtasks(task_ids):
    '''
    Fetches subtasks given a list of task IDs.
    '''
    # TODO: filepath can be omitted; things.py will find default location
    kwargs = dict(include_items=True, filepath=ENV_THINGS_DB)
    if DEBUG: print("\nSUBTASK QUERY:"); kwargs['print_sql'] = True
    return [things.todos(task_id, **kwargs) for task_id in task_ids]

def query_tasks(end_time):
    '''
    Fetches tasks completed after the timestamp provided.
    '''
    # FUTURE: if both args provided, why not filter on both?

    # things.py parameter documention here:
    # https://thingsapi.github.io/things.py/things/api.html#tasks
    # 
    # TODO: if filepath can be omitted; things.py will find default location
    kwargs = dict(filepath=ENV_THINGS_DB)

    if end_time is not None:
        kwargs['status'] = None
        kwargs['stop_date'] = f'>{end_time}'
    elif ARG_DUE:
        kwargs['deadline'] = True
        kwargs['start_date'] = True
        kwargs['status'] = 'incomplete'
        kwargs['start'] = 'Inbox'
    elif ARG_TAG is not None:
        kwargs['search_query'] = ARG_TAG
        kwargs['status'] = None
        kwargs['stop_date'] = False
    elif ARG_TODAY:
        kwargs['start_date'] = True
        kwargs['start'] = 'Anytime'
        kwargs['index'] = 'todayIndex'

    if ARG_ORDERBY == "index":
        kwargs['index'] = 'todayIndex'

    if DEBUG: kwargs['print_sql'] = True; print("\nTASK QUERY:")

    tasks = things.tasks(**kwargs)

    if ARG_ORDERBY == "project":
        # FIXED: does sort by name
        tasks.sort(key=lambda x: x['stop_date'], reverse=True)
        tasks.sort(key=lambda x: x.get("project_title",""))
    elif ARG_ORDERBY == 'index':
        pass
    elif ARG_DUE:
        tasks.sort(key=lambda x: x['deadline'])
    elif ARG_TODAY:
        pass
    else:
        tasks.sort(key=lambda x: x['stop_date'], reverse=True)

    return tasks[:QUERY_LIMIT]

def remove_emojis(input_string):
    '''
    Strips out emojis from the given string.
    '''
    cleaned_string = EMOJI_PATTERN.sub(r'', input_string)
    cleaned_string = cleaned_string.strip()
    return cleaned_string

def get_gcal_link(task_id, task_title):
    '''
    Generates URL for the given task that creates a GCal event, linking back to the task.
    '''
    url_base = "https://calendar.google.com/calendar/u/0/r/eventedit"
    event_text = urllib.parse.quote_plus(task_title) # encode url
    things_url = things.link(task_id)
    event_details = f'<a href="{things_url}">{things_url}</a>'
    event_details = urllib.parse.quote_plus(event_details) # encode url
    url=f"{url_base}?text={event_text}&dates={GCAL_EVENT_DATES}&details={event_details}"
    return f"[📅]({url})"

# #############################################################################
# MAIN
# #############################################################################

if DEBUG: print("THINGS_DB:\n{}".format(ENV_THINGS_DB))
if DEBUG: print("PARAMS:\n{}".format(args))

start_date = None
end_date = None
if ARG_RANGE is not None:
    start_date, end_date = get_time_range(ARG_RANGE)
    if start_date == None:
        print(f"Error: Invalid date range: {ARG_RANGE}")
        exit()
    if DEBUG: print(f"\nDATE RANGE:\n\"{ARG_RANGE}\" == {start_date} to {end_date}")

if DEBUG: print(f"\nTODAY: {TODAY}, TODAY_DATE: {TODAY_DATE}, TODAY_INT: {TODAY_INT}, TODAY_TIMESTAMP: {TODAY_TIMESTAMP}")

#
# Get Tasks
#

task_results = query_tasks(start_date)

#
# Get Projects
#

project_results = query_projects(start_date)

# format projects:
# store in associative array for easier reference later and strip out project emojis
if DEBUG: print(f"PROJECTS ({len(project_results)}):")
projects = {}
for row in project_results:
    if DEBUG: print(dict(row))
    projects[row['uuid']] = remove_emojis(row['title'])

#
# Prepare Tasks
# 

completed_work_tasks = {}
cancelled_work_tasks = {}
skipped_tasks = {}
completed_work_task_ids = []
task_notes = {}

work_task_date_previous = ""
taskProject_previous = "TASKPROJECTPREVIOUS"

if DEBUG: print(f"\nTASKS ({len(task_results)}):")
for row in task_results:
    # pre-process tags and skip
    taskTags = ""
    if 'tags' in row:
        if ENV_SKIP_TAGS:
            if any(item in row['tags'] for item in ENV_SKIP_TAGS):
                skipped_tasks[row['uuid']] = dict(row)
                if DEBUG: print(f"... SKIPPED (TAG): {dict(row)}")
                continue
        taskTags = " #".join(row['tags'])
    if DEBUG: print(dict(row))
    # project name
    taskProject = ""
    taskProjectRaw = "No Project"
    if row.get('project') is not None:
        taskProjectRaw = projects[row['project']]
        taskProject = f"{taskProjectRaw} // "
    # task date
    work_task_date = ""
    if row.get('stop_date') is not None:
        work_task_date = datetime.fromisoformat(row['stop_date']).date()
    # header
    if not ARG_SIMPLE:
        if ARG_GROUPBY == "date":
            # date header
            if work_task_date != work_task_date_previous:
                completed_work_tasks[row['uuid'] + "-"] = f"\n## ☑️ {work_task_date}\n"
                work_task_date_previous = work_task_date
        elif ARG_GROUPBY == "project":
            # project header
            if taskProject != taskProject_previous:
                completed_work_tasks[row['uuid'] + "-"] = f"\n## ☑️ {taskProjectRaw}\n"
                taskProject_previous = taskProject
    # task title, project, date
    if ARG_FORMAT == "import":
        work_task = f"# {row['title']}\n"
    else:
        work_task = "- "
        if not ARG_SIMPLE:
            if row['status'] == 'incomplete':
                work_task += "[ ] "
            elif row['status'] == 'canceled':
                work_task += "[x] "
            else:
                work_task += "[/] "
        # task project
        if ARG_GROUPBY != "project" or ARG_SIMPLE:
            work_task += f"{taskProject}"
        # task name
        # if it's a project
        if row['type'] == 'project':
            # link to it in Things
            work_task += f"{remove_emojis(row['title'])} [↗]({things.link(row['uuid'])})"
        else:
            work_task += row['title'].strip()
        # task date
        if work_task_date != "":
            if ARG_GROUPBY != "date" or (ARG_SIMPLE and ARG_RANGE not in ('today', 'yesterday')):
                work_task += f" • {work_task_date}"
        # gcal link
        if ARG_GCAL_LINKS:
            work_task += f" {get_gcal_link(row['uuid'], row['title'])}"
        if row.get('deadline'):
            work_task += f" • ⚑ {row['deadline']}"
    # task tags
    # work_task += f" • {taskTags}"
    completed_work_tasks[row['uuid']] = work_task
    if row['status'] == 'canceled':
        cancelled_work_tasks[row['uuid']] = work_task
    completed_work_task_ids.append(row['uuid'])
    if row.get('notes'):
        task_notes[row['uuid']] = row['notes']
        
if DEBUG:
    print(f"\nTASKS COMPLETED ({len(completed_work_tasks)}):\n{completed_work_tasks}")
    print(f"\nCOMPLETED NOTES ({len(task_notes)}):\n{task_notes}")
    print(f"\nSKIPPED TASKS ({len(skipped_tasks)}):\n{skipped_tasks}")

#
# Get Subtasks (for completed tasks)
# 

if not ARG_SIMPLE:
    tasks_with_subtasks = query_subtasks(completed_work_task_ids)
    tasks_with_subtasks = [todo for todo in tasks_with_subtasks if todo.get('checklist')]

    if DEBUG: print(f"TASKS WITH SUBTASKS ({len(tasks_with_subtasks)}):")
    # format subtasks
    task_subtasks = {}
    for row in tasks_with_subtasks:
        if DEBUG: print(row['uuid'], row.get('title'))
        for checklist_item in row.get('checklist'):
            if row['uuid'] in task_subtasks:
                subtask = task_subtasks[row['uuid']] + "\n"
            else:
                subtask = ""
            if ARG_FORMAT == "import":
                subtask += "- "
            else:
                subtask += "\t- "
                if checklist_item.get('stop_date') is not None:
                    subtask += "[/] "
                else:
                    subtask += "[ ] "
            subtask += checklist_item['title']
            task_subtasks[row['uuid']] = subtask

    if DEBUG: print(task_subtasks)

#
# Write Tasks
# 

if DEBUG: print("\nWRITING TASKS ({}):".format(len(completed_work_tasks)))

if completed_work_tasks:
    # if not ARG_SIMPLE and ARG_RANGE != None:
    #     print('# ☑️ Since {}'.format(ARG_RANGE.title()))
    
    for key in completed_work_tasks:
        # if DEBUG: print(completed_work_tasks[key])
        if key not in cancelled_work_tasks:
            print(f"{completed_work_tasks[key]}")
            if not ARG_SIMPLE:
                if key in task_notes:
                    if ARG_FORMAT == "import":
                        print(f"{task_notes[key]}")
                    else:
                        print(f"{indent_string(task_notes[key])}")
                if key in task_subtasks:
                    print(task_subtasks[key])
            if ARG_FORMAT == "import":
                print("\n---")
    if cancelled_work_tasks:
        if not ARG_SIMPLE:
            print("\n## 🅇 Cancelled\n")
            for key in cancelled_work_tasks:
                print(f"{cancelled_work_tasks[key]}")
                if key in task_notes:
                    print(f"{indent_string(task_notes[key])}")
                if key in task_subtasks:
                    print(task_subtasks[key])

if DEBUG: print("\nDONE!")
