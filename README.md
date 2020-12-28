# how trader
How to be a (quant) trader.  
如何成为一个量化交易者

the project is forked from VNPY. you can refer to the vnpy project. For
easy to learn and easy to install the vnpy project. I just simply remove
the other part not related to cryptocurrency. 

这个项目是fork vnpy的代码。为了方便区分，我把名字改成了howtrader,
并对其中的部分代码进行了修改，主要为了方便大家学习和使用。vnpy的安装非常复杂，而且容易出错。主要是因为里面依赖的东西过多。
而且很多部分我们是用不到的。

# 安装 installation 
直接在终端输入:
> pip install git+https://github.com/51bitquant/howtrader.git

you can use pip to install the howtrader.

> pip install git+https://github.com/51bitquant/howtrader.git

如果提示你没有git, 那么你需要去安装git软件，具体的话参考系列课程的第十三课的视频。

或者你直接把代码下载下来，然后切换到你的虚拟环境，或者使用当前的环境也是可以的，
在终端输入：

> pip install -r requirements.txt 

> python setup.py install 

or you can directly download the source code. then open your termal,
then script the following command

> pip install -r requirements.txt 

> python setup.py install 

但是我们直接推荐你用pip来安装，这样它能帮你把各种依赖处理好，减少错误的发生。

but we recommend you using the pip to install the howtrader, for you can
encounter some unexpected errors.

# 更新版本 update
直接在终端输入: 

> pip install git+https://github.com/51bitquant/howtrader.git -U 



# 使用 Usage
你需要在项目下面创建一个文件夹加，howtrader, 这个主要是存放一些日记和配置文件的信息。
如果不不知道配置文件如何配置，你可以启动examples文件目录下面的main_window.py文件，就可以看到其下面的一些日志和配置文件信息了。

1. firstly you need to create a folder(howtrader) at your project, at
   this folder, there are log file or configuration file. If you're not
   sure how to config, you can simply run the main_window.py at examples
   folder, you can play with UI.
# 数据爬取
howtrader可以通过data_manager的app直接下载数据，但是这个过程比较慢，适合少量数据的更新。
如果你想批量获取数据，可以参考examples下面的download_data_demo2.py文件.

you can download the data through data_manage app, but it's pretty slow,
it just designs for small piece of data updating and strategy data
warming. If you want to download the data as soon as possible, you can
try the download_data_demo2.py or download_data_demo1.py at examples
folder by using the multi-threads for speeding.

## learning materials 学习资料

学习资料请参考网易云课堂[《VNPY数字货币量化交易从零到实盘》](https://study.163.com/course/courseMain.htm?courseId=1210904816)
你也可以在youtube或者b站找到相应的视频，搜索51bitquant即可找到视频。

## updates

1. V2.1.7.3 update the binance gateway for klines, subscribe the 1min
   kline for kline update, V2.1.7.3版本更新了币安的K线数据的更新。
2. V2.1.7.4 Order Status management for bad network or disconnection,
   V2.1.7.4版本对订单状态查询和更新,
   特别是在在网络失去连接的时候能够进行查询和更新。

3. V2.1.7.5 update the on_trade event and binance future api position
   更新对on_trade交易事件的推送，websocket断开的时候订单的成交能够重新推送，并且能够计算策略的仓位。

4. V2.1.7.6 : update the position. 对订阅的交易对，都会推送其头寸的更新.

5. V2.1.7.7 add the position_update_interval and order_update_interval,
   添加对订单和仓位信息的更新频率.
   
6. V2.1.7.8 move the default strategies to example/strategies folders
   把内置的策略移到example/strategies文件夹.
  
7. V2.1.7.9 account update interval and binance_spot_grid_strategy
   添加资产更新的定时推送和币安现货网格交易的策略。
  
8. V2.1.8 增加现货和合约网格策略 add spot and future grid strategies


## 联系方式
微信: bitquant51

[币安邀请链接](https://www.binancezh.pro/cn/futures/ref/51bitquant)