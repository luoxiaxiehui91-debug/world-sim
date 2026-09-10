# 基础镜像与 pip 源可用 build-arg 覆盖（默认保留国内加速源）。
# 海外网络或自建镜像代理请改回官方源，例如：
#   docker build \
#     --build-arg BASE_IMAGE=python:3.11-slim \
#     --build-arg PIP_INDEX_URL=https://pypi.org/simple/ \
#     -t <image> <context>
ARG BASE_IMAGE=docker.1ms.run/library/python:3.11-slim
FROM ${BASE_IMAGE}

# 换用 USTC 镜像加速，安装 cron 和 tzdata
RUN sed -i 's|deb.debian.org|mirrors.ustc.edu.cn|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || \
    sed -i 's|deb.debian.org|mirrors.ustc.edu.cn|g' /etc/apt/sources.list 2>/dev/null || true \
    && apt-get update && apt-get install -y --no-install-recommends \
    cron \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

WORKDIR /app

# 先安装依赖（利用 Docker 层缓存）
COPY requirements.txt .
# wheels/ 目录预下载了 feedparser + sgmllib3k，避免构建时访问外网
COPY wheels/ /tmp/wheels/
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple/
ARG PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn
RUN pip install --no-cache-dir \
    -i ${PIP_INDEX_URL} \
    --trusted-host ${PIP_TRUSTED_HOST} \
    --find-links /tmp/wheels \
    -r requirements.txt

# 代码通过 volume 挂载，不 COPY（方便热更新）

# 创建日志目录
RUN mkdir -p /var/log/macro-scan

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

CMD ["/entrypoint.sh"]
