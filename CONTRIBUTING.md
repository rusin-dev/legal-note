# 贡献指南 | Contributing Guide

感谢你有兴趣为 rusin-note-desktop 做出贡献。本文档说明在本仓库工作的约定。

> 本项目仍处于早期阶段，`src/` 下大部分模块目前只有目录骨架和中文说明注释。如果你打算实现某个功能，请先提 Issue 说明思路，避免和其他人或维护者的工作重复。

## 开始之前

- **提 Issue**：新功能、较大的重构、以及行为变更，先开 Issue 讨论范围和方案。
- **可以直接提 PR 的**：错别字与文档修正、明确的小 bug 修复。
- **不建议的**：未经讨论的依赖升级、目录结构大改、批量格式化既有代码。

## 环境搭建

项目使用 [uv](https://docs.astral.sh/uv/) 管理依赖和虚拟环境，Python 版本要求 **3.12 及以上**（见 `.python-version` 与 `pyproject.toml`）。

**所有依赖安装和运行操作都通过 `uv` 完成**（由 `uv sync` 管理的项目虚拟环境），不要直接对系统 Python 使用 `pip`，也不要把 `.venv/` 提交到仓库。

```bash
# 安装 uv 本体（仅首次，推荐按 uv 官方文档的方式安装）
pip install uv

# 克隆仓库
git clone <repo-url>
cd rusin-note-desktop

# 创建虚拟环境并安装依赖
uv sync

# 验证环境，应输出 Python 3.12+
uv run python --version

# 运行入口（当前 main.py 只有说明注释，执行后无输出属于正常现象）
uv run main.py
```

新增或移除依赖请用 `uv add` / `uv remove`，它们会同步更新 `pyproject.toml` 和 `uv.lock`，请把这两个文件的改动一起提交：

```bash
uv add <package>      # 添加依赖
uv remove <package>   # 移除依赖
```

只临时装进环境、不写进 `pyproject.toml` 时用 `uv pip install <package>`（例如调试工具）。

## 项目结构

```
main.py                 程序入口
src/
  app.py                应用装配
  core/                 与具体功能无关的基础设施
    logger.py           日志（RotatingFileHandler 轮转）
    ui/                 UI 层
  modules/              功能模块，一个目录一件事
    ai_copilot/         AI 副驾驶，按后端拆分（openai / anthropic / ollama）
    storage/            笔记存储，local 与 remote 分离
    updater/            更新检查
```

除 `src/core/logger.py` 外，上表中的文件目前大多只有中文说明注释，功能尚待实现。

约定：

- 新的独立功能放在 `src/modules/<功能名>/` 下，模块内部通过 `__init__.py` 暴露必要接口，不要把实现细节散落到调用方。
- 跨功能复用的通用能力（日志、配置等）放在 `src/core/`。
- 同一类后端的多种实现参照 `ai_copilot` 的目录形态：各实现独立成文件，公共抽象放在 `base.py`（当前尚无内容）。
- README 中提到的 Flet 界面与插件/主题系统尚未接入代码，相关改动请先在 Issue 中讨论。

## 开发流程

1. 从 **`dev-v1`** 切出分支（这是当前的活跃开发分支），分支名体现改动类型：`feat/markdown-render`、`fix/storage-crash`。
2. 提交信息沿用仓库现有风格，即 Conventional Commits 的前缀加中文描述：

   ```
   feat: 添加程序入口
   fix: 修复日志轮转大小配置
   docs: 补充贡献指南
   ```

   一次提交只做一件事；功能未定型时可用 `WIP:` 前缀标记。
3. 本地确认改动可运行、没有引入回归后再推送。
4. PR 的目标分支同样选 `dev-v1`；`main` 由每日自动合并保持同步，**不要直接向 `main` 提 PR**。PR 描述请说明：改动目的、如何验证、关联的 Issue 编号（`Closes #123`）。
5. 及时 rebase 或合并 `dev-v1` 的更新，减少冲突。针对 `dev-v1` 的 PR 会触发 CodeQL 静态扫描，若报警请先修复并在 PR 描述中说明。
6. 维护者审阅后才会合并；请勿自行合并自己的 PR，除非只是修正文档笔误。

## 代码风格

以下约定来自仓库现有代码，请保持一致：

- 每个模块文件顶部写一段中文 docstring，说明该文件的职责（如 `"""日志入口"""`）。
- 函数带类型标注，返回值也标注（参考 `src/core/logger.py` 的 `get_logger(name: str, filename: str) -> Logger`）。
- 注释和文档字符串用中文；标识符用英文。
- 字面量在行尾用注释标明实际含义，例如日志轮转大小 `maxBytes=64*1024*1024` 旁注明其代表的量级。
- 只在系统边界（网络响应、用户输入、外部配置文件）做校验，内部调用不过度防御。

项目目前尚未配置格式化器和测试框架，因此**没有需要运行的 lint / 测试命令**。请不要在 PR 里夹带全仓库的格式改动。等工具链建立后本节会同步更新。

## 许可证

提交贡献即表示你同意该贡献按仓库 `LICENSE`（GPL-3.0）中的条款发布，且你有权这样授权。请勿提交包含第三方专有代码或凭据（API Key、Token）的内容。
