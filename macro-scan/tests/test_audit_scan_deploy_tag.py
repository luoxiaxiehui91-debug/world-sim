#!/usr/bin/env python3
"""审计回归测试 (scan-deploy-tag / finding #14 HIGH correctness).

背景:
  deploy.sh 的 _build() 从 docker-compose.example.yml 提取镜像 tag 来 docker build,
  但线上 docker compose up 使用的是 docker-compose.yml。若两处 tag 不一致,
  --build 构建出的镜像永远不会被 compose 启用(compose 拉的是另一个 tag)。

期望(正确)行为:
  deploy.sh --build 构建所用的镜像 tag == docker-compose.yml 中声明的 image tag。

当前实现:
  example.yml=macro-scan:v7, docker-compose.yml=macro-scan:v8 → 不一致。
  这是已确认但尚未修复的 bug,故用 xfail(strict=True) 断言【正确】行为。
"""
import os
import re

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODULE_ROOT = os.path.abspath(os.path.join(_HERE, ".."))

_DEPLOY_SH = os.path.join(_MODULE_ROOT, "deploy.sh")
_COMPOSE = os.path.join(_MODULE_ROOT, "docker-compose.yml")


def _read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _extract_image_tag(text):
    """从 compose 风格文本里取第一个 macro-scan:vN tag。"""
    m = re.search(r"macro-scan:v(\d+)", text)
    return m.group(0) if m else None


def _build_source_file(deploy_text):
    """解析 deploy.sh _build(): IMAGE_TAG 是从哪个 compose 文件 grep 出来的。

    匹配形如: IMAGE_TAG=$(grep 'image:' <filename> | grep -o 'macro-scan:v[0-9]*' ...)
    返回该 filename(相对模块根)。
    """
    m = re.search(
        r"IMAGE_TAG=\$\(\s*grep\s+['\"]image:['\"]\s+([^\s|]+)",
        deploy_text,
    )
    return m.group(1) if m else None


def test_deploy_build_tag_matches_compose_image_tag():
    """deploy.sh --build 构建的镜像 tag 必须与 docker-compose.yml 的 image tag 一致。"""
    deploy_text = _read(_DEPLOY_SH)
    compose_text = _read(_COMPOSE)

    # 确认 _build 确实从某个 compose 文件取 tag(签名核对: deploy.sh:70)
    src_file = _build_source_file(deploy_text)
    assert src_file is not None, (
        "无法在 deploy.sh 中定位 IMAGE_TAG 的来源文件, deploy.sh 结构可能已变更"
    )

    src_path = os.path.join(_MODULE_ROOT, src_file)
    assert os.path.exists(src_path), f"deploy.sh 引用的 compose 文件不存在: {src_file}"

    build_tag = _extract_image_tag(_read(src_path))
    compose_tag = _extract_image_tag(compose_text)

    assert build_tag is not None, f"未能从 {src_file} 解析出 macro-scan:vN tag"
    assert compose_tag is not None, "未能从 docker-compose.yml 解析出 macro-scan:vN tag"

    assert build_tag == compose_tag, (
        f"构建 tag({build_tag}, 源自 {src_file})与运行 tag"
        f"({compose_tag}, docker-compose.yml)不一致 → --build 产物永不被启用"
    )


# 已确认但尚未修复的 bug: 期望上面测试通过, 但当前代码会失败(v7 != v8)。
# strict=True: 一旦有人修复(tag 对齐/改从 docker-compose.yml 取源)导致 xpass, 强制摘标记。
test_deploy_build_tag_matches_compose_image_tag = pytest.mark.xfail(
    strict=True,
    reason="审计发现 #14 HIGH correctness: deploy.sh --build 从 example.yml 取 v7, "
    "但 docker-compose.yml 期望 v8, 构建产物永不被 compose 启用",
)(test_deploy_build_tag_matches_compose_image_tag)
