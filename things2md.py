# Things3 Logbook -> Markdown conversion script.
# For use in Obsidian for Daily Notes.
# Execute from Obsidian with the shellcommands community plugin.

import argparse
import os
import sqlite3
import re
import urllib.parse
from datetime import datetime
from dateutil.relativedelta import *
from dotenv import load_dotenv

# #############################################################################
# CONFIGURATION
# #############################################################################

load_dotenv()

# get path to main.sqllite from .env
THINGS_DB = os.getenv("THINGS_DB")

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
parser.add_argument('--range', help='Relative date range to get completed tasks for (e.g., "today", "1 day ago", "1 week ago"). Completed tasks are relative to midnight of the day requested.')
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

QUERY_LIMIT = 100

TODAY = datetime.today()
TODAY_DATE = TODAY.date()
TODAY_TIMESTAMP = datetime(TODAY.year, TODAY.month, TODAY.day).timestamp()
TOMORROW = datetime(TODAY.year, TODAY.month, TODAY.day) + relativedelta(days=1)
TOMORROW_TIMESTAMP = TOMORROW.timestamp()

# default GCal event times to 9am-9:30am today
event_start_time = datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)
event_finish_time = event_start_time + relativedelta(minutes=30)
event_start_rfc5545 = event_start_time.strftime('%Y%m%dT%H%M%S')
event_finish_rfc5545 = event_finish_time.strftime('%Y%m%dT%H%M%S')
GCAL_EVENT_DATES = f"{event_start_rfc5545}/{event_finish_rfc5545}"

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

# #############################################################################
# FUNCTIONS
# #############################################################################

def get_past_time(str_days_ago):
    '''
    Returns a timestamp for the given date range relative to today.
    today, yesterday, X days ago, X weeks ago, X months ago, X years ago
    '''

    splitted = str_days_ago.split()
    past_time = ""
    if len(splitted) == 1 and splitted[0].lower() == 'today':
        past_time = TODAY.timestamp()
    elif len(splitted) == 1 and splitted[0].lower() == 'yesterday':
        past_date = TODAY - relativedelta(days=1)
        past_time = past_date.timestamp()
    elif splitted[1].lower() in ['day', 'days', 'd']:
        past_date = TODAY - relativedelta(days=int(splitted[0]))
        past_time = past_date.timestamp()
    elif splitted[1].lower() in ['wk', 'wks', 'week', 'weeks', 'w']:
        past_date = TODAY - relativedelta(weeks=int(splitted[0]))
        past_time = past_date.timestamp()
    elif splitted[1].lower() in ['mon', 'mons', 'month', 'months', 'm']:
        past_date = TODAY - relativedelta(months=int(splitted[0]))
        past_time = past_date.timestamp()
    elif splitted[1].lower() in ['yrs', 'yr', 'years', 'year', 'y']:
        past_date = TODAY - relativedelta(years=int(splitted[0]))
        past_time = past_date.timestamp()
    else:
        return("Wrong date range format")

    # get midnight of the day requested, to ensure we get all tasks
    past_date = datetime.fromtimestamp(float(past_time))
    past_date = datetime(past_date.year, past_date.month, past_date.day)
    past_time = past_date.timestamp()

    return past_time    

def indent_string(string_to_indent):
    '''
    Indents a multi-line string with tabs.
    '''
    lines = string_to_indent.split("\n")
    indented_lines = ["\t" + line for line in lines]
    indented_string = "\n".join(indented_lines)
    return indented_string

def query_projects(past_time):
    '''
    Fetches projects not finished, or finished after the timestamp provided.
    '''
    where_clause = 'AND p.stopDate IS NULL'
    if past_time != None:
        where_clause = 'AND (p.stopDate IS NULL OR p.stopDate > {})'.format(past_time)

    PROJECT_QUERY = f"""
    SELECT
        p.uuid as uuid,
        p.title as title,
        p.stopDate as stopDate
    FROM
        TMTask t
    INNER JOIN TMTask p ON p.uuid = t.project
    WHERE
        p.trashed = 0
        {where_clause}
    GROUP BY
        p.uuid
    """

    conn = sqlite3.connect(THINGS_DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if DEBUG: print("\nPROJECT QUERY:" + PROJECT_QUERY)
    cursor.execute(PROJECT_QUERY)
    project_results = cursor.fetchall()
    conn.close()

    return project_results

def query_subtasks(task_ids):
    '''
    Fetches subtasks given a list of task IDs.
    '''
    SUBTASK_QUERY = f"""
    SELECT
        c.uuid as uuid,
        c.task as task,
        c.title as title,
        c.stopDate as stopDate
    FROM
        TMChecklistItem c
    WHERE
        c.task IN ({','.join(['?']*len(task_ids))})
    ORDER BY
        c.task, [index]
    """

    conn = sqlite3.connect(THINGS_DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if DEBUG: print("\nSUBTASK QUERY:" + SUBTASK_QUERY)
    cursor.execute(SUBTASK_QUERY, task_ids)
    subtask_results = cursor.fetchall()
    conn.close()

    return subtask_results

def query_tasks(past_time):
    '''
    Fetches tasks completed after the timestamp provided.
    '''
    # FUTURE: if both args provided, why not filter on both?
    where_clause = ''
    if past_time != None:
        where_clause = f'AND stopDate IS NOT NULL AND stopDate > {past_time} '
    elif ARG_DUE:
        where_clause = f'AND deadline IS NOT NULL AND startDate IS NOT NULL AND status = 0 AND start = 1 '
    elif ARG_TAG != None:
        where_clause = f'AND TMTag.title LIKE "%{ARG_TAG}%" AND stopDate IS NULL '
    elif ARG_TODAY:
        where_clause = 'AND startDate IS NOT NULL AND status = 0 AND start = 1 '

    if ARG_ORDERBY == "project":
        # FIX: doesn't actually sort by name (just by ID)
        orderby_clause = 'TMTask.project ASC, TMTask.stopDate DESC'
    elif ARG_ORDERBY == "index":
        orderby_clause = 'TMTask.todayIndex'
    elif ARG_DUE:
        orderby_clause = 'deadline'
    else:
        orderby_clause = 'TMTask.stopDate DESC'

    TASK_QUERY = f"""
    SELECT
        TMTask.uuid as uuid,
        TMTask.title as title,
        TMTask.notes as notes,
        TMTask.startDate as startDate,
        TMTask.stopDate as stopDate,
        TMTask.status as status,
        TMTask.project as project,
        date(
            CASE
                WHEN TMTask.deadline
            THEN
                format(
                    '%d-%02d-%02d',
                    (TMTask.deadline & 134152192) >> 16,
                    (TMTask.deadline & 61440) >> 12,
                    (TMTask.deadline & 3968) >> 7
                )
            ELSE
                TMTask.deadline
            END
        ) AS deadline,
        GROUP_CONCAT(TMTag.title, ' #') as tags
    FROM
        TMTask
    LEFT JOIN TMTaskTag
        ON TMTaskTag.tasks = TMTask.uuid
    LEFT JOIN TMTag
        ON TMTag.uuid = TMTaskTag.tags
    WHERE
        TMTask.trashed = 0
        {where_clause}
    GROUP BY
        TMTask.uuid
    ORDER BY
        {orderby_clause}
    LIMIT {QUERY_LIMIT}
    """

    conn = sqlite3.connect(THINGS_DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if DEBUG: print("\nTASK QUERY:" + TASK_QUERY)
    cursor.execute(TASK_QUERY)
    task_results = cursor.fetchall()
    conn.close()

    return task_results

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
    event_details = f'<a href="things:///show?id={task_id}">things:///show?id={task_id}</a>'
    event_details = urllib.parse.quote_plus(event_details) # encode url
    url=f"{url_base}?text={event_text}&dates={GCAL_EVENT_DATES}&details={event_details}"
    return f"[📅]({url})"

# #############################################################################
# MAIN
# #############################################################################

if DEBUG: print("THINGS_DB:\n{}".format(THINGS_DB))
if DEBUG: print("PARAMS:\n{}".format(args))

past_time = None
if ARG_RANGE != None:
    past_time = get_past_time(ARG_RANGE)
    if past_time == "Wrong date range format":
        print("Error: " + past_time + ": " + ARG_RANGE)
        exit()
    if DEBUG: print("\nDATE:\n{} -> {}".format(ARG_RANGE,past_time))

#
# Get Tasks
#

task_results = query_tasks(past_time)

#
# Get Projects
#

project_results = query_projects(past_time)

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
completed_work_task_ids = []
task_notes = {}

work_task_date_previous = ""
taskProject_previous = "TASKPROJECTPREVIOUS"

if DEBUG: print(f"\nTASKS ({len(task_results)}):")
for row in task_results:
    # pre-process tags and skip
    taskTags = ""
    if row['tags'] != None:
        if "personal" in row['tags'] or "pers" in row['tags']:
            if DEBUG: print(f"... SKIPPED (personal|pers tag): {dict(row)}")
            continue
        taskTags = " #" + row['tags']
    if DEBUG: print(dict(row))
    # project name
    taskProject = ""
    taskProjectRaw = "No Project"
    if row['project'] != None:
        taskProjectRaw = projects[row['project']]
        taskProject = f"{taskProjectRaw} // "
    # task date
    work_task_date = ""
    if row['stopDate'] != None:
        work_task_date = datetime.fromtimestamp(row['stopDate']).date()
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
            if row['status'] == 0:
                work_task += "[ ] "
            elif row['status'] == 2:
                work_task += "[x] "
            else:
                work_task += "[/] "
        # task project
        if ARG_GROUPBY != "project" or ARG_SIMPLE:
            work_task += f"{taskProject}"
        # task name
        work_task += row['title']
        # task date
        if work_task_date != "":
            if ARG_GROUPBY != "date" or (ARG_SIMPLE and ARG_RANGE not in ('today', 'yesterday')):
                work_task += f" • {work_task_date}"
        if row['deadline']:
            work_task += f" • ⚑ {row['deadline']}"
    # task tags
    # work_task += f" • {taskTags}"
    # gcal link
    if ARG_GCAL_LINKS:
        work_task += " " + get_gcal_link(row['uuid'], row['title'])
    completed_work_tasks[row['uuid']] = work_task
    if row['status'] == 2:
        cancelled_work_tasks[row['uuid']] = work_task
    completed_work_task_ids.append(row['uuid'])
    if row['notes']:
        task_notes[row['uuid']] = row['notes']
        
if DEBUG:
    print(f"\nTASKS COMPLETED ({len(completed_work_tasks)}):\n{completed_work_tasks}")
    print(f"\nCOMPLETED NOTES ({len(task_notes)}):\n{task_notes}")

#
# Get Subtasks (for completed tasks)
# 

if not ARG_SIMPLE:
    subtask_results = query_subtasks(completed_work_task_ids)

    if DEBUG: print(f"SUBTASKS ({len(subtask_results)}):")

    # format subtasks
    task_subtasks = {}
    for row in subtask_results:
        if DEBUG: print(dict(row))
        if row['task'] in task_subtasks:
            subtask = task_subtasks[row['task']] + "\n"
        else:
            subtask = ""
        if ARG_FORMAT == "import":
            subtask += "- "
        else:
            subtask += "\t- "
            if row['stopDate'] != None:
                subtask += "[/] "
            else:
                subtask += "[ ] "
        subtask += row['title']
        task_subtasks[row['task']] = subtask

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