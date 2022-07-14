# 如何对接tradingview等三方交易信号

howtrader增加了对接tradingview等第三方交易信号的功能，通过内置一个Web请求接口给对方调用，
然后把信号转发到对应的策略。该接口路径为:

- http://xxx.xxx.xxx.xxx:9999/webhook, 请求方法为POST请求。


## howtrader中Tradingview功能讲解

### 发送的数据要求

发送过来的数据要求
```
{
  "tv_id": "id号，howtrader根据改id转发到对应的策略",
  "action": "long" # 可选的值如下：long short exit, 默认三个值，你可以扩展，long是做多，short是做空，exit是有多头仓位就平多，有空头仓位就平空
  "volume": "下单的数量" # 可以有或者或者没有
  "passphrase": "设置的验证密码，防止别人随意调用"  # 该值有和vt_setting.json 中的passphrase 一致
 
}

你可以根据自己需要添加值，但是要在代码中加上并处理

```

### 内置的策略说明

1. SimpleTVStrategy

该策略是一个简单的市价单下单策略，收到信号后，会直接以超过市场的价格去下单，你可以设置滑点的值，如果单子没有成交，过几秒钟后，撤单重新超价下单，直到成交完成为止。
如果你的下单数量不大， 也不太考虑成交手续费和滑点，可以用该策略。策略参数如下：

- order_volume, float类型，下单数量，如果设置为零，则下单数量来自第三方接口

- max_slippage_percent, float, 超价的百分比，默认0.5，是0.5%。

2. BestLimitTVStrategy

该策略是最优限价单，收到信号后，会把单子拆分成小单，然后在买一(做多单)/卖一(做空单)上挂单等待成交，
如果价格偏离了，就会撤单，重新下单，知道成交完成为止。 如果你的下单数量比较大，可以考虑该策略。策略参数如下：

- order_volume, float类型，下单数量，如果设置为零，则下单数量来自第三方接口
- min_volume_per_order,
  float类型，拆单后最小的下单数量，不要设置小于最小的成交量，不然没法下单。
- max_volume_per_order，float类型，拆单后最大的下单数量

3. FixedVolumeBestLimitTVStrategy 

该策略跟BestLimitTVStrategy相同，它主要是收到相同的信号后，不做处理。比如你现在持有多单，那么你再发送做多的信号，
它就直接过滤，不做处理。参数跟BestLimitTVStrategy一致。

4. TwapTVStrategy

改策略是类似TWAP算法，把按时间来拆分下单，比如你有100个eth,
要在5分钟内下完，每10s下一次单。那么每次下单的数量为 100/(5*60/10) = 3.33个eth,
也就是每10s中下3.33个订单，这是标准的做法，但是策略中考虑了可能不成交的情况。所以还是平均下单，
然后按照类似BestLimit的方式下单。当然你可以参考具体的是实现过程，
按照自己的方式来实现下单方式。该策略参数如下:

- order_volume, float类型，下单数量，如果设置为零，则下单数量来自第三方接口
  
- interval, 每次循环下单的周期，比如上面说的10s钟下一次单
 
- total_order_time，下单的总的时间，单位为秒，比如上面说的10分钟，那么就是10 *
  60 = 600s


## nginx配置

由于在tradingview中，不能设置端口，所以需要通过nginx服务器来配置端口的转发。

### 1. 购买服务器、域名和安装nginx软件
如果你还没有服务器，可以购买一个服务器和域名，并把你的域名解析到当前服务器ip地址.

完成上一步之后，你还需要安装nginx软件。window用户可以从这个网站下载[https://nginx.org/en/download.html](https://nginx.org/en/download.html)，对于macOS系统,
你可以在终端输入一下命令安装:

> brew install nginx

其他有用的命令如下:

> brew services start nginx 

> brew services restart nginx

> brew services reload nginx

如果提示你没有brew, 那么你需要安装下homebrew, 具体百度或者谷歌一下。

对于window系统，你可以从以下链接下载nginx:
https://nginx.org/en/download.html, 然后解压到指定目录. 然后启动它:

> start nginx.exe

其他有用的命令如下:

> nginx.exe -s stop

> nginx.exe -s quit

> nginx.exe -s stop

> nginx.exe -s reload (reload)


另外你还需要编辑下nginx.cong文件,该文件只要是配置你的nginx进行端口转发。由于tradingview只能用80端口，所以你需要为你的web服务器进行端口转发。
在http里面添加如下配置信息：

```
server {
        listen 80;
        server_name your.dormain.com;
        charset utf-8;

        location / {
          proxy_pass http://localhost:9999;
        }

    }

```

修改nginx.conf后需要重启nginx 或者重新加载，你的配置才会生效， 最后运行main.py。

## linux 系统下安装nginx

**Window服务器推荐**：[https://www.ucloud.cn/site/active/kuaijie.html?invitation_code=C1x2EA81CD79B8C#dongjing](https://www.ucloud.cn/site/active/kuaijie.html?invitation_code=C1x2EA81CD79B8C#dongjing)


linux系统的如何部署和安装anaconda可以参考我的博客文章：[https://www.jianshu.com/p/50fc54ca5ead](https://www.jianshu.com/p/50fc54ca5ead)
里面有讲解如何在linux下安装anaconda。

使用前，更新下linux的一些库和依赖

> sudo apt-get update

> sudo apt-get upgrade

> sudo apt-get install build-essential libssl-dev libffi-dev python3-dev

执行命令安装nginx:
> sudo apt-get install nginx


nginx进程管理工具:

> sudo serice nginx start # 启动服务器
  
> sudo service nginx stop # 停止服务

> sudo service nginx restart # 重启服务

> sudo service nginx reload # 重载

> sudo service disable nginx # 默认情况下，Nginx配置为在服务器引导时自动启动。如果这不是您想要的，可以使用这条命令来禁用此行为

> sudo service enable nginx # 要重新启用服务以在启动时启动

> ps -ef|grep nginx # 查看进程号 

> kill -QUIT 927 # 杀掉进程927进程


接下来修改nginx配置文件, 配置文件的路径为：/etc/nginx/nginx.conf，
在该文件添加上下面的配置：

```
server {
        listen 80;
        server_name your_ip or your.domain.com; 
        charset utf-8;

        location / {
          proxy_pass http://localhost:9999;
        }

    }

```

server_name
为填写你的ip地址或者你的域名，如果填写域名的话，需要解析你的域名到你服务器的ip地址。


### 创建webhook信号提醒

 创建webhook提醒的时候，勾选Webhook Url 选项,
 然后把你webhook的链接粘贴进去，例如: http://www.your.domain/webhook,
 消息体格式如下

```
{"action": "{{strategy.order.comment}}",
  "symbol": "ETHUSDT",
"price":"{{strategy.order.price}}",
"close": "{{close}}",
"tv_id": "设置的tvid, howtrader根据该id来转发信号到相应的策略里面"
"passphrase": "你的认证安全字符串，类似密码，要跟howtrader里面设置的一样",
"volume": "下单数量，如果设置就会用该下单的数量，否则用策略中的下单的数量" 
}

```
在你的策略中，你订单的comment要填写成如下格式:

```

strategy.entry('L', strategy.long, comment="long")
strategy.entry('S', strategy.short, comment="short")
strategy.exit('tp', comment="exit")


```

# 联系方式

微信: bitquant51 

discord: 51bitquant#8078

如果使用中遇到任何问题，可以咨询我。




