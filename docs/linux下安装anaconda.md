# linux系统下如何安装anaconda


linux系统的如何部署和安装anaconda可以参考我的博客文章：[https://www.jianshu.com/p/50fc54ca5ead](https://www.jianshu.com/p/50fc54ca5ead)
里面有讲解如何在linux下安装anaconda。

linux下安装也很简单，anaconda的下载地址可以在下面网址找到:

> https://repo.anaconda.com/archive/

找到最新的版本，我这里选择的版本是 Anaconda3-2022.05-Linux-x86_64.sh,
完整的链接就是前面的地址加上名字， 如下:

> https://repo.anaconda.com/archive/Anaconda3-2022.05-Linux-x86_64.sh

下载完成后，输入:
> sudo bash Anaconda3-2022.05-Linux-x86_64.sh (刚下载的文件名)

然后一路按回车确认就可以了。安装完成后输入: conda，
如果输出正常，就没有问题，如果提示找不到conda命令，那么你需要添加conda到系统路径。

> vi ~/.bashrc

conda 默认安装的目录是：home/anaconda3，然后再最后一行添加:
PATH=/home/anaconda3/bin:$PATH, 具体的目录要看你的anaconda3安装在哪里。

添加完成后，输入：

> source ~/.bashrc

如果还有问题可以参考下面这个博客,
[https://blog.csdn.net/wyf2017/article/details/118676765](https://blog.csdn.net/wyf2017/article/details/118676765)