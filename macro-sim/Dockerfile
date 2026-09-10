# 基础镜像与 pip 源可用 build-arg 覆盖（默认保留国内加速源）。
# 海外网络或自建镜像代理请改回官方源，例如：
#   docker build \
#     --build-arg BASE_IMAGE=python:3.11-slim \
#     --build-arg PIP_INDEX_URL=https://pypi.org/simple/ \
#     -t <image> <context>
ARG BASE_IMAGE=docker.1ms.run/library/python:3.11-slim
FROM ${BASE_IMAGE}

WORKDIR /app

# 换用国内镜像加速 apt，安装中文字体 + tzdata（08-18 P1-a：容器 TZ=UTC 致报告时间早 8h）
RUN sed -i 's|deb.debian.org|mirrors.ustc.edu.cn|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || \
    sed -i 's|deb.debian.org|mirrors.ustc.edu.cn|g' /etc/apt/sources.list 2>/dev/null || true && \
    apt-get update -q && apt-get install -y -q fonts-wqy-zenhei tzdata && rm -rf /var/lib/apt/lists/*
ENV TZ=Asia/Shanghai

# 安装依赖（用国内 pip 镜像）
COPY requirements.txt .
ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
RUN pip install --no-cache-dir -i ${PIP_INDEX_URL} -r requirements.txt

# 复制源码
COPY run.py ./
COPY verify_human.py ./
COPY backfill_criteria.py ./
COPY core/ ./core/
COPY config/ ./config/
COPY souls/ ./souls/
COPY scripts/ ./scripts/
COPY VERSION ./

# 输出目录
RUN mkdir -p /app/output /app/reports

CMD ["python3", "-u", "run.py", "--daemon"]
