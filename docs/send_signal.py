from requests import Response
import requests
import json

## 发送信号到框架
url = 'http://127.0.0.1:9999/webhook'
data = {
    'action': 'long',
    'passphrase':'howtrader12344',  # 你的
    'tv_id': 'eth',
    'volume': 10,
}

print(json.dumps(data))

response:Response = requests.post(url, data=json.dumps(data))
print(response.json())


'''
# 框架中处理的方式如下

import json
from flask import Flask, request

# create global event_engine
event_engine: EventEngine = EventEngine()
passphrase = SETTINGS.get("passphrase", "")
port = SETTINGS.get("port", 9999)

app = Flask(__name__)


@app.route('/', methods=['GET'])
def welcome():
    return "Hi, this is tv server!"


@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = json.loads(request.data)
        if data.get('passphrase', None) != passphrase:
            return {"status": "failure", "msg": "passphrase is incorrect"}
        del data['passphrase']  # del it for safety.
        event: Event = Event(type=EVENT_TV_SIGNAL, data=data)
        event_engine.put(event)
        return {"status": "success", "msg": ""}
    except Exception as error:
        return {"status": "error", "msg": str(error)}


def start_tv_server():
    app.run(host="127.0.0.1", port=port)
'''
