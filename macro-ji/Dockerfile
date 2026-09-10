# macro-ji — 天玑独立容器（验证评估层）
# COPY 镜像模式：真相 = 容器内 ≡ 仓库 HEAD；改码须重建镜像
# 基础镜像与 pip 源可用 build-arg 覆盖（默认保留国内加速源）。
# 海外网络或自建镜像代理请改回官方源，例如：
#   docker build \
#     --build-arg BASE_IMAGE=python:3.11-slim \
#     --build-arg PIP_INDEX_URL=https://pypi.org/simple/ \
#     -t <image> <context>
ARG BASE_IMAGE=docker.1ms.run/library/python:3.11-slim
FROM ${BASE_IMAGE}

WORKDIR /app

# pyyaml 唯一第三方依赖（weight_matrix 模块级 HAS_YAML + tianji_verifier 函数内 import）
COPY requirements.txt /app/
ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
RUN pip install --no-cache-dir -i ${PIP_INDEX_URL} -r requirements.txt

# 天玑验证内核（纯 stdlib + pyyaml）
COPY tianji_db.py tianji_verifier.py weight_matrix.py optim_config.py tianji_calibrator.py llm_judge.py /app/
# watchdog：T2 共享触发文件轮询（trigger → 执行验证 → 写回）
COPY verify_watchdog.py tianji_verify_cron.py verify_geo_auto.py verify_hypothesis.py verify_predictions.py /app/

ENV OPENCLAW_WORKSPACE=/app
ENV TIANJI_DATA_DIR=/app/macro_data
ENV TZ=Asia/Shanghai

# 无端口暴露；由触发文件驱动（T2 机制）
CMD ["python3", "verify_watchdog.py"]
