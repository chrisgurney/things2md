# Things3 Logbook -> Markdown conversion script.
# For use in Obsidian for Daily Notes.
# Execute from Obsidian with the shellcommands community plugin.

import argparse
from argparse import RawTextHelpFormatter
import errno
import json
import re
import sys
import urllib.parse
from datetime import datetime
from dateutil.relativedelta import *
import things

# #############################################################################
# CLI ARGUMENTS
# #############################################################################

parser = argparse.ArgumentParser(description='Things3 database -> Markdown conversion script.', formatter_class=RawTextHelpFormatter)

parser.add_argument('--date', help='Date to get completed tasks for, in ISO format (e.g., 2023-10-07).')
parser.add_argument('--debug', default=False, action='store_true', help='If set will show script debug information.')
parser.add_argument('--due', default=False, action='store_true', help='If set will show incomplete tasks with deadlines.')
parser.add_argument('--format', default=[], nargs='+', choices=['note','noemojis'], help='Format modes. Pick one or more of:\n note: Outputs each task as a formatted note.\n noemojis: Strips emojis.')
parser.add_argument('--groupby', choices=['date','project'], help='How to group the tasks.')
parser.add_argument('--orderby', default='date', choices=['date','index','project'], help='How to order the tasks.')
parser.add_argument('--project', help='If provided, only tasks for this project are fetched.')
parser.add_argument('--range', help='Relative date range to get completed tasks for (e.g., "today", "1 day ago", "1 week ago", "this week" which starts on Monday). Completed tasks are relative to midnight of the day requested.')
parser.add_argument('--tag', help='If provided, only uncompleted tasks with this tag are fetched.')
parser.add_argument('--template', default='default', help='Name of the template to use from the configuration.')
parser.add_argument('--today', default=False, action='store_true', help='If set will show incomplete tasks in Today.')
parser.add_argument('--oprojects', default=False, action='store_true', help='If set will show a list of projects, formatted for Obsidian + Dataview.')

args = parser.parse_args()

DEBUG = args.debug
ARG_DATE = args.date
ARG_DUE = args.due
ARG_FORMAT = args.format
ARG_GROUPBY = args.groupby
ARG_ORDERBY = args.orderby
ARG_PROJECT = args.project
ARG_PROJECT_UUID = None # set later if ARG_PROJECT is provided
ARG_RANGE = args.range
ARG_TAG = args.tag
ARG_TEMPLATE = args.template
ARG_TODAY = args.today
ARG_OPROJECTS = args.oprojects

required_args = [ARG_DATE, ARG_DUE, ARG_OPROJECTS, ARG_PROJECT, ARG_RANGE, ARG_TAG, ARG_TODAY]
if all(arg is None or arg is False for arg in required_args):
    sys.stderr.write(f"things2md: At least one of these arguments are required: date, due, oprojects, project, range, tag, today\n")
    parser.print_help()
    exit(errno.EINVAL) # Invalid argument error code

# #############################################################################
# CONFIGURATION
# #############################################################################

THINGS2MD_CONFIG_FILE = './things2md.json'

try:
    with open(THINGS2MD_CONFIG_FILE, "r") as config_file:
        CONFIG = json.load(config_file)
except:
    sys.stderr.write(f"things2md: Unable to open config file: {THINGS2MD_CONFIG_FILE}\n")
    exit(1)

CFG_AREA_SEPARATOR = CONFIG.get("area_sep", "")
CFG_DATE_SEPARATOR = CONFIG.get("date_sep", "")
CFG_DEADLINE_SEPARATOR = CONFIG.get("deadline_sep", "")
CFG_HEADING_SEPARATOR = CONFIG.get("heading_sep", "")
CFG_PROJECT_SEPARATOR = CONFIG.get("project_sep", "")
CFG_SKIP_TAGS = CONFIG.get("skip_tags", "").split(",") if CONFIG.get("skip_tags") else []
CFG_STATUS_SYMBOLS = CONFIG.get("status_symbols", "")

CFG_TEMPLATES = CONFIG.get("templates", [])
CFG_TEMPLATE = None
for template in CFG_TEMPLATES:
    if template.get("name") == ARG_TEMPLATE:
        CFG_TEMPLATE = template
        break
if CFG_TEMPLATE == None:
    sys.stderr.write(f"things2md: Unable to find template: {ARG_TEMPLATE}\n")
    exit(1)

# validate the template lines are set
required_template_lines = ["groupby_project", "groupby_date", "project", "task", "notes", "subtasks", "subtask"]
if not all(line in CFG_TEMPLATE for line in required_template_lines):
    sys.stderr.write(f"things2md: These template lines are required in {THINGS2MD_CONFIG_FILE} "
                     f"for the selected template '{ARG_TEMPLATE}': {required_template_lines}\n")
    exit(1)

# TODO: for ease-of-use, replace all variables with lower-case, prior to doing substitution
    
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
    if CFG_SKIP_TAGS:
        if any(item in tags_to_check for item in CFG_SKIP_TAGS):
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
    return output

def format_notes(notes):
    '''
    Formats notes by replacing non http links with markdown links.
    '''
    if notes:
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
for project in project_results:
    if DEBUG: print(dict(project))
    formatted_project_name = format_project_name(project['title'])
    projects[project['uuid']] = formatted_project_name
    if ARG_PROJECT:
        if ARG_PROJECT in (project['title'], formatted_project_name):
            ARG_PROJECT_UUID = project['uuid']

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

for task in task_results:

    # skip this task if requested
    if 'tags' in task and has_skip_tags(task['tags']):
        skip_tag_tasks[task['uuid']] = dict(task)
        if DEBUG: print(f"... SKIPPED (TAG): {dict(task)}")
        continue
    
    if DEBUG: print(dict(task))

    #
    # map Things data to template variables
    #

    vars = {}
    
    # these variables apply to both tasks and projects
    vars['date'] = f"{datetime.fromisoformat(task['stop_date']).date()}" if task['stop_date'] is not None else ""
    vars['date_sep'] = CFG_DATE_SEPARATOR if vars['date'] else ""
    vars['deadline'] = task['deadline'] if task['deadline'] is not None else ""
    vars['deadline_sep'] = CFG_DEADLINE_SEPARATOR if vars['deadline'] else ""
    vars['gcal_url'] = get_gcal_url(task['uuid'], task['title'])
    vars['notes'] = format_notes(task['notes']) if task['notes'] else None
    vars['url'] = things.link(task['uuid'])
    vars['status'] = CFG_STATUS_SYMBOLS.get(task['status'], CFG_STATUS_SYMBOLS['other'])
    # TODO: consider other tag list formats (e.g., for frontmatter lists)
    vars['tags'] = "#" + " #".join(task['tags']) if 'tags' in task else ""
    vars['title'] = task['title']
    vars['uuid'] = task['uuid']

    if task['type'] == "to-do":
        vars['heading'] = task['heading_title'] if 'heading_title' in task else ""
        vars['heading_sep'] = CFG_HEADING_SEPARATOR if vars['heading'] else ""
        vars['project'] = projects[task['project']] if 'project' in task else ""
        # if this task has a heading, we have to get the project name from the heading's task
        if not vars['project'] and ('heading' in task) and (heading_task := things.tasks(uuid=task['heading'])):
            vars['project'] = format_project_name(heading_task['project_title'])
        vars['project_sep'] = CFG_PROJECT_SEPARATOR if vars['project'] else ""
        # attempt merge with template
        try:
            md_output = CFG_TEMPLATE.get("task").format(**vars)
        except KeyError as e:
            sys.stderr.write(f"things2md: Invalid task template variable: '{e.args[0]}'.")
            exit(1)

    elif task['type'] == "project":
        vars['area'] = remove_emojis(task['area_title']) if 'area_title' in task else ""
        vars['area_sep'] = CFG_AREA_SEPARATOR if vars['area'] else ""
        vars['title'] = format_project_name(task['title'])
        # attempt merge with template
        try: 
            md_output = CFG_TEMPLATE.get("project").format(**vars)
        except KeyError as e:
            sys.stderr.write(f"things2md: Invalid project template variable: '{e.args[0]}'.")
            exit(1)

    elif task['type'] == "heading":
        # TODO: do something for --project output
        pass

    else:
        # areas?
        sys.stderr.write(f"things2md: DEBUG: UNHANDLED TYPE: {task['type']}")

    #
    # prepare groupby headers
    #

    if ARG_GROUPBY == "date":
        if vars['date'] != work_task_date_previous:
            try:
                completed_work_tasks[task['uuid'] + "-"] = CFG_TEMPLATE.get("groupby_date").format(**vars)
            except KeyError as e:
                sys.stderr.write(f"things2md: Invalid groupby_date template variable: '{e.args[0]}'.")
                exit(1)
            work_task_date_previous = vars['date']
    elif ARG_GROUPBY == "project":
        if 'project' in vars and vars['project'] and vars['project'] != taskProject_previous:
            try:
                completed_work_tasks[task['uuid'] + "-"] = CFG_TEMPLATE.get("groupby_project").format(**vars)
            except KeyError as e:
                sys.stderr.write(f"things2md: Invalid groupby_project template variable: '{e.args[0]}'.")
                exit(1)
            taskProject_previous = vars['project']

    #
    # prepare task + project output
    #

    md_output = md_output.replace("[[]]", "") # remove empty wikilinks
    md_output = md_output.strip() # remove spacing around output
    md_output = re.sub(r'\s+', ' ', md_output) # reduce spaces within output

    #
    # prepare note output (assuming template is non-empty)
    #    

    if vars['notes'] and CFG_TEMPLATE.get("notes"):
        try:
            task_notes[task['uuid']] = CFG_TEMPLATE.get("notes").format(**vars)
        except KeyError as e:
            sys.stderr.write(f"things2md: Invalid notes template variable: '{e.args[0]}'.")
            exit(1)

    #
    # store results for output later 
    #

    completed_work_tasks[task['uuid']] = md_output
    if task['status'] == 'canceled': cancelled_work_tasks[task['uuid']] = md_output
    completed_work_task_ids.append(task['uuid'])

if DEBUG:
    print(f"\nTASKS COMPLETED ({len(completed_work_tasks)}):\n{completed_work_tasks}")
    print(f"\nCOMPLETED NOTES ({len(task_notes)}):\n{task_notes}")
    print(f"\nSKIPPED TASKS ({len(skip_tag_tasks)}):\n{skip_tag_tasks}")

if len(skip_tag_tasks) > 0:
    sys.stderr.write(f"things2md: Skipped {len(skip_tag_tasks)} tasks with specified SKIP_TAGS\n")

#
# Get Subtasks (for completed tasks)
# 

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
            print(f"- {format_project_name(p['title'])} [↗]({things.link(p['uuid'])}){projectDeadline}{projectTags}")
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
                    print(f"- {format_project_name(p['title'])} [↗]({things.link(p['uuid'])}){projectArea}{projectDeadline}{projectTags}")

if DEBUG: print("\nDONE!")
