# -*- coding: utf-8-*-
from robot.sdk import unit
from robot.sdk.AbstractPlugin import AbstractPlugin
import requests
import json
from robot.Player import SoxPlayer
from recognizers_date_time import recognize_datetime, Culture
import datetime

def get_view_alias(): 
    return '由音箱创建'
def get_404_string():
    return '好像找不到对应的家具或者任务，请准确的指出它的别称或者地点。'
def get_state_failed_string():
    return '好像控制不了对应的家具，它可能需要检修。'

def get_refer_string(object):
    ret = ""
    if 'loc' in object:
        ret += object['loc'] + '的'
    if 'address' in object:
        ret += '家具'
    else:
        ret += '任务'
    if 'alias' in object:
        ret += object['alias']
    return ret
def get_state_string(type, state):
    strings = [
        ['关闭', '打开'], 
        ['关闭', '打开', '增强' ]
    ]
    return strings[type][state]

def get_date_string(dt):
    now = datetime.datetime.now()
    if dt.year == now.year:
        if dt.month == now.month:
            offset = dt.day - now.day
            if offset == 0:
                return ''
            return dt.strftime('%d日')
        return dt.strftime('%m月%d日')
    return dt.strftime('%Y年%m月%d日')
def get_time_string(dt):
    if dt.second == 0:
        return dt.strftime('%H时%M分')
    return dt.strftime('%H时%M分%S秒')
def get_datetime_string(dt):
    now = datetime.datetime.now()
    if now.timestamp() >= dt.timestamp():
        return '正在'
    return '将在' + get_date_string(dt) + get_time_string(dt)

def get_auto_string(dt, view):
    return get_datetime_string(dt) + '执行' + get_refer_string(view)
def get_furniture_string(dt, furniture, state):
    return get_datetime_string(dt) + get_state_string(furniture['type'], state) + get_refer_string(furniture)

def postJSON(method, input={}):
    input['pk_uid'] = 0
    response = requests.post('http://localhost:11151' + method, data=json.dumps(input))
    if response.status_code != 200:
        raise Exception(response)
    output = json.loads(response.content)
    return output

def hit(text, marks):
    for mark in marks:
        if text.find(mark) != -1:
            return True
    return False
def get_expect_state(text):
    marks = ['关']
    marks_powerful = ['增强']
    if hit(text, marks):
        return 0
    elif hit(text, marks_powerful):
        return 2
    else:
        return 1

def modify_views_score(text, views):
    marks_do = ['执行']
    marks_refer = ['任务']
    if hit(text, marks_do):
        for view in views:
            if view['score'] > 0:
                view['score'] += 1
    if hit(text, marks_refer):
        for view in views:
            if view['score'] > 0:
                view['score'] += 1

def get_datetime(text):
    results = recognize_datetime(text, Culture.Chinese)
    last = len(results) - 1
    if last >= 0:
        value = results[last].resolution['values'][0]
        print(value)
        if value['type'] == 'date':
            date = datetime.date.fromisoformat(value['value'])
            now = datetime.datetime.now()
            time = datetime.time(hour=now.hour,minute=now.minute,second=now.second)
            return int(datetime.datetime.combine(date, time).timestamp())
        elif value['type'] == 'time':
            time = datetime.time.fromisoformat(value['value'])
            return int(datetime.datetime.combine(datetime.date.today(), time).timestamp())
        elif value['type'] == 'datetime':
            return int(datetime.datetime.strptime(value['value'], '%Y-%m-%d %H:%M:%S').timestamp())
        elif value['type'] == 'datetimerange':
            start = int(datetime.datetime.strptime(value['start'], '%Y-%m-%d %H:%M:%S').timestamp())
            end = int(datetime.datetime.strptime(value['end'], '%Y-%m-%d %H:%M:%S').timestamp())
            return (start + end) // 2
    return 0

def calculate_configs(text):
    input = {}
    input['connected'] = True
    addresses = postJSON('/filter', input)['addresses']
    configs = []
    for address in addresses:
        input = {}
        input['address'] = address
        configs.append(postJSON('/config', input))
    for config in configs:
        config['score'] = 0
        if 'alias' in config:
            configAlias = config['alias']
            if text.find(configAlias) != -1:
                config['score'] += len(configAlias)
        if 'loc' in config:
            configLoc = config['loc']
            if text.find(configLoc) != -1:
                config['score'] += len(configLoc)
    return configs
def calculate_views(text):
    uids = postJSON('/views', {})['uids']
    views = []
    for uid in uids:
        input = {}
        input['uid'] = uid
        views.append(postJSON('/view', input))
    for view in views:
        view['score'] = 0
        if 'alias' in view:
            viewAlias = view['alias']
            if text.find(viewAlias) != -1:
                view['score'] += len(viewAlias)
        if 'loc' in view:
            viewLoc = view['loc']
            if text.find(viewLoc) != -1:
                view['score'] += len(viewLoc)
    return views

class Plugin(AbstractPlugin):

    def __init__(self, con):
        super(Plugin, self).__init__(con)
        self.player = SoxPlayer()

    def isValid(self, text, parsed):
        return True

    def handle(self, text, parsed):
        configs = calculate_configs(text)
        configs.sort(key=lambda a: a['score'], reverse=True)
        views = calculate_views(text)
        views.sort(key=lambda a: a['score'], reverse=True)
        modify_views_score(text, views)
        if len(configs) > 0 and len(views) == 0 and configs[0]['score'] > 0:
            self.handle_furniture(text, configs[0])
        elif len(configs) == 0 and len(views) > 0 and views[0]['score'] > 0:
            self.handle_auto(text, views[0])
        elif len(configs) > 0 and len(views) > 0 and (configs[0]['score'] > 0 or views[0]['score'] > 0):
            if configs[0]['score'] > views[0]['score']:
                self.handle_furniture(text, configs[0])
            else:
                self.handle_auto(text, views[0])
        else:
            self.say(get_404_string())

    def handle_furniture(self, text, config):
        start = get_datetime(text)
        if start == 0:
            input = {}
            input['address'] = config['address']
            expect = get_expect_state(text)
            input['state'] = expect
            postJSON('/state', input)
            self.say(get_furniture_string(datetime.datetime.now(), config, expect))
        else:
            state = {}
            state['address'] = config['address']
            expect = get_expect_state(text)
            state['state'] = expect
            states = []
            states.append(state)
            input = {}
            input['states'] = states
            input['alias'] = get_view_alias()
            output = postJSON('/view', input)
            input = {}
            input['view'] = output['uid']
            input['start'] = start
            postJSON('/auto', input)
            self.say(get_furniture_string(datetime.datetime.fromtimestamp(start), config, expect))
    
    def handle_auto(self, text, view):
        start = get_datetime(text)
        if start == 0:
            start = int(datetime.datetime.now().timestamp())
        input = {}
        input['start'] = start
        input['view'] = view['uid']
        postJSON('/auto', input)
        self.say(get_auto_string(datetime.datetime.fromtimestamp(start), view))
