import things

kwargs = dict()

kwargs['start_date'] = True
kwargs['start'] = 'Anytime'
kwargs['index'] = 'todayIndex'

tasks = things.tasks(**kwargs)

for task in tasks:
    print(task['title'])