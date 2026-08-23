# macro-ji — 天玑独立容器（验证评估层）
# COPY 镜像模式：真相 = 容器内 ≡ 仓库 HEAD；改码须重建镜像
FROM docker.1ms.run/library/python:3.11-slim

WORKDIR /app

# pyyaml 唯一第三方依赖（weight_matrix 模块级 HAS_YAML + tianji_verifier 函数内 import）
COPY requirements.txt /app/
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ -r requirements.txt

# 天玑验证内核（纯 stdlib + pyyaml）
COPY tianji_db.py tianji_verifier.py weight_matrix.py optim_config.py tianji_calibrator.py llm_judge.py /app/
# watchdog：T2 共享触发文件轮询（trigger → 执行验证 → 写回）
COPY verify_watchdog.py /app/

ENV OPENCLAW_WORKSPACE=/app
ENV TIANJI_DATA_DIR=/app/macro_data
ENV TZ=Asia/Shanghai

# 无端口暴露；由触发文件驱动（T2 机制）
CMD ["python3", "verify_watchdog.py"]
