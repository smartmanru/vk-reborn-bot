import requests


class LongPoll(object):
    def __init__(self, key, server, ts):
        self.k = key
        self.s = server
        self.t = ts

    def get(self):
        r = requests.get('https://%s?act=a_check&key=%s&ts=%s&wait=25&mode=2&version=1' % (self.s, self.k, self.t))
        response = r.json()
        if 'ts' in response:
            self.t = response['ts']
            return response['updates']
        if 'failed' in response:
            return None
        else:
            raise LongPollException(str(response))


class LongPollException(Exception):
    pass
