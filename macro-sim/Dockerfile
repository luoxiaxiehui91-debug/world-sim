FROM docker.1ms.run/library/python:3.11-slim

WORKDIR /app

# 换用国内镜像加速 apt，安装中文字体
RUN sed -i 's|deb.debian.org|mirrors.ustc.edu.cn|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || \
    sed -i 's|deb.debian.org|mirrors.ustc.edu.cn|g' /etc/apt/sources.list 2>/dev/null || true && \
    apt-get update -q && apt-get install -y -q fonts-wqy-zenhei && rm -rf /var/lib/apt/lists/*

# 安装依赖（用国内 pip 镜像）
COPY requirements.txt .
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ -r requirements.txt

# 复制源码
COPY run.py ./
COPY core/ ./core/
COPY config/ ./config/
COPY souls/ ./souls/
COPY scripts/ ./scripts/
COPY VERSION ./

# 输出目录
RUN mkdir -p /app/output /app/reports

CMD ["python3", "-u", "run.py", "--daemon"]
