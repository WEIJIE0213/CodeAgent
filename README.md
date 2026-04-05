# CodeAgent

[![PyPI](https://img.shields.io/pypi/v/weijie-codeagent)](https://pypi.org/project/weijie-codeagent/)
[![Python](https://img.shields.io/pypi/pyversions/weijie-codeagent)](https://pypi.org/project/weijie-codeagent/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

基于 **LangGraph** 的 CLI 编程 Agent 助手，支持意图路由、任务拆解、分层记忆、11 种工具调用和实时推理展示。

```
You: 查看一下当前项目，分析主要功能

[CODE] Agent  ──────────────────────────────────────
  💭 我来查看项目结构并分析其功能。
  → 调用 list_dir
  💭 让我查看核心配置文件和入口。
  → 调用 read_file

╭──────────────── [CODE] Agent ─────────────────╮
│ ## 项目功能分析                                │
│ 这是一个基于 LangGraph 的多 Agent 编程助手…   │
╰────────────────────────────────────────────────╯
```

## 特性

| 能力 | 说明 |
|------|------|
| **意图路由** | 自动识别用户意图，路由到合适 Agent（代码 / 任务 / 问答 / 记忆） |
| **代码生成** | 生成完整可运行代码，Reflection 自动审查与修正 |
| **任务拆解** | 复杂任务拆解为子步骤，实时展示任务链进度（✓） |
| **分层记忆** | 短期滑动窗口 + SQLite 长期持久化 + Qdrant 向量语义检索 |
| **11 种工具** | 文件读写、精确编辑、多策略搜索、Shell 沙箱、任务追踪、MCP 协议 |
| **推理展示** | 工具调用时展示 💭 推理步骤和 → 工具名，最终答案整块渲染 |

## 快速开始

### 环境要求

- Python 3.11+
- Qdrant（向量记忆，可选）

### 安装

```bash
# 推荐使用虚拟环境
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate  # Linux/Mac

pip install weijie-codeagent -i https://pypi.org/simple
```

或从源码安装：

```bash
git clone https://github.com/WEIJIE0213/codeagent
cd codeagent
pip install -e .
```

### 配置

推荐使用全局配置文件，在任意目录都能直接使用：

```bash
# Windows
mkdir %USERPROFILE%\.codeagent
# 在 C:\Users\<你的用户名>\.codeagent\ 下创建 .env 文件
```

```env
# LLM 配置（必填）
LLM_API_KEY=your_api_key_here
LLM_BASE_URL=https://ark.cn-beijing.volces.com/api/coding/v3
LLM_MODEL=deepseek-v3.2

# Embedding 向量配置
EMBEDDING_MODEL=doubao-embedding-vision-250615
EMBEDDING_BASE_URL=https://ark.cn-beijing.volces.com/api/coding/v3

# Qdrant 向量数据库地址
QDRANT_URL=http://localhost:6333

# 工具操作的根目录（可选，默认为启动命令时所在目录）
# WORKSPACE_DIR=E:\your\project
```

也可以在项目目录下创建 `.env` 文件（仅对该目录生效）。

### 启动 Qdrant（向量记忆，可选）

```bash
docker run -d -p 6333:6333 -v qdrant_storage:/qdrant/storage qdrant/qdrant
```

不启动也可正常使用，向量检索会静默跳过。

### 运行

```bash
# Windows 建议设置 UTF-8
set PYTHONUTF8=1

# 交互对话模式
codeagent chat

# 单次执行
codeagent run "帮我写一个快速排序算法"

# 切换会话（多项目隔离）
codeagent chat --thread my-project

# 查看当前配置
codeagent config
```

## 内置命令

在交互模式下输入斜杠命令：

| 命令 | 说明 |
|------|------|
| `/help` | 显示帮助和工具列表 |
| `/history` | 查看本次会话对话历史 |
| `/memory` | 查看长期记忆摘要 |
| `/tasks` | 查看最近一次任务拆解计划 |
| `/compress` | 手动触发上下文压缩 |
| `/config` | 查看当前配置 |
| `/clear` | 开启新会话（旧记录保留在 SQLite） |
| `/exit` | 退出 |

## 可用工具

Agent 会根据需要自动调用：

| 分类 | 工具 | 说明 |
|------|------|------|
| 文件读写 | `read_file` | 读取工作目录内的文件 |
| | `write_file` | 写入文件（整体覆盖，自动创建目录） |
| | `list_dir` | 列出目录内容 |
| 精确编辑 | `apply_diff` | 应用 unified diff 补丁，精确修改局部内容 |
| | `search_and_replace` | 在文件中搜索并替换文本 |
| | `insert_content` | 在指定行号后插入内容 |
| 搜索 | `search_files` | 多策略搜索（git grep → ripgrep → Python） |
| | `search_code` | 正则表达式搜索代码文件 |
| 执行 | `run_shell` | 沙箱执行 Shell 命令（危险命令拦截） |
| 追踪 | `update_todos` | Agent 内部任务列表（add/list/complete/remove） |
| MCP | `use_mcp_tool` | 调用外部 MCP 工具服务器 |

**Shell 沙箱安全策略**：黑名单拦截 `rm -rf` / `dd` / `mkfs` 等危险命令，30s 超时，环境变量隔离，输出最多 10000 字符。

## MCP 工具服务器配置

在 `~/.codeagent/mcp_servers.json` 中配置（与 Claude Desktop 格式兼容）：

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/dir"]
    }
  }
}
```

安装 MCP SDK 后即可使用：

```bash
pip install "weijie-codeagent[mcp]"
```

## 架构

```
用户输入
   │
   ▼
context_loader      ← 加载长期摘要 + Qdrant 向量检索（Top-3）
   │
   ▼
intent_router       ← LLM 分类: code / decompose / qa / memory
   │
   ├── code ──────► code_agent        ← 代码生成 + 11 种工具调用
   ├── decompose ► task_decomposer    ← 任务拆解 + 工具调用 + 任务链展示
   └── qa/memory ► context_qa        ← 上下文问答 / 记忆查询
                         │
                         ▼
                     reflection       ← 仅 code/decompose 触发，最多修正 1 次
                         │
                         ▼
                     memory_writer    ← 更新短期窗口 + SQLite + Qdrant
                         │
                         ▼
                      终端输出（推理步骤 + 最终答案）
```

**记忆层**：
- **短期**：滑动窗口 10 轮消息（In-Memory）
- **长期**：SQLite 会话摘要持久化（`codeagent.db`）
- **向量**：Qdrant 语义检索，每次对话前自动召回相关历史

## 环境变量参考

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LLM_API_KEY` | — | LLM API Key（必填） |
| `LLM_BASE_URL` | Ark API | OpenAI 兼容 BaseURL |
| `LLM_MODEL` | `deepseek-v3.2` | 模型名称 |
| `EMBEDDING_MODEL` | `doubao-embedding-vision-250615` | Embedding 模型 |
| `EMBEDDING_BASE_URL` | Ark API | Embedding 接口地址 |
| `QDRANT_URL` | `http://localhost:6333` | Qdrant 地址 |
| `WORKSPACE_DIR` | `.` | 工具调用的文件操作根目录 |
| `WINDOW_SIZE` | `10` | 短期记忆滑动窗口轮数 |
| `LLM_MAX_RETRIES` | `3` | API 限流重试次数 |

## 依赖

- [LangGraph](https://github.com/langchain-ai/langgraph) — Agent 图编排
- [LangChain OpenAI](https://github.com/langchain-ai/langchain) — LLM 接口
- [Typer](https://typer.tiangolo.com/) — CLI 框架
- [Rich](https://rich.readthedocs.io/) — 终端美化
- [Qdrant Client](https://qdrant.tech/) — 向量数据库
- [mcp](https://github.com/modelcontextprotocol/python-sdk)（可选）— MCP 协议

## License

MIT
