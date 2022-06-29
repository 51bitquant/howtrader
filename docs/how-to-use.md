# 更新部分

1. gateway, 订单的推送，增加定时更新订单的部分接口
2. 修改订单的价格、volume、traded为Decimal
3. 添加对tradingview的支持.

# talib 安装过程

1. github搜索ta-lib: https://github.com/mrjbq7/ta-lib

2. 下载地址: https://www.lfd.uci.edu/~gohlke/pythonlibs/#ta-lib

3. 搜索ta-lib找到ta-lib的包: 
TA_Lib‑0.4.24‑cp39‑cp39‑win_amd64.whl

记得下载自己对应的python版本，cp39就是python3.9版本， amd64就是64位的意思。

4. 通过pip命令安装 
> pip install TA_Lib‑0.4.24‑cp39‑cp39‑win_amd64.whl