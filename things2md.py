# Things3 Logbook -> Markdown conversion script.
# For use in Obsidian for Daily Notes.
# Execute from Obsidian with the shellcommands community plugin.

import argparse
from argparse import RawTextHelpFormatter
import errno
import os
import re
import sys
import urllib.parse
from datetime import datetime
from dateutil import tz
from dateutil.relativedelta import *
from dotenv import load_dotenv
import things

# #############################################################################
# CONFIGURATION
# #############################################################################

# get config from .env
load_dotenv()

# optional
ENV_SKIP_TAGS = os.getenv("SKIP_TAGS")
if ENV_SKIP_TAGS:
    ENV_SKIP_TAGS = ENV_SKIP_TAGS.split(",")

# #############################################################################
# CLI ARGUMENTS
# #############################################################################

parser = argparse.ArgumentParser(description='Things3 database -> Markdown conversion script.', formatter_class=RawTextHelpFormatter)

parser.add_argument('--date', help='Date to get completed tasks for, in ISO format (e.g., 2023-10-07).')
parser.add_argument('--debug', default=False, action='store_true', help='If set will show script debug information.')
parser.add_argument('--due', default=False, action='store_true', help='If set will show incomplete tasks with deadlines.')
parser.add_argument('--format', nargs='+', choices=['note','noemojis','wikilinks'], help='Format modes. Pick one or more of:\n note: Outputs each task as a formatted note.\n noemojis: Strips emojis.\n wikilinks: Formats project names as wikilinks.')
parser.add_argument('--gcallinks', default=False, action='store_true', help='If provided, appends links to create a Google calendar event for the task.')
parser.add_argument('--groupby', default='date', choices=['date','project'], help='How to group the tasks.')
parser.add_argument('--orderby', default='date', choices=['date','index','project'], help='How to order the tasks.')
parser.add_argument('--project', help='If provided, only tasks for this project are fetched.')
parser.add_argument('--range', help='Relative date range to get completed tasks for (e.g., "today", "1 day ago", "1 week ago", "this week" which starts on Monday). Completed tasks are relative to midnight of the day requested.')
parser.add_argument('--simple', default=False, action='store_true', help='If set will hide task subtasks, notes, and cancelled tasks.')
parser.add_argument('--tag', help='If provided, only uncompleted tasks with this tag are fetched.')
parser.add_argument('--tasklinks', default=False, action='store_true', help='If provided, appends a link to the task in Things.')
parser.add_argument('--today', default=False, action='store_true', help='If set will show incomplete tasks in Today.')
parser.add_argument('--oprojects', default=False, action='store_true', help='If set will show a list of projects, formatted for Obsidian + Dataview.')

args = parser.parse_args()

DEBUG = args.debug
ARG_DATE = args.date
ARG_DUE = args.due
ARG_FORMAT = [] if args.format is None else args.format
ARG_GCAL_LINKS = args.gcallinks
ARG_GROUPBY = args.groupby
ARG_ORDERBY = args.orderby
ARG_PROJECT = args.project
ARG_PROJECT_UUID = None # set later if ARG_PROJECT is provided
ARG_RANGE = args.range
ARG_SIMPLE = args.simple # TODO: might deprecate and fold into 'format' argument
ARG_TAG = args.tag
ARG_TASK_LINKS = args.tasklinks
ARG_TODAY = args.today
ARG_OPROJECTS = args.oprojects

required_args = [ARG_DATE, ARG_DUE, ARG_OPROJECTS, ARG_PROJECT, ARG_RANGE, ARG_TAG, ARG_TODAY]
if all(arg is None or arg is False for arg in required_args):
    sys.stderr.write(f"things2md: At least one of these arguments are required: date, due, oprojects, project, range, tag, today\n")
    parser.print_help()
    exit(errno.EINVAL) # Invalid argument error code

# #############################################################################
# GLOBALS
# #############################################################################

# TODO: move to configuration
PROJECT_SEPARATOR = "//"
HEADING_SEPARATOR = "//"
AREA_SEPARATOR = "//"
DEADLINE_SEPARATOR = "⚑"

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

TODAY = datetime.today().astimezone()
TODAY_DATE = TODAY.date()
TODAY_INT = int(TODAY_DATE.strftime('%Y%m%d'))
TODAY_TIMESTAMP = datetime(TODAY.year, TODAY.month, TODAY.day).timestamp()
TOMORROW = datetime(TODAY.year, TODAY.month, TODAY.day) + relativedelta(days=1)
TOMORROW_TIMESTAMP = TOMORROW.timestamp()

# #############################################################################
# FUNCTIONS
# #############################################################################

def get_datetime_range(date_range):
    '''
    Returns dates for the given date range expressed in English, relative to today.
    Supported: today, yesterday, X days ago, X weeks ago, X months ago, X years ago
      "this week" is also supported, and starts on Monday
    '''
    splitted = date_range.split()
    start_date = None
    end_date = None
    if date_range == "this week":
        start_date = TODAY - relativedelta(days=TODAY.weekday())
        end_date = start_date + relativedelta(days=6)
    elif len(splitted) == 1 and splitted[0].lower() == 'today':
        start_date = TODAY
    elif len(splitted) == 1 and splitted[0].lower() == 'yesterday':
        start_date = TODAY - relativedelta(days=1)
    elif splitted[1].lower() in ['day', 'days', 'd']:
        start_date = TODAY - relativedelta(days=int(splitted[0]))
    elif splitted[1].lower() in ['wk', 'wks', 'week', 'weeks', 'w']:
        start_date = TODAY - relativedelta(weeks=int(splitted[0]))
    elif splitted[1].lower() in ['mon', 'mons', 'month', 'months', 'm']:
        start_date = TODAY - relativedelta(months=int(splitted[0]))
    elif splitted[1].lower() in ['yrs', 'yr', 'years', 'year', 'y']:
        start_date = TODAY - relativedelta(years=int(splitted[0]))
    else:
        return None, None

    start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
    # set the end date to 11:59:59pm, to ensure we get all tasks
    if end_date:
        end_date = end_date.replace(hour=23, minute=59, second=59)
    else:
        end_date = TODAY.replace(hour=23, minute=59, second=59, microsecond=999999)

    return start_date, end_date

def has_skip_tags(tags_to_check):
    '''
    Returns True if any of the tags in the list provided is in ENV_SKIP_TAGS.
    '''
    skip = False
    if ENV_SKIP_TAGS:
        if any(item in tags_to_check for item in ENV_SKIP_TAGS):
            skip = True
    return skip

def indent_string(string_to_indent):
    '''
    Indents a multi-line string with tabs.
    '''
    lines = string_to_indent.split("\n")
    indented_lines = ["\t" + line for line in lines]
    indented_string = "\n".join(indented_lines)
    return indented_string

def query_areas():
    '''
    Fetches areas.
    '''
    kwargs = dict()
    if DEBUG: kwargs['print_sql'] = True; print("\AREAS QUERY:")

    areas = things.areas(**kwargs)

    return areas

def query_projects(first_datetime):
    '''
    Fetches projects not finished, or finished within the range provided.
    '''
    kwargs = dict(status=None)
    if DEBUG: kwargs['print_sql'] = True; print("\nPROJECT QUERY:")

    projects = things.projects(stop_date=False, **kwargs)
    if first_datetime is not None:
        # FIX: note that this drops the timezone, as Things works off UTC
        # sounds like this needs to be fixed in Things.py:
        # https://github.com/chrisgurney/things2md/pull/2#issuecomment-1967535472
        # ...or not? (similar discussion here:) https://github.com/PyGithub/PyGithub/issues/512
        stop_date = first_datetime.strftime("%Y-%m-%d")
        projects += things.projects(stop_date=f'>{stop_date}', **kwargs)

    return projects

def query_subtasks(task_ids):
    '''
    Fetches subtasks given a list of task IDs.
    '''
    kwargs = dict(include_items=True)
    if DEBUG: print("\nSUBTASK QUERY:"); kwargs['print_sql'] = True
    return [things.todos(task_id, **kwargs) for task_id in task_ids]

def query_tasks(first_datetime, last_datetime = None):
    '''
    Fetches tasks completed within the range provided.
    '''
    # things.py parameter documention here:
    # https://thingsapi.github.io/things.py/things/api.html#tasks
    kwargs = dict()

    if ARG_PROJECT:
        kwargs['project'] = ARG_PROJECT_UUID

    if ARG_TAG:
        kwargs['tag'] = ARG_TAG

    if first_datetime is not None:
        kwargs['status'] = None
        # FIX: note that this drops the timezone, as Things works off UTC
        # sounds like this needs to be fixed in Things.py:
        # https://github.com/chrisgurney/things2md/pull/2#issuecomment-1967535472
        # ...or not? (similar discussion here:) https://github.com/PyGithub/PyGithub/issues/512
        stop_date = first_datetime.strftime("%Y-%m-%d")
        kwargs['stop_date'] = f'>{stop_date}'
    elif ARG_DATE:
        kwargs['status'] = None
        kwargs['stop_date'] = f'{ARG_DATE}'
    elif ARG_DUE:
        kwargs['deadline'] = True
        kwargs['start_date'] = True
        kwargs['status'] = 'incomplete' # default, but leaving here for clarity
    elif ARG_TODAY:
        kwargs['start_date'] = True
        kwargs['start'] = 'Anytime'
        kwargs['index'] = 'todayIndex'
    else:
        kwargs['status'] = 'incomplete' # default, but leaving here for clarity

    if ARG_ORDERBY == "index":
        kwargs['index'] = 'todayIndex'

    if DEBUG: kwargs['print_sql'] = True; print("\nTASK QUERY:")

    tasks = things.tasks(**kwargs)

    # FIX: get tasks for next day if last_datetime is provided as well
    # get next day's tasks as well, so that we can account for GMT being past midnight local time
    if ARG_DATE: # or last_datetime
        # if ARG_DATE:
        given_date_obj = datetime.strptime(ARG_DATE, "%Y-%m-%d")
        # if last_datetime:
            # given_date_obj = last_datetime
        next_day_date_obj = given_date_obj + relativedelta(days=1)
        next_day_date = next_day_date_obj.strftime("%Y-%m-%d")

        kwargs['stop_date'] = f'{next_day_date}'
        next_day_tasks = things.tasks(**kwargs)
        tasks = tasks + next_day_tasks

    #
    # filter based on arguments
    #

    # return tasks based on the provided date
    if ARG_DATE:
        given_date_local = given_date_obj.astimezone()
        given_date_local_eod = given_date_local.replace(hour=23, minute=59, second=59)
        # FIX: do when we have an end date set 
        for item in tasks[:]:
            # FIX: should this instead specify that this is UTC?
            stop_date_local = datetime.strptime(item['stop_date'], "%Y-%m-%d %H:%M:%S").astimezone()
            if stop_date_local > given_date_local and stop_date_local <= given_date_local_eod:
                pass
            else:
                tasks.remove(item)

    #
    # sort based on arguments
    #
   
    if ARG_ORDERBY == "project":
        # FIXED: does sort by name
        tasks.sort(key=lambda x: x['stop_date'] if x['stop_date'] is not None else float('-inf'), reverse=True)
        tasks.sort(key=lambda x: x.get("project_title",""))
    elif ARG_ORDERBY == 'index':
        pass
    elif ARG_DUE:
        tasks.sort(key=lambda x: x['deadline'])
    elif ARG_TODAY:
        pass
    elif ARG_TAG:
        pass
    else:
        tasks.sort(key=lambda x: x['stop_date'] if x['stop_date'] is not None else float('-inf'), reverse=True)

    return tasks[:QUERY_LIMIT]

def remove_emojis(input_string):
    '''
    Strips out emojis from the given string.
    '''
    cleaned_string = EMOJI_PATTERN.sub(r'', input_string)
    cleaned_string = cleaned_string.strip()
    return cleaned_string

def get_gcal_url(task_id, title):
    '''
    Generates URL for the given task that creates a GCal event, linking back to the task.
    '''
    url_base = "https://calendar.google.com/calendar/u/0/r/eventedit"
    event_text = urllib.parse.quote_plus(title) # encode url
    things_url = things.link(task_id)
    event_details = f'<a href="{things_url}">{things_url}</a>'
    event_details = urllib.parse.quote_plus(event_details) # encode url
    url=f"{url_base}?text={event_text}&dates={GCAL_EVENT_DATES}&details={event_details}"
    return url

def format_project_name(project_title):
    '''
    Formats the name of the project for output according to provided arguments.
    '''
    output = project_title
    if ARG_FORMAT:
        if 'noemojis' in ARG_FORMAT:
            output = remove_emojis(output)
        if 'wikilinks' in ARG_FORMAT:
            output = f"[[{output}]]"
    return output

def format_notes(notes):
    '''
    Formats notes by replacing non http links with markdown links.
    '''
    non_http_pattern = r'\b((?!http)\w+://\S+)'
    # Find all non-HTTP URI links in the text
    non_http_links = re.findall(non_http_pattern, notes)
    # Replace non-HTTP URI links with markdown format
    for link in non_http_links:
        # Extract the scheme from the URI
        scheme = link.split("://")[0].capitalize()
        markdown_link = f'[{scheme} Link]({link})'
        notes = notes.replace(link, markdown_link)
    return notes

# #############################################################################
# MAIN
# #############################################################################

if DEBUG: print("PARAMS:\n{}".format(args))

start_datetime = None
end_datetime = None
if ARG_RANGE is not None:
    start_datetime, end_datetime = get_datetime_range(ARG_RANGE)
    if start_datetime == None:
        sys.stderr.write(f"things2md: Error: Invalid date range: {ARG_RANGE}")
        exit(errno.EINVAL) # Invalid argument error code
    if DEBUG: print(f"\nDATE RANGE:\n\"{ARG_RANGE}\" == {start_datetime} to {end_datetime}")

if DEBUG: print(f"\nTODAY: {TODAY}, TODAY_DATE: {TODAY_DATE}, TODAY_INT: {TODAY_INT}, TODAY_TIMESTAMP: {TODAY_TIMESTAMP}")

#
# Get Areas + Projects
#

# get area names
areas = dict()
if ARG_OPROJECTS:
    area_results = query_areas()
    for area in area_results:
        areas[area['uuid']] = area['title']

project_results = query_projects(start_datetime)

# format projects:
# store in associative array for easier reference later
if DEBUG: print(f"PROJECTS ({len(project_results)}):")
projects = {}
for row in project_results:
    if DEBUG: print(dict(row))
    formatted_project_name = format_project_name(row['title'])
    projects[row['uuid']] = formatted_project_name
    if ARG_PROJECT:
        if ARG_PROJECT in (row['title'], formatted_project_name):
            ARG_PROJECT_UUID = row['uuid']

if ARG_PROJECT and ARG_PROJECT_UUID is None:
    sys.stderr.write(f"things2md: Project not found: {ARG_PROJECT}")
    exit(errno.EINVAL) # Invalid argument error code

#
# Get Tasks
#

task_results = {}
# don't need to get tasks if we're just getting the projects list
if not ARG_OPROJECTS:
    task_results = query_tasks(start_datetime, end_datetime)

#
# Prepare Tasks
# 

completed_work_tasks = {}
cancelled_work_tasks = {}
skip_tag_tasks = {}
completed_work_task_ids = []
task_notes = {}

work_task_date_previous = ""
taskProject_previous = "TASKPROJECTPREVIOUS"

if DEBUG: print(f"\nTASKS ({len(task_results)}):")
for row in task_results:

    # pre-process tags and skip
    taskTags = ""
    if 'tags' in row:
        if has_skip_tags(row['tags']):
            skip_tag_tasks[row['uuid']] = dict(row)
            if DEBUG: print(f"... SKIPPED (TAG): {dict(row)}")
            continue
        taskTags = " #" + " #".join(row['tags'])
    if DEBUG: print(dict(row))

    # project name
    taskProject = ""
    taskProjectRaw = "No Project"
    if not ARG_PROJECT:
        if row.get('project') is not None:
            taskProjectRaw = projects[row['project']]
            taskProject = f"{taskProjectRaw} {PROJECT_SEPARATOR} "
        elif row.get('heading') is not None:
            # if it's not set, this may have a heading, so get the project name from it's UUID instead
            # TODO: should we store headings for faster lookups?
            heading_task = things.tasks(uuid=row['heading'])
            taskProject = format_project_name(heading_task['project_title']) + " " + PROJECT_SEPARATOR + " "

    # heading
    if 'heading_title' in row:
        taskProject += f"{row['heading_title']} {PROJECT_SEPARATOR} "

    # task date
    work_task_date = ""
    if row.get('stop_date') is not None:
        work_task_date = datetime.fromisoformat(row['stop_date']).date()

    # header
    if not ARG_SIMPLE:
        if ARG_GROUPBY == "date" and not ARG_DATE:
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
    if 'note' in ARG_FORMAT:
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
            work_task += f"{format_project_name(row['title'])} [↗]({things.link(row['uuid'])})"
        else:
            work_task += row['title'].strip()
            # task link
            if ARG_TASK_LINKS:
                work_task += f" [↗]({things.link(row['uuid'])})"

        # task date
        if work_task_date != "":
            if ARG_GROUPBY != "date" or (ARG_SIMPLE and ARG_RANGE not in ('today', 'yesterday')):
                work_task += f" • {work_task_date}"
        # gcal link
        if ARG_GCAL_LINKS:
            work_task += f" [📅]({get_gcal_url(row['uuid'], row['title'])})"
        if row.get('deadline'):
            work_task += f" • ⚑ {row['deadline']}"

    # task tags
    # work_task += f" • {taskTags}"
    completed_work_tasks[row['uuid']] = work_task

    if row['status'] == 'canceled':
        cancelled_work_tasks[row['uuid']] = work_task

    completed_work_task_ids.append(row['uuid'])

    if row.get('notes'):
        task_notes[row['uuid']] = format_notes(row['notes'])
        
if DEBUG:
    print(f"\nTASKS COMPLETED ({len(completed_work_tasks)}):\n{completed_work_tasks}")
    print(f"\nCOMPLETED NOTES ({len(task_notes)}):\n{task_notes}")
    print(f"\nSKIPPED TASKS ({len(skip_tag_tasks)}):\n{skip_tag_tasks}")

if len(skip_tag_tasks) > 0:
    sys.stderr.write(f"things2md: Skipped {len(skip_tag_tasks)} tasks with specified SKIP_TAGS\n")

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
            if 'note' in ARG_FORMAT:
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
                    if 'note' in ARG_FORMAT:
                        print(f"{task_notes[key]}")
                    else:
                        print(f"{indent_string(task_notes[key])}")
                if key in task_subtasks:
                    print(task_subtasks[key])
            if 'note' in ARG_FORMAT:
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

# format a list of projects as a list with inline attributes for Obsidian, grouped by area
if ARG_OPROJECTS:
    # TODO: refactor repeated code here
    for p in project_results:
        if 'area' not in p:
            projectDeadline = ""
            projectTags = ""
            if p['deadline']:
                projectDeadline = f" (deadline:: ⚑ {p['deadline']})"
            if 'tags' in p:
                if has_skip_tags(p['tags']):
                    continue
                projectTags = ",".join(p['tags'])
                projectTags = f" (taglist:: {projectTags})"
            print(f"- {format_project_name(p['title'])} [↗]({things.link(row['uuid'])}){projectDeadline}{projectTags}")
    for a in area_results:
        if 'tags' in a:
            if has_skip_tags(a['tags']):
                continue  
        for p in project_results:
            if 'area' in p:
                if p['area'] == a['uuid']:
                    projectArea = f" (area:: {remove_emojis(p['area_title'])})"
                    projectDeadline = ""
                    projectTags = ""
                    if p['deadline']:
                        projectDeadline = f" (deadline:: ⚑ {p['deadline']})"
                    if 'tags' in p:
                        if has_skip_tags(p['tags']):
                            continue
                        projectTags = ",".join(p['tags'])
                        projectTags = f" (taglist:: {projectTags})"
                    print(f"- {format_project_name(p['title'])} [↗]({things.link(row['uuid'])}){projectArea}{projectDeadline}{projectTags}")

if DEBUG: print("\nDONE!")
