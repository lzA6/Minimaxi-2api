# Minimaxi-Local-API - 一个高性能 Minimaxi (海螺AI) 本地代理

[!Status [<sup>1</sup>](https://img.shields.io/badge/status-开发中断-red.svg)](https://github.com/wdawdwa/minimaxi-local)
[!License [<sup>2</sup>](https://img.shields.io/badge/license-MIT-blue.svg)](https://opensource.org/licenses/MIT)

**一个将 Minimaxi (海螺AI) 网页版聊天接口转换为 OpenAI 标准 API 格式的本地代理服务。本项目旨在提供一个高性能、支持多 `token` 轮询的解决方案，但由于目标网站后端验证机制的升级，目前在公有云平台（如 Hugging Face）上的部署已宣告失败。**

**警告：本项目目前处于【开发中断】状态。直接部署将无法正常工作。请仔细阅读本文档以了解原因和潜在的解决方案。**

---

## 核心功能 (设计目标)

*   **OpenAI 格式兼容**: 将 Minimaxi 的 SSE 流式接口无缝转换为 OpenAI `v1/chat/completions` 格式，兼容各种下游应用（如 LobeChat, NextChat 等）。
*   **高性能异步处理**: 基于 `FastAPI` 和 `httpx`，全程异步处理，实现高并发、低延迟。
*   **多 Token 轮询**: 支持配置多个 Minimaxi 账号的 `token`，并通过 `itertools.cycle` 实现自动轮询，分摊请求压力。
*   **动态签名破解**: 成功逆向并实现了 Minimaxi 前端用于验证请求的 `yy` MD5 签名算法。
*   **Docker 化部署**: 提供完整的 `Dockerfile` 和 `docker-compose.yml`，方便本地一键启动。

## 项目的失败：一场与反逆向工程的军备竞赛

这个项目的开发过程经历了一场与 Minimaxi 后端反爬虫、反逆向工程机制的激烈对抗。理解这段历史对于任何想要继续此项目的人都至关重要。

### 阶段一：`401 Unauthorized` - Token 验证

*   **问题**: 最初的请求被 `401` 错误拒绝。
*   **原因**: 未提供或提供了过期的 `token`。
*   **解决方案**: 从浏览器开发者工具中抓取最新的 `token` 并通过环境变量传入。**此问题已解决。**

### 阶段二：`400 Bad Request` (请求异常) - `yy` 签名验证

*   **问题**: 即使 `token` 有效，请求依然被 `400` 错误拒绝，返回 "请求异常，请检查请求参数"。
*   **原因**: Minimaxi 服务器会验证一个名为 `yy` 的动态签名。该签名是基于 `unix` 时间戳、`uuid` 和 `msgContent` 等参数通过一个固定的盐 (`YY_SALT`) 进行 MD5 哈希计算得出的。我们最初的签名算法与服务器期望的不匹配。
*   **解决方案**: 通过精确分析前端 JS 代码，我们成功在 Python 后端复现了 `yy` 签名算法。**此问题理论上已解决，但被下一阶段的问题所掩盖。**

### 阶段三：`400 Bad Request` (请求异常) - 浏览器指纹验证

*   **问题**: 即使我们动态生成了正确的 `yy` 签名，请求依然被 `400` 拒绝。
*   **原因**: 我们发现 Minimaxi 的服务器不仅仅验证 `yy` 签名本身，还会交叉比对生成该签名的**请求的完整指纹**。这包括 `user-agent`、`cpu_core_num`、`screen_width` 等几十个浏览器环境参数。我们的 Python 请求由于缺少这些指纹参数，即使签名在数学上正确，也会被判定为“异常请求”。
*   **解决方案**: 我们将一个真实浏览器的所有指纹参数硬编码到请求中，尝试完美伪装。**但此方案依然失败**，我们推断签名算法中可能包含了 `cookie` 或其他更深层次的动态值，导致纯 HTTP 请求无法模拟。

### 最终阶段：`Executable doesn't exist` - 部署环境的鸿沟 (Hugging Face)

*   **问题**: 为了绕过所有签名和指纹问题，我们决定采用终极武器：`Playwright`，一个无头浏览器自动化工具。但在 Hugging Face Spaces 上部署时，应用启动后立刻崩溃。
*   **原因**: 这是压垮项目的最后一根稻草。
    1.  `Playwright` 需要在环境中安装一个完整的 Chromium 浏览器。
    2.  在 `Dockerfile` 中，安装过程通常以 `root` 用户执行，浏览器被安装在 `/root/.cache/` 目录下。
    3.  然而，Hugging Face 出于安全考虑，在运行时是以一个低权限的 `user` 用户来运行我们的应用。
    4.  这个 `user` 用户没有权限访问 `/root` 目录，因此当 Playwright 尝试启动浏览器时，它找不到可执行文件，导致应用崩溃。
    5.  我们尝试了各种 `Dockerfile` 技巧（如切换用户安装、全程 root），但都因为 Hugging Face 环境的权限黑箱而失败。`playwright install --with-deps` 命令要么因权限不足无法安装系统依赖，要么安装到错误的位置。
*   **结论**: **在 Hugging Face Spaces 这种高度隔离和受控的 PaaS 平台上，部署需要复杂系统依赖和特定文件路径的 Playwright 应用是极其困难且不可靠的。**

## 当前状态与未实现的功能

*   **核心功能**: **完全不可用**。由于上述原因，无论是基于 `httpx` 的直接请求还是基于 `Playwright` 的浏览器自动化，都无法成功与 Minimaxi 服务器建立有效的通信。
*   **代码结构**: 项目保留了 v8.0 (Playwright 方案) 的代码结构，因为它代表了解决此问题的最终尝试方向。
*   **配置**: `config.py` 和 `.env` 文件中的配置项是完整的，但由于核心功能失效，它们目前没有实际作用。

## 如何在【你自己的环境】中拯救这个项目

尽管在 Hugging Face 上部署失败了，但理论上，你可以在一个你拥有完全 `root` 控制权的环境中让这个项目（的 Playwright 版本）起死回生。

### 部署环境要求

*   一台你拥有 `root` 权限的 Linux 服务器 (如 VPS, EC2, 或本地虚拟机)。
*   已安装 Docker 和 Docker Compose。

### 部署步骤

1.  **克隆仓库**:
    ```bash
    git clone https://github.com/wdawdwa/minimaxi-local.git
    cd minimaxi-local
    ```

2.  **获取你的 Minimaxi Token**:
    *   在 Chrome 浏览器中登录 `https://chat.minimaxi.com`。
    *   按 `F12` 打开开发者工具，切换到“网络(Network)”标签页。
    *   随便发送一条消息，找到名为 `msg` 的请求。
    *   在“请求标头(Request Headers)”中，找到 `token`，复制其完整的 `eyJ...` 值。

3.  **创建并配置 `.env` 文件**:
    在项目根目录下创建一个名为 `.env` 的文件，填入以下内容：

    ```dotenv
    # .env - Minimaxi-Local-API 配置文件

    # 服务监听的外部端口
    LISTEN_PORT=8085

    # 应用元数据
    APP_NAME="Minimaxi Local API"
    APP_VERSION="8.0.0-dev"
    DESCRIPTION="一个基于 Playwright 的高性能 Minimaxi 网页版聊天本地代理。"

    # 你的 API 访问密钥，可以设置为任何你喜欢的字符串
    API_MASTER_KEY="your_secret_key"

    # 你的 Minimaxi 账号凭证
    # 将这里替换为你从浏览器复制的真实 token
    MINIMAXI_TOKENS="替换为你的token"
    ```

4.  **使用 Docker Compose 构建并启动**:
    使用 `v9.0 - 回归初心，全程 Root` 版本的 `Dockerfile`。确保你的 `docker-compose.yml` 文件内容如下：

    ```yaml
    # docker-compose.yml
    version: '3.8'
    services:
      minimaxi-local:
        build: .
        ports:
          - "${LISTEN_PORT:-8085}:8085"
        env_file:
          - .env
        restart: unless-stopped
        # 增加 shm_size 对 Playwright/Chrome 稳定运行至关重要
        shm_size: '2gb' 
    ```
    
    然后，在项目根目录执行：
    ```bash
    docker-compose up --build
    ```
    这将开始漫长的构建过程。由于你是在自己的环境中，`root` 权限是真实的，`playwright install` 应该会成功。

5.  **验证**:
    启动完成后，你可以通过 `curl` 或任何 API 测试工具来访问：
    ```bash
    curl -X GET "http://localhost:8085/v1/models" -H "Authorization: Bearer your_secret_key"
    ```
    如果一切顺利，它应该返回模型列表。然后你就可以在你的客户端中配置 `http://<你的服务器IP>:${LISTEN_PORT}` 作为 API 地址进行聊天了。

## 结论

这个项目是一个典型的逆向工程案例，它展示了与现代 Web 应用后端保护机制对抗的复杂性和脆弱性。虽然我们最终在 Hugging Face 平台碰壁，但整个过程和代码库对于学习 FastAPI、Playwright、Docker 以及理解网络请求攻防具有重要的参考价值。

如果你有决心和合适的环境，欢迎你接过这把战旗，让这个项目重获新生。

---
