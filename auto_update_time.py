# pip install ntplib

## 如果你地电脑更新的时间有问题，可以尝试下这个代码。

import os
import time
import ntplib

client = ntplib.NTPClient()

while True:
    try:
        resp = client.request('cn.pool.ntp.org')
        ts = resp.tx_time
        _date = time.strftime('%Y-%m-%d',time.localtime(ts))
        _time = time.strftime("%X", time.localtime(ts))
        print(_date)
        print(_time)
        os.system("date {} && time {}".format(_date,_time))
        time.sleep(10)
    except Exception:
        pass