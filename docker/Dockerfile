FROM python:3.11

LABEL authors="51bitquant"

RUN apt-get update && apt-get install -y \
    build-essential \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Download and install TA-Lib
WORKDIR /tmp
RUN wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz \
    && tar -xzf ta-lib-0.4.0-src.tar.gz \
    && cd ta-lib \
    && ./configure --prefix=/usr \
    && make \
    && make install \
    && cd .. \
    && rm -rf ta-lib ta-lib-0.4.0-src.tar.gz

# working directory
WORKDIR /app
COPY . /app

# Install Python packages
RUN pip install -r requirements.txt
RUN pip install TA-Lib==0.4.26
RUN pip install git+https://github.com/51bitquant/howtrader

# port for signal from Tradingview.
EXPOSE 9999
CMD [ "python", "-u", "main.py"]