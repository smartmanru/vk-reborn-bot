import os
import json

import redis
from apscheduler.schedulers.blocking import BlockingScheduler


from utils import db_like

sched = BlockingScheduler()
r = redis.from_url(os.environ.get("REDIS_URL"), charset="utf-8", decode_responses=True)


@sched.scheduled_job('cron', hour='21')
def timed_job():
    r.set('limit', '500')
    data = r.get('ll')
    if data is not None:
        json.loads(data)
        for i in data:
            db_like(i, 50)
    print('Called')


sched.start()
