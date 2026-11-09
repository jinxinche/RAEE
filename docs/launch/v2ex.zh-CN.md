# 开源 RAEE-Lite：AI 说“完成了”，具体测了什么？

> 发布草稿，尚未发布。目标：V2EX「分享创造」。复制正文前请去掉本行。

分享一下我的开源项目 RAEE-Lite，一个本地 Python 命令行工具，用来把需求和实际执行过的检查关联起来，提示缺失或过期的验证记录。

举个很小的例子：需求是“注册函数拒绝非法邮箱”，但测试只检查 `1 + 1 == 2`。测试确实通过了，这条需求却没有关联的验证记录。

仓库里的演示会走完四步：

1. 无关的算术测试通过，需求仍为 `UNTESTED`。
2. 给需求关联一个真正调用注册函数的测试，暴露错误：`FAILED_CHECK`。
3. 修复示例函数，两项测试通过：`OBSERVED_PASS`。
4. 再改源文件，先前的记录变为 `STALE`，提示需要重跑。

[看 40 秒演示与安装步骤](https://github.com/jinxinche/RAEE#see-the-difference)。视频是实际本地输出的编排回放，留了阅读停顿。想自己跑，在检查过的源码目录、Python 3.10+ 虚拟环境中执行：

```bash
python -m pip install --no-deps .
python examples/run_demo.py
```

示例在临时目录执行 Python 标准库测试，结束后自动清理，不需要 AI API 密钥或私人日志。

有个边界需要说清楚：需求与测试的关联由用户指定，RAEE-Lite 不会自动判断测试是否充分覆盖语义。`OBSERVED_PASS` 只表示记录到相应命令通过。演示中的邮箱检查也只判断是否含 `@`，不是生产级校验。

目前是 MIT 许可的 `v0.10.0rc2` 源码候选版。欢迎试用，尤其想了解：哪个状态难以理解？哪些情况下应该标记过期却没有标记？在哪一步安装或运行卡住了？

如果遇到问题，可以在 [反馈 Issue](https://github.com/jinxinche/RAEE/issues/7) 留下系统、Python 版本、期望结果和实际结果。用最小的合成例子即可，不用上传私人代码或原始聊天日志。

[项目源码](https://github.com/jinxinche/RAEE) · [中文说明](https://github.com/jinxinche/RAEE/blob/main/docs/README.zh-CN.md)

本文使用 AI 辅助整理；演示文字已与保存的实际运行输出核对。
