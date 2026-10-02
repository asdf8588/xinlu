# Campus Mind 数字人 — 免费云端部署包

单容器 = 数字人页面（digital-human / wallpaper）+ LLM 流式对话 + TTS viseme 语音。
不需要 MySQL / Java 后端。浏览器打开一个网址即可使用，本机无需运行任何服务。

## 目录结构（自包含，可整个文件夹推到任意容器平台）

```
cloud/
  app.py            # FastAPI：静态托管 + /ai/chat/stream + /ai/tts
  config.py         # 环境变量配置（密钥不写死）
  llm.py            # LLM 客户端（OpenAI 兼容）
  prompts.py        # 系统提示词/情绪词表/危机关键词
  static/           # 前端页面 + vendor + Live2D 模型
  Dockerfile
  requirements.txt
```

> 前端改动后需重新同步：`Copy-Item src/main/resources/static/* deploy/cloud/static -Recurse -Force`

## 环境变量

| 变量 | 必填 | 说明 |
|---|---|---|
| `AI_API_KEY` | 是 | 智谱 API Key（glm-4-flash 免费） |
| `AI_MODEL` | 否 | 默认 glm-4-flash |
| `TTS_VOICE` | 否 | 默认 zh-CN-XiaoyiNeural |
| `PORT` | 否 | 默认 7860 |

## 方案 A：ClawCloud Run（推荐，国内直连快）

1. 用 GitHub 账号登录 https://run.claw.cloud（账号需注册满 180 天，每月赠 $5 额度，够跑满月）
2. Create → **Deploy from Dockerfile**（或先把这个文件夹推到 GitHub 仓库再选仓库）
3. Region 选 **Japan / Singapore**（国内延迟低）
4. Environment 里添加 `AI_API_KEY`
5. 部署完成后用分配的公网域名直接访问 `https://xxx.host/digital-human.html`

## 方案 B：Hugging Face Spaces（免费 2vCPU，国内需代理）

1. 新建 Space → SDK 选 **Docker**
2. 把本文件夹所有内容（含 static）推到 Space 的 git 仓库
3. Settings → Variables and secrets → 添加 `AI_API_KEY`（Secret）
4. 访问 `https://<user>-<space>.hf.space/digital-human.html`

## 方案 C：Render（免费 750h/月，闲置休眠）

1. GitHub 上新建仓库推送本文件夹
2. render.com → New → Web Service → 选仓库 → Runtime 选 Docker
3. Environment 添加 `AI_API_KEY`
4. 免费档 15 分钟无访问会休眠，首次打开冷启动约 50 秒

## 本地验证

```powershell
$env:AI_API_KEY='<你的key>'; $env:PORT='8085'; python app.py
# 浏览器打开 http://localhost:8085/digital-human.html
```

## 免费额度须知

- 免费容器普遍有**休眠机制**（HF 48h / Render 15min 无访问），首访冷启动 30-60s，之后正常
- glm-4-flash 免费；edge-tts 免费；容器流量按平台额度计
- API Key 通过平台 Secret 注入，不要提交进公开仓库

## 壁纸模式（云端版）

wallpaper.html 同样可访问，Lively Wallpaper 里填云端 URL 即可——
这样**换电脑/重装系统也能用同一套数字人壁纸**（时钟+气泡可用；语音问候依赖服务不休眠）。
